"""Enrolling members, adding dependants, and the premium schedule.

Run against a real Postgres as induduzo_api, like test_api.py, because the
guarantees worth checking live in the database: one transaction per enrolment,
the unique indexes that refuse duplicates, and the grants the API role needs.

Every person here is invented. ID numbers are generated with a valid check
digit for a chosen birth date; phone numbers are placeholders.
"""

from __future__ import annotations

import random
import uuid
from datetime import date

import psycopg
import pytest
from psycopg.rows import dict_row

from app.schemas import valid_sa_id
from app.services import instalments


def _id_number(born: date, male: bool = False) -> str:
    sequence = random.randint(5000, 9999) if male else random.randint(0, 4999)
    body = born.strftime("%y%m%d") + "%04d" % sequence + "08"
    return next(body + str(d) for d in range(10) if valid_sa_id(body + str(d)))


def _policy_number() -> str:
    return "T" + uuid.uuid4().hex[:9].upper()


def _adult_id_number() -> str:
    """A different adult each call, so tests never collide on the unique index."""
    return _id_number(date(random.randint(1940, 1990), random.randint(1, 12), random.randint(1, 28)))


def _enrolment(**overrides) -> dict:
    body = {
        "surname": "Testperson",
        "first_names": "Thandiwe",
        "id_number": _adult_id_number(),
        "mobile": "082 000 0002",
        "email": "thandiwe@example.test",
        "address_line1": "1 Test Road",
        "city": "Pietermaritzburg",
        "postal_code": "3201",
        "policy_number": _policy_number(),
        "plan_code": "plan_a",
        "premium_cents": 25000,
        "cover_cents": 1_000_000,
        "payment_method": "debit_order",
        "debit_day": 25,
    }
    body.update(overrides)
    return body


def _lead(client) -> str:
    response = client.post("/api/enquiries", json={
        "first_name": "Thandiwe", "surname": "Testperson",
        "mobile_number": "082 000 0002", "contact_consent": True,
    })
    assert response.status_code == 201
    return response.json()["id"]


def _one(db, query: str, *params):
    return db.execute(query, params).fetchone()


def _count(db, query: str, *params) -> int:
    return _one(db, query, *params)[0]


# --- Enrolment -----------------------------------------------------------------

def test_enrolling_an_enquiry_writes_the_whole_family_record(client, db, staff_as):
    enquiry_id = _lead(client)
    staff_as("admin")
    body = _enrolment(enquiry_id=enquiry_id, id_number=_id_number(date(1980, 5, 20)))

    response = client.post("/api/admin/members", json=body)

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["instalments_scheduled"] == 12
    person_id, policy_id = result["person_id"], result["policy_id"]

    assert _one(db, "select id_number_status::text, gender::text, date_of_birth, source "
                    "from people where id = %s", person_id) == (
        "valid", "female", date(1980, 5, 20), "portal")
    assert _one(db, "select number, is_primary, is_whatsapp from person_phones "
                    "where person_id = %s", person_id) == ("+27820000002", True, True)
    assert _count(db, "select count(*) from addresses where person_id = %s", person_id) == 1
    assert _one(db, "select status_code, enquiry_id::text, premium_cents from policies "
                    "where id = %s", policy_id) == ("pending", enquiry_id, 25000)
    assert _one(db, "select member_type, person_id::text from policy_members "
                    "where policy_id = %s", policy_id) == ("main_member", person_id)
    assert _one(db, "select method, debit_day, frequency::text from policy_payments "
                    "where policy_id = %s", policy_id) == ("debit_order", 25, "monthly")

    schedule = db.execute("select due_date, amount_cents, status from premium_instalments "
                          "where policy_id = %s order by due_date", (policy_id,)).fetchall()
    assert len(schedule) == 12
    assert all(day.day == 25 and amount == 25000 and state == "due"
               for day, amount, state in schedule)
    assert schedule[0][0] >= date.today()

    assert _one(db, "select person_id::text, status::text from plan_enquiries where id = %s",
                enquiry_id) == (person_id, "awaiting_payment")
    assert _count(db, "select count(*) from enquiry_events where enquiry_id = %s "
                      "and event_type = 'converted_to_policy' and actor = 'admin@staff.test'",
                  enquiry_id) == 1
    assert _count(db, "select count(*) from staff_events where subject = %s "
                      "and event_type = 'member_enrolled'", person_id) == 1

    # The enquiry page now knows it has been enrolled.
    detail = client.get(f"/api/admin/enquiries/{enquiry_id}").json()
    assert detail["person_id"] == person_id

    # And it cannot be enrolled a second time.
    again = client.post("/api/admin/members", json=_enrolment(enquiry_id=enquiry_id))
    assert again.status_code == 409


