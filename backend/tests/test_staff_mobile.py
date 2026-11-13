"""A cell number on each staff account (0028, 13 Nov 2026).

The owner keeps the office's cell numbers on the Team page. A number is
optional, stored E.164 like every other number in the book, changed only by an
owner, and never written to a log or to the append-only staff_events trail.
"""

from __future__ import annotations

import uuid

import pytest

# Made-up numbers in a range nobody is issued: never a real employee's.
TYPED = "082 555 0123"
STORED = "+27825550123"


def _add(client, **extra) -> dict:
    address = f"cell-{uuid.uuid4().hex[:10]}@staff.test"
    response = client.post("/api/admin/staff",
                           json={"email": address, "role": "admin", **extra})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def owner(staff_as):
    return staff_as("owner")


def test_adding_someone_with_a_number_stores_it_e164(client, db, owner):
    member = _add(client, mobile=TYPED)

    assert member["mobile"] == STORED
    assert db.execute("select mobile from staff_users where id = %s",
                      (member["id"],)).fetchone() == (STORED,)


def test_adding_someone_without_a_number_leaves_it_empty(client, owner):
    assert _add(client)["mobile"] is None
    assert _add(client, mobile="")["mobile"] is None


def test_the_owner_sets_a_number_and_the_list_shows_it(client, db, owner):
    member = _add(client)

    response = client.patch(f"/api/admin/staff/{member['id']}/mobile",
                            json={"mobile": "0825550123"})

    assert response.status_code == 200
    assert response.json()["mobile"] == STORED
    listed = {m["id"]: m for m in client.get("/api/admin/staff").json()}
    assert listed[member["id"]]["mobile"] == STORED


@pytest.mark.parametrize("cleared", [None, "", "   "])
def test_a_blank_number_clears_it(client, db, owner, cleared):
    member = _add(client, mobile=TYPED)

    response = client.patch(f"/api/admin/staff/{member['id']}/mobile",
                            json={"mobile": cleared})

    assert response.status_code == 200
    assert response.json()["mobile"] is None
    assert db.execute("select mobile from staff_users where id = %s",
                      (member["id"],)).fetchone() == (None,)


@pytest.mark.parametrize("bad", ["12345", "033 342 2111", "082 555 01234", "not a number"])
def test_a_number_that_is_not_a_sa_mobile_is_refused(client, db, owner, bad):
    member = _add(client, mobile=TYPED)

    response = client.patch(f"/api/admin/staff/{member['id']}/mobile", json={"mobile": bad})

    assert response.status_code == 422
    assert db.execute("select mobile from staff_users where id = %s",
                      (member["id"],)).fetchone() == (STORED,)


def test_the_number_field_must_be_sent(client, owner):
    member = _add(client)

    response = client.patch(f"/api/admin/staff/{member['id']}/mobile", json={})

    assert response.status_code == 422


@pytest.mark.parametrize("role", ["viewer", "admin"])
def test_only_an_owner_changes_a_number(client, db, staff_as, role):
    staff_as("owner")
    member = _add(client, mobile=TYPED)
    staff_as(role)

    response = client.patch(f"/api/admin/staff/{member['id']}/mobile",
                            json={"mobile": "0825550999"})

    assert response.status_code == 403
    assert db.execute("select mobile from staff_users where id = %s",
                      (member["id"],)).fetchone() == (STORED,)


def test_an_unknown_staff_member_is_a_404(client, owner):
    response = client.patch(f"/api/admin/staff/{uuid.uuid4()}/mobile",
                            json={"mobile": TYPED})

    assert response.status_code == 404


def test_the_number_reaches_neither_the_logs_nor_the_audit_trail(client, db, owner, caplog):
    member = _add(client)

    with caplog.at_level("DEBUG"):
        client.patch(f"/api/admin/staff/{member['id']}/mobile", json={"mobile": TYPED})

    assert STORED not in caplog.text and "0825550123" not in caplog.text
    payloads = db.execute(
        "select event_type, payload::text from staff_events where subject = %s",
        (member["email"],),
    ).fetchall()
    assert ("mobile_changed", '{"has_mobile": true}') in payloads
    assert not any(STORED in p or "825550123" in p for _, p in payloads)


def test_the_database_refuses_a_number_that_is_not_e164(db):
    # The API normalises first; this is the backstop if anything else writes.
    member_id = db.execute(
        "insert into staff_users (email, role) values (%s, 'viewer') returning id",
        (f"raw-{uuid.uuid4().hex[:10]}@staff.test",),
    ).fetchone()[0]

    with pytest.raises(Exception, match="staff_users_mobile_e164"):
        db.execute("update staff_users set mobile = '082 555 0123' where id = %s",
                   (member_id,))
