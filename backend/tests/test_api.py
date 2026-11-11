"""What must stay true before this API takes real registrations.

Each check runs against a real Postgres built from db/migrations, connected as
the restricted API role, because the bugs worth catching live in the SQL, the
grants and the row-level security rather than in Python alone.

No real person appears here. The ID numbers are generated, with a valid check
digit, and the mobile number is a placeholder that is never messaged: conftest
switches every notification channel off.
"""

from __future__ import annotations

import random
import re
import uuid

import psycopg
import pytest

from app import main
from app.schemas import valid_sa_id


def _lead(**overrides) -> dict:
    payload = {
        "first_name": "Test",
        "surname": "Applicant",
        "mobile_number": "082 000 0001",
        "plan_interest": "plan_a",
        "contact_consent": True,
    }
    payload.update(overrides)
    return payload


def _synthetic_id_number() -> str:
    """A made-up SA ID number that passes the same check the API applies."""
    body = "%02d%02d%02d%04d08" % (
        random.randint(50, 99), random.randint(1, 12), random.randint(1, 28),
        random.randint(0, 9999),
    )
    return next(body + str(d) for d in range(10) if valid_sa_id(body + str(d)))


def _count(db, query: str, *params) -> int:
    return db.execute(query, params).fetchone()[0]


# --- /health -------------------------------------------------------------------

def test_health_is_200_when_the_database_answers(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "up"


def test_health_is_503_when_the_database_does_not(client, monkeypatch):
    def unreachable():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "connection", unreachable)
    response = client.get("/health")

    # Railway and uptime monitors read any 2xx as healthy.
    assert response.status_code == 503
    assert response.json()["database"] == "down"


def test_health_says_who_whatsapp_may_message(client):
    # conftest leaves WHATSAPP_OUTBOUND blank, and blank means off.
    assert client.get("/health").json()["whatsapp_outbound"] == "off"


# --- Stage 1 -------------------------------------------------------------------

def test_stage_one_saves_one_lead_and_one_lead_captured_event(client, db):
    response = client.post("/api/enquiries", json=_lead())

    assert response.status_code == 201
    body = response.json()
    assert re.fullmatch(r"IND-\d{4}-\d{6}", body["reference"])
    assert body["mobile_number"] == "+27820000001"

    assert db.execute(
        "select stage::text, status::text from plan_enquiries where id = %s", (body["id"],)
    ).fetchall() == [("lead", "new")]
    assert _count(
        db,
        "select count(*) from enquiry_events where enquiry_id = %s and event_type = 'lead_captured'",
        body["id"],
    ) == 1


@pytest.mark.parametrize(
    "change, field",
    [
        ({"mobile_number": "12345"}, "mobile_number"),
        ({"contact_consent": False}, "contact_consent"),
        ({"first_name": ""}, "first_name"),
        ({"website": "https://spam.example"}, "website"),  # the honeypot
        ({"account_number": "123"}, "account_number"),  # unknown fields are refused
    ],
)
def test_an_invalid_lead_is_422_and_saves_nothing(client, db, change, field):
    before = _count(db, "select count(*) from plan_enquiries")

    response = client.post("/api/enquiries", json=_lead(**change))

    assert response.status_code == 422
    assert field in response.json()["field_errors"]
    assert _count(db, "select count(*) from plan_enquiries") == before


# --- Stage 2 -------------------------------------------------------------------

def test_stage_two_promotes_the_same_enquiry_rather_than_adding_one(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]
    id_number = _synthetic_id_number()
    before = _count(db, "select count(*) from plan_enquiries")

    response = client.patch(
        f"/api/enquiries/{enquiry_id}/application",
        json={"id_number": id_number, "plan_selected": "plan_a", "terms_accepted": True},
    )

    assert response.status_code == 200
    assert response.json()["id"] == enquiry_id
    assert _count(db, "select count(*) from plan_enquiries") == before
    assert db.execute(
        "select stage::text, status::text, id_number from plan_enquiries where id = %s",
        (enquiry_id,),
    ).fetchall() == [("application", "application_submitted", id_number)]
    assert _count(
        db,
        "select count(*) from enquiry_events "
        "where enquiry_id = %s and event_type = 'application_submitted'",
        enquiry_id,
    ) == 1