def test_a_taken_policy_number_is_refused_and_nothing_is_written(client, db, staff_as):
    staff_as("admin")
    number = _policy_number()
    assert client.post("/api/admin/members", json=_enrolment(policy_number=number)).status_code == 201
    people_before = _count(db, "select count(*) from people")

    response = client.post("/api/admin/members", json=_enrolment(policy_number=number.lower()))

    assert response.status_code == 409
    assert number in response.json()["detail"]
    # The second person was inserted before the policy clashed; it must be gone.
    assert _count(db, "select count(*) from people") == people_before


def test_a_person_already_in_the_book_is_not_enrolled_twice(client, db, staff_as):
    staff_as("admin")
    id_number = _adult_id_number()
    assert client.post("/api/admin/members", json=_enrolment(id_number=id_number)).status_code == 201
    policies_before = _count(db, "select count(*) from policies")

    response = client.post("/api/admin/members", json=_enrolment(id_number=id_number))

    assert response.status_code == 409
    assert "ID number" in response.json()["detail"]
    assert _count(db, "select count(*) from policies") == policies_before


@pytest.mark.parametrize(
    "change, field",
    [
        ({"id_number": "1234567890123"}, "id_number"),
        ({"date_of_birth": "2001-01-01"}, "date_of_birth"),  # disagrees with the ID
        ({"mobile": "12345"}, "mobile"),
        ({"postal_code": "32"}, "postal_code"),
        ({"premium_cents": -1}, "premium_cents"),
        ({"account_number": "123"}, "account_number"),  # never accepted
    ],
)
def test_an_invalid_enrolment_is_422(client, staff_as, change, field):
    staff_as("admin")
    response = client.post("/api/admin/members", json=_enrolment(**change))

    assert response.status_code == 422
    assert field in response.json()["field_errors"]


def test_a_viewer_can_read_but_not_write(client, staff_as):
    staff_as("viewer")
    some_id = uuid.uuid4()

    assert client.get("/api/admin/policies").status_code == 200
    assert client.post("/api/admin/members", json=_enrolment()).status_code == 403
    assert client.post(f"/api/admin/policies/{some_id}/members",
                       json={"surname": "A", "first_names": "B", "member_type": "child"}).status_code == 403
    assert client.post(f"/api/admin/instalments/{some_id}/payment",
                       json={"paid_on": "2026-01-01", "amount_cents": 1, "method": "cash"}).status_code == 403
    assert client.post(f"/api/admin/instalments/{some_id}/waive",
                       json={"reason": "test"}).status_code == 403


def test_the_next_policy_number_follows_the_highest(client, staff_as):
    staff_as("admin")
    suggested = client.get("/api/admin/policies/next-number").json()["policy_number"]
    assert suggested.startswith("AA")

    assert client.post("/api/admin/members",
                       json=_enrolment(policy_number=suggested)).status_code == 201

    following = client.get("/api/admin/policies/next-number").json()["policy_number"]
    assert following == "AA" + str(int(suggested[2:]) + 1).zfill(len(suggested) - 2)


# --- Dependants ------------------------------------------------------------------

def test_dependants_join_the_policy_and_a_known_person_is_reused(client, db, staff_as):
    staff_as("admin")
    policy_id = client.post("/api/admin/members", json=_enrolment()).json()["policy_id"]
    spouse_id_number = _id_number(date(1983, 11, 4), male=True)

    spouse = client.post(f"/api/admin/policies/{policy_id}/members", json={
        "surname": "Testperson", "first_names": "Sipho", "id_number": spouse_id_number,
        "member_type": "spouse", "mobile": "083 000 0003"})
    child = client.post(f"/api/admin/policies/{policy_id}/members", json={
        "surname": "Testperson", "first_names": "Lwazi", "date_of_birth": "2015-03-10",
        "member_type": "child"})

    assert spouse.status_code == 201, spouse.text
    assert child.status_code == 201, child.text
    assert spouse.json()["existing_person"] is False

    lives = client.get(f"/api/admin/policies/{policy_id}").json()["lives"]
    assert [life["member_type"] for life in lives] == ["main_member", "spouse", "child"]
    assert lives[2]["entry_age"] == date.today().year - 2015 - (
        (date.today().month, date.today().day) < (3, 10))

    # The same spouse twice on one policy is refused.
    twice = client.post(f"/api/admin/policies/{policy_id}/members", json={
        "surname": "Testperson", "first_names": "Sipho", "id_number": spouse_id_number,
        "member_type": "spouse"})
    assert twice.status_code == 409

    # On a second policy the spouse is the SAME person, not a copy.
    other_policy = client.post("/api/admin/members", json=_enrolment()).json()["policy_id"]
    people_before = _count(db, "select count(*) from people")
    linked = client.post(f"/api/admin/policies/{other_policy}/members", json={
        "surname": "Testperson", "first_names": "Sipho", "id_number": spouse_id_number,
        "member_type": "extended"})
    assert linked.status_code == 201
    assert linked.json()["existing_person"] is True
    assert linked.json()["person_id"] == spouse.json()["person_id"]
    assert _count(db, "select count(*) from people") == people_before


