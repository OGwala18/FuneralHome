"""The public form is the one place a stranger can write to the database.

What arrives there is checked before a single row is written (app/schemas.py)
and again by Postgres. These cases come from a probe on 13 Nov 2026, which
found that a NUL byte made the insert fail with a 500, that `a,b@x.com` would
have addressed the confirmation email to two mailboxes, and that a name could
be a spreadsheet formula or carry an invisible right-to-left override.

Each refusal must be a 422 naming the field (so the form can highlight it),
and must save nothing. Each acceptance must store exactly what was typed:
over-zealous validation would turn away a real family, which is worse.
"""

from __future__ import annotations

import uuid

import pytest


def _lead(**overrides) -> dict:
    payload = {"first_name": "Nomvula", "surname": "Dlamini",
               "mobile_number": "082 000 0003", "contact_consent": True}
    payload.update(overrides)
    return payload


def _count(db) -> int:
    return db.execute("select count(*) from plan_enquiries").fetchone()[0]


REFUSED = [
    # (field, value) - each refused with a 422 on that field, nothing saved
    ("first_name", "Nom\x00vula"),            # NUL: used to be a 500
    ("surname", "Dla\x1bmini"),               # escape character
    ("city", "Pieter\x00maritzburg"),
    ("surname", "Dlamini‮ilimalD"),      # right-to-left override
    ("first_name", "Nom​vula"),          # zero-width space
    ("first_name", "﻿Nomvula"),          # byte-order mark
    ("surname", "Dlamini\nZuma"),             # a name is one line
    ("surname", '=HYPERLINK("http://x","x")'),  # spreadsheet formula
    ("city", "+SUM(A1:A9)"),
    ("how_heard", "@cmd"),
    ("best_contact_time", "=1+1"),
    ("first_name", "<b>Nomvula</b>"),
    ("first_name", "12345"),                  # a name has letters
    ("first_name", "!!!"),
    ("email", "admin,attacker@example.test"),  # one field, one mailbox
    ("email", "a b@example.test"),
    ("email", "<a@example.test>"),
    ("email", "a@example.test\r\nBcc: b@example.test"),
    ("email", '"quoted"@example.test'),
    ("email", "a@example"),
    ("email", "=cmd@example.test"),
]


@pytest.mark.parametrize("field, value", REFUSED, ids=[f"{f}-{v!r}"[:40] for f, v in REFUSED])
def test_hostile_input_is_refused_on_its_field_and_saves_nothing(client, db, field, value):
    before = _count(db)

    response = client.post("/api/enquiries", json=_lead(**{field: value}))

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert field in body["field_errors"]
    assert _count(db) == before


ACCEPTED = [
    # (field, typed, stored) - real people's details must get through
    ("first_name", "Mary-Jane", "Mary-Jane"),
    ("surname", "O'Neil", "O'Neil"),
    ("surname", "Dlamini-Zuma", "Dlamini-Zuma"),
    ("surname", "Ngcobo Jnr.", "Ngcobo Jnr."),
    ("first_name", "Zoë", "Zoë"),
    ("first_name", "  Thabo   Sipho  ", "Thabo Sipho"),   # spaces tidied
    ("surname", "van der Merwe", "van der Merwe"),
    ("city", "Pietermaritzburg (PMB)", "Pietermaritzburg (PMB)"),
    ("suburb_or_town", "Unit 14, Edendale", "Unit 14, Edendale"),
    ("how_heard", "-a friend from church", "-a friend from church"),
    ("email", "First.Last+cover@Sub.Example.co.za", "first.last+cover@sub.example.co.za"),
    ("email", "o'connor@example.test", "o'connor@example.test"),
    # Stored as text, never run: the queries are parameterised throughout.
    ("surname", "Robert'); DROP TABLE plan_enquiries;--", "Robert'); DROP TABLE plan_enquiries;--"),
    ("city", "' OR '1'='1", "' OR '1'='1"),
]