def test_an_invalid_application_is_422_and_leaves_the_lead_alone(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]

    response = client.patch(
        f"/api/enquiries/{enquiry_id}/application",
        json={"id_number": "1234567890123", "terms_accepted": True},
    )

    assert response.status_code == 422
    assert "id_number" in response.json()["field_errors"]
    assert db.execute(
        "select stage::text from plan_enquiries where id = %s", (enquiry_id,)
    ).fetchall() == [("lead",)]


def test_an_application_for_an_unknown_enquiry_is_404(client):
    response = client.patch(
        f"/api/enquiries/{uuid.uuid4()}/application", json={"terms_accepted": True}
    )

    assert response.status_code == 404


# --- The staff gate --------------------------------------------------------------

def _staff_routes() -> list[tuple[str, str]]:
    """Every staff route the app actually registers, found rather than listed,
    so a route added later is checked without anyone remembering to add it."""
    # Read from the OpenAPI schema rather than app.routes: FastAPI now wraps
    # included routers in a private type, and the schema is the public view.
    found = []
    for path, operations in main.app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            concrete = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
            found += [(method.upper(), concrete) for method in sorted(operations)]
    return found


def test_there_are_staff_routes_to_check():
    assert len(_staff_routes()) >= 9


@pytest.mark.parametrize("method, path", _staff_routes())
def test_staff_routes_refuse_a_caller_without_a_token(client, method, path):
    response = client.request(method, path, json={})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


# --- Adding staff --------------------------------------------------------------

def test_adding_staff_says_whether_an_invitation_was_sent(client, db, staff_as, caplog):
    owner = staff_as("owner")
    address = f"new-{uuid.uuid4().hex[:10]}@staff.test"

    with caplog.at_level("INFO"):
        response = client.post("/api/admin/staff", json={"email": address, "role": "viewer"})

    assert response.status_code == 201
    body = response.json()
    # conftest leaves the service-role key blank, so no invitation can be sent,
    # and the portal must be told so rather than say "check your email".
    assert body["invite_sent"] is False
    assert body["email"] == address
    assert db.execute(
        "select role::text from staff_users where email = %s", (address,)
    ).fetchall() == [("viewer",)]
    # Neither the owner's address nor the new person's reaches the logs.
    assert owner.email not in caplog.text
    assert address not in caplog.text


# --- Idempotency (0019) ----------------------------------------------------------

def test_a_retried_lead_with_the_same_key_is_one_enquiry(client, db):
    key = str(uuid.uuid4())
    before = _count(db, "select count(*) from plan_enquiries")

    first = client.post("/api/enquiries", json=_lead(), headers={"Idempotency-Key": key})
    again = client.post("/api/enquiries", json=_lead(), headers={"Idempotency-Key": key})

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert again.headers.get("idempotent-replayed") == "true"
    assert "idempotent-replayed" not in first.headers
    assert _count(db, "select count(*) from plan_enquiries") == before + 1
    assert _count(
        db,
        "select count(*) from enquiry_events where enquiry_id = %s and event_type = 'lead_captured'",
        first.json()["id"],
    ) == 1


def test_a_key_reused_with_different_details_is_refused(client, db):
    key = str(uuid.uuid4())
    client.post("/api/enquiries", json=_lead(), headers={"Idempotency-Key": key})
    before = _count(db, "select count(*) from plan_enquiries")

    response = client.post(
        "/api/enquiries", json=_lead(first_name="Someone"), headers={"Idempotency-Key": key}
    )

    assert response.status_code == 422
    assert _count(db, "select count(*) from plan_enquiries") == before