def test_a_dependant_cannot_be_added_as_a_second_main_member(client, staff_as):
    staff_as("admin")
    policy_id = client.post("/api/admin/members", json=_enrolment()).json()["policy_id"]

    response = client.post(f"/api/admin/policies/{policy_id}/members", json={
        "surname": "X", "first_names": "Y", "member_type": "main_member"})

    assert response.status_code == 422


# --- The schedule ----------------------------------------------------------------

def test_due_dates_land_on_the_debit_day_and_clamp_at_month_end():
    assert instalments.due_dates(date(2027, 1, 15), 31, "monthly", 3) == [
        date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)]
    assert instalments.due_dates(date(2028, 2, 1), 30, "monthly", 1) == [date(2028, 2, 29)]
    # This month's debit day has already passed, so the first one is next month.
    assert instalments.due_dates(date(2026, 10, 20), 15, "monthly", 2) == [
        date(2026, 11, 15), date(2026, 12, 15)]
    assert instalments.due_dates(date(2026, 10, 20), None, "monthly", 1) == [date(2026, 10, 20)]
    assert instalments.due_dates(date(2026, 10, 20), 5, "once_off", 12) == [date(2026, 10, 20)]


def test_generating_the_schedule_again_adds_nothing(client, staff_as):
    staff_as("admin")
    policy_id = client.post("/api/admin/members", json=_enrolment()).json()["policy_id"]

    import os
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        assert instalments.generate(conn, policy_id) == 0


def test_the_first_payment_activates_the_policy_and_its_enquiry(client, db, staff_as):
    enquiry_id = _lead(client)
    staff_as("admin")
    policy_id = client.post("/api/admin/members",
                            json=_enrolment(enquiry_id=enquiry_id)).json()["policy_id"]
    first, second = client.get(f"/api/admin/policies/{policy_id}").json()["instalments"][:2]

    paid = client.post(f"/api/admin/instalments/{first['id']}/payment", json={
        "paid_on": date.today().isoformat(), "amount_cents": 25000, "method": "cash"})

    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json()["recorded_by"] == "admin@staff.test"
    assert _one(db, "select status_code from policies where id = %s", policy_id) == ("active",)
    assert _one(db, "select status::text from plan_enquiries where id = %s", enquiry_id) == ("active",)
    assert _count(db, "select count(*) from enquiry_events where enquiry_id = %s "
                      "and event_type = 'policy_activated'", enquiry_id) == 1

    again = client.post(f"/api/admin/instalments/{first['id']}/payment", json={
        "paid_on": date.today().isoformat(), "amount_cents": 25000, "method": "cash"})
    assert again.status_code == 409

    waived = client.post(f"/api/admin/instalments/{second['id']}/waive",
                         json={"reason": "Agreed payment holiday"})
    assert waived.status_code == 200
    assert waived.json()["status"] == "waived"


def test_overdue_and_upcoming_lists(client, db, staff_as):
    staff_as("admin")
    created = client.post("/api/admin/members", json=_enrolment()).json()
    policy_id = created["policy_id"]
    # Generation never creates past instalments, so make one ten days late.
    overdue_id = _one(db, "insert into premium_instalments (policy_id, due_date, amount_cents) "
                          "values (%s, current_date - 10, 25000) returning id::text", policy_id)[0]

    overdue = client.get("/api/admin/instalments", params={"view": "overdue"}).json()
    mine = [row for row in overdue if row["instalment_id"] == overdue_id]
    assert len(mine) == 1
    assert mine[0]["days_overdue"] == 10
    assert mine[0]["policy_number"] == created["policy_number"]
    assert mine[0]["main_member_phone"] == "+27820000002"

    upcoming = client.get("/api/admin/instalments", params={"view": "upcoming", "days": 40}).json()
    assert any(row["policy_id"] == policy_id and row["days_overdue"] <= 0 for row in upcoming)
    assert all(row["instalment_id"] != overdue_id for row in upcoming)