@pytest.mark.parametrize("field, typed, stored", ACCEPTED, ids=[a[1][:30] for a in ACCEPTED])
def test_real_details_are_accepted_and_stored_as_typed(client, db, field, typed, stored):
    response = client.post("/api/enquiries", json=_lead(**{field: typed}))

    assert response.status_code == 201, response.json()
    assert db.execute(f"select {field} from plan_enquiries where id = %s",
                      (response.json()["id"],)).fetchone()[0] == stored


def test_notes_keep_line_breaks_and_emoji_but_not_hidden_characters(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]
    path = f"/api/enquiries/{enquiry_id}/application"
    notes = "My mother is 74.\n- She prefers isiZulu.\nNgiyabonga 🙏🏾 👨‍👩‍👧"

    assert client.patch(path, json={"terms_accepted": True, "notes": notes}).status_code == 200
    assert db.execute("select notes from plan_enquiries where id = %s",
                      (enquiry_id,)).fetchone()[0] == notes

    refused = client.patch(path, json={"terms_accepted": True, "notes": "fine\x00not fine"})
    assert refused.status_code == 422
    assert "notes" in refused.json()["field_errors"]


@pytest.mark.parametrize("field, value", [
    ("address_line1", "=HYPERLINK(\"x\")"),
    ("next_of_kin_name", "<img src=x>"),
    ("beneficiary_name", "‮evil"),
    ("next_of_kin_relationship", "son\x00"),
])
def test_stage_two_fields_are_held_to_the_same_rules(client, db, field, value):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]

    response = client.patch(f"/api/enquiries/{enquiry_id}/application",
                            json={"terms_accepted": True, field: value})

    assert response.status_code == 422
    assert field in response.json()["field_errors"]
    assert db.execute("select stage::text from plan_enquiries where id = %s",
                      (enquiry_id,)).fetchone()[0] == "lead"


def test_the_table_survives_an_injection_attempt(client, db):
    client.post("/api/enquiries", json=_lead(surname="x'); DELETE FROM plan_enquiries; --"))
    assert _count(db) > 0


# --- Requests that are not a form at all -----------------------------------------

def test_an_oversized_body_is_refused_before_it_is_read(client, db):
    before = _count(db)

    response = client.post("/api/enquiries", json=_lead(notes="x" * 300_000))

    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"
    assert _count(db) == before


def test_an_oversized_body_without_a_length_is_refused_while_reading(client, db):
    before = _count(db)

    def chunks():
        yield b'{"first_name": "'
        for _ in range(40):
            yield b"x" * 10_000
        yield b'"}'

    response = client.post("/api/enquiries", content=chunks(),
                           headers={"content-type": "application/json"})

    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"
    assert _count(db) == before


@pytest.mark.parametrize("content, content_type, status, code", [
    (b"{not json", "application/json", 422, "validation_failed"),
    (b"first_name=x", "application/x-www-form-urlencoded", 422, "validation_failed"),
    (b"[" * 20000 + b"]" * 20000, "application/json", 400, "bad_request"),
    (b"", "application/json", 422, "validation_failed"),
], ids=["broken-json", "form-encoded", "deeply-nested", "empty"])
def test_a_body_that_is_not_a_form_is_a_coded_4xx(client, content, content_type, status, code):
    response = client.post("/api/enquiries", content=content,
                           headers={"content-type": content_type})

    assert response.status_code == status
    assert response.json()["code"] == code


@pytest.mark.parametrize("enquiry_id", ["not-a-uuid", "../../etc/passwd", "1 OR 1=1",
                                        str(uuid.uuid4())])
def test_stage_two_for_a_made_up_enquiry_is_404(client, enquiry_id):
    response = client.patch(f"/api/enquiries/{enquiry_id}/application",
                            json={"terms_accepted": True})

    assert response.status_code == 404
    assert response.json()["code"] in {"enquiry_not_found", "not_found"}


def test_a_value_postgres_cannot_store_is_a_422_on_staff_routes_too(client, staff_as):
    """Staff screens are not validated as strictly as the public form; the
    database's refusal is turned into a 422, never a 500."""
    staff_as("admin")

    response = client.post(f"/api/admin/instalments/{uuid.uuid4()}/waive",
                           json={"reason": "family\x00request"})

    # The UPDATE carries the reason, so Postgres refuses it before any lookup.
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