def test_a_key_that_is_not_a_uuid_is_400(client):
    response = client.post("/api/enquiries", json=_lead(), headers={"Idempotency-Key": "abc"})
    assert response.status_code == 400


def test_leads_without_a_key_still_work_for_older_browsers(client, db):
    before = _count(db, "select count(*) from plan_enquiries")
    assert client.post("/api/enquiries", json=_lead()).status_code == 201
    assert client.post("/api/enquiries", json=_lead()).status_code == 201
    assert _count(db, "select count(*) from plan_enquiries") == before + 2


def test_a_replay_does_not_use_up_the_rate_limit(client):
    key = str(uuid.uuid4())
    for _ in range(10):
        assert client.post(
            "/api/enquiries", json=_lead(), headers={"Idempotency-Key": key}
        ).status_code == 201


def test_the_same_application_twice_changes_and_records_nothing_more(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]
    body = {"id_number": _synthetic_id_number(), "plan_selected": "plan_a", "terms_accepted": True}

    first = client.patch(f"/api/enquiries/{enquiry_id}/application", json=body)
    again = client.patch(f"/api/enquiries/{enquiry_id}/application", json=body)

    assert first.status_code == again.status_code == 200
    assert again.headers.get("idempotent-replayed") == "true"
    assert _count(
        db,
        "select count(*) from enquiry_events "
        "where enquiry_id = %s and event_type = 'application_submitted'",
        enquiry_id,
    ) == 1


def test_a_corrected_application_still_updates(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]
    body = {"id_number": _synthetic_id_number(), "plan_selected": "plan_a", "terms_accepted": True}
    client.patch(f"/api/enquiries/{enquiry_id}/application", json=body)

    response = client.patch(
        f"/api/enquiries/{enquiry_id}/application", json={**body, "plan_selected": "plan_b"}
    )

    assert response.status_code == 200
    assert "idempotent-replayed" not in response.headers
    assert db.execute(
        "select plan_selected::text from plan_enquiries where id = %s", (enquiry_id,)
    ).fetchone()[0] == "plan_b"


def test_the_rate_limit_counts_the_proxy_address_not_a_forged_one(client):
    # A script that invents a new X-Forwarded-For per request must still be
    # counted as one caller: the proxy's own entry is the right-most one.
    statuses = [
        client.post(
            "/api/enquiries",
            json=_lead(),
            headers={"X-Forwarded-For": f"10.0.0.{n}, 203.0.113.7"},
        ).status_code
        for n in range(8)
    ]
    assert statuses[:6] == [201] * 6
    assert statuses[6:] == [429, 429]


def test_the_form_header_passes_the_cors_preflight(client):
    response = client.options(
        "/api/enquiries",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        },
    )
    assert response.status_code == 200
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()


# --- The plan sets the premium (0020) ----------------------------------------------

def test_the_form_cannot_set_its_own_premium(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]
    body = {"id_number": _synthetic_id_number(), "plan_selected": "plan_a",
            "terms_accepted": True, "premium_amount_cents": 1}

    response = client.patch(f"/api/enquiries/{enquiry_id}/application", json=body)

    assert response.status_code == 422
    assert "premium_amount_cents" in response.json()["field_errors"]


@pytest.mark.parametrize("plan, premium", [("plan_a", 35000), ("plan_b", 25000),
                                           ("dome_plan", 40000), ("plan_c", None)])
def test_the_premium_on_an_application_comes_from_the_plan(client, db, plan, premium):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]
    body = {"id_number": _synthetic_id_number(), "plan_selected": plan, "terms_accepted": True}

    assert client.patch(f"/api/enquiries/{enquiry_id}/application", json=body).status_code == 200
    assert db.execute("select premium_amount_cents from plan_enquiries where id = %s",
                      (enquiry_id,)).fetchone()[0] == premium
