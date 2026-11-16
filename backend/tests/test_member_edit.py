"""Correcting a member, changing their plan, and the history that keeps the old values.

Run against a real Postgres as induduzo_api, like test_enrolment.py, because
what matters lives in the database: one transaction per change, the unique
indexes that refuse a clash, and the triggers (0031) that keep every value an
edit overwrites, written with rights the API itself does not have.

Every person here is invented.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from test_enrolment import _adult_id_number, _enrolment, _id_number


def _one(db, query: str, *params):
    return db.execute(query, params).fetchone()


def _enrol(client, **overrides) -> dict:
    response = client.post("/api/admin/members", json=_enrolment(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _edit_body(client, policy_id: str, **changes) -> dict:
    """The edit form's request: what the form loaded, with `changes` typed over it."""
    current = client.get(f"/api/admin/policies/{policy_id}/member").json()
    body = {key: current[key] for key in (
        "surname", "first_names", "initials", "id_number", "email", "mobile",
        "language_preference", "address_line1", "address_line2", "suburb", "city",
        "province", "postal_code", "country_of_birth", "citizenship", "passport_number",
        "employment_status", "employer_name", "industry", "occupation", "job_role",
        "source_of_funds", "source_of_funds_other", "salary_day", "payment_method",
        "pay_branch_code", "debit_day", "notes")}
    body.update(changes)
    return body


def _due(db, policy_id: str) -> list[tuple]:
    return db.execute(
        "select due_date, amount_cents from premium_instalments "
        "where policy_id = %s and status = 'due' and archived_at is null order by due_date",
        (policy_id,)).fetchall()


# --- Correcting a member ---------------------------------------------------------

def test_the_edit_form_starts_from_what_was_enrolled(client, staff_as):
    staff_as("admin")
    enrolled = _enrol(client)

    form = client.get(f"/api/admin/policies/{enrolled['policy_id']}/member")

    assert form.status_code == 200, form.text
    body = form.json()
    assert body["policy_number"] == enrolled["policy_number"]
    assert body["person_id"] == enrolled["person_id"]
    assert body["mobile"] == "+27820000002"
    assert body["address_line1"] == "1 Test Road"
    assert (body["plan_code"], body["frequency"], body["debit_day"]) == ("plan_b", "monthly", 25)
    assert body["premium_cents"] == 25000


def test_a_correction_changes_the_member_and_the_history_keeps_what_it_was(client, db, staff_as):
    staff_as("admin")
    enrolled = _enrol(client)
    policy_id = enrolled["policy_id"]
    old_id = _one(db, "select id_number from people where id = %s", enrolled["person_id"])[0]
    new_id = _adult_id_number()

    response = client.patch(f"/api/admin/policies/{policy_id}/member", json=_edit_body(
        client, policy_id, surname="Corrected", id_number=new_id, mobile="083 111 2222",
        email="new@example.test", address_line1="2 Other Street", employment_status="pensioner",
        source_of_funds="pension", payment_method="cash", pay_branch_code="boshoff"))

    assert response.status_code == 200, response.text
    assert response.json()["surname"] == "Corrected"
    assert response.json()["mobile"] == "+27831112222"
    assert _one(db, "select surname, id_number, email, employment_status, employer_name "
                    "from people where id = %s", enrolled["person_id"]) == (
        "Corrected", new_id, "new@example.test", "pensioner", None)
    # The old number is archived, not deleted: one live primary, the new one.
    assert db.execute("select number from person_phones where person_id = %s "
                      "and archived_at is null", (enrolled["person_id"],)).fetchall() == [
        ("+27831112222",)]
    assert _one(db, "select method, pay_branch_code from policy_payments where policy_id = %s",
                policy_id) == ("cash", "boshoff")

    # What it used to say, and who changed it.
    history = client.get(f"/api/admin/policies/{policy_id}/history").json()
    people = next(e for e in history if e["table_name"] == "people" and e["operation"] == "update")
    changes = {c["field"]: (c["old"], c["new"]) for c in people["changes"]}
    assert people["changed_by"] == "admin@staff.test"
    assert changes["surname"] == ("Testperson", "Corrected")
    assert changes["id_number"] == (old_id, new_id)
    assert "updated_at" not in changes and "id_number_raw" not in changes
    phone = next(e for e in history if e["table_name"] == "person_phones"
                 and e["operation"] == "update")
    assert {c["field"]: c["old"] for c in phone["changes"]}["is_primary"] == "yes"


def test_the_policy_number_plan_and_premium_cannot_be_sent(client, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]
    for extra in ({"policy_number": "AA9999"}, {"plan_code": "plan_a"},
                  {"premium_cents": 100}, {"entry_date": "2020-01-01"}):
        response = client.patch(f"/api/admin/policies/{policy_id}/member",
                                json=_edit_body(client, policy_id, **extra))
        assert response.status_code == 422, extra


def test_a_viewer_can_open_the_form_but_not_save_it(client, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]
    body = _edit_body(client, policy_id, surname="Nope")
    staff_as("viewer")

    assert client.get(f"/api/admin/policies/{policy_id}/member").status_code == 200
    assert client.patch(f"/api/admin/policies/{policy_id}/member", json=body).status_code == 403
    assert client.post(f"/api/admin/policies/{policy_id}/plan",
                       json={"plan_code": "plan_a", "frequency": "monthly"}).status_code == 403


def test_an_id_number_changed_to_a_wrong_one_is_refused(client, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]

    good = _adult_id_number()
    response = client.patch(f"/api/admin/policies/{policy_id}/member", json=_edit_body(
        client, policy_id, id_number=good[:-1] + str((int(good[-1]) + 1) % 10)))

    assert response.status_code == 422
    assert "id_number" in response.json()["field_errors"]


def test_another_members_id_number_is_a_409_and_nothing_changes(client, db, staff_as):
    staff_as("admin")
    first = _enrol(client)
    second = _enrol(client)
    taken = _one(db, "select id_number from people where id = %s", first["person_id"])[0]

    response = client.patch(f"/api/admin/policies/{second['policy_id']}/member", json=_edit_body(
        client, second["policy_id"], id_number=taken, surname="Changed"))

    assert response.status_code == 409
    assert _one(db, "select surname from people where id = %s",
                second["person_id"]) == ("Testperson",)


def test_an_imported_bad_id_number_does_not_block_other_fixes(client, db, staff_as):
    """An ID number that fails its checksum came in with the paper book. Left
    as it is, it must not stop staff fixing the address."""
    staff_as("admin")
    enrolled = _enrol(client)
    good = _adult_id_number()
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)   # fails its checksum
    db.execute("update people set id_number = %s, id_number_status = 'checksum_failed' "
               "where id = %s", (bad, enrolled["person_id"]))

    response = client.patch(f"/api/admin/policies/{enrolled['policy_id']}/member",
                            json=_edit_body(client, enrolled["policy_id"],
                                            address_line1="9 Fixed Road",
                                            date_of_birth="1980-01-01"))
    assert response.status_code == 200, response.text
    assert _one(db, "select id_number, id_number_status::text from people where id = %s",
                enrolled["person_id"]) == (bad, "checksum_failed")
    assert response.json()["address_line1"] == "9 Fixed Road"


def test_adding_the_missing_id_and_mobile_clears_their_flags(client, db, staff_as):
    staff_as("admin")
    enrolled = _enrol(client, id_number=None, mobile=None, date_of_birth="1980-03-03",
                      gender="female")
    open_flags = ("select issue_code from data_quality_flags where person_id = %s "
                  "and resolved_at is null order by issue_code")
    assert db.execute(open_flags, (enrolled["person_id"],)).fetchall() == [
        ("id_number_missing",), ("phone_number_missing",)]

    response = client.patch(f"/api/admin/policies/{enrolled['policy_id']}/member", json=_edit_body(
        client, enrolled["policy_id"], id_number=_id_number(date(1980, 3, 3)),
        mobile="082 555 0101"))

    assert response.status_code == 200, response.text
    assert db.execute(open_flags, (enrolled["person_id"],)).fetchall() == []


def test_a_new_payment_day_moves_the_premiums_still_to_come(client, db, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]
    assert {d.day for d, _ in _due(db, policy_id)} == {25}

    response = client.patch(f"/api/admin/policies/{policy_id}/member",
                            json=_edit_body(client, policy_id, debit_day=1))

    assert response.status_code == 200, response.text
    due = _due(db, policy_id)
    assert {d.day for d, _ in due} == {1}
    assert len(due) == 12
    assert _one(db, "select count(*) from premium_instalments where policy_id = %s "
                    "and status = 'cancelled'", policy_id)[0] == 12


# --- Changing plan -----------------------------------------------------------------

def test_changing_plan_reprices_and_replaces_only_the_unpaid_premiums(client, db, staff_as):
    staff_as("admin")
    enrolled = _enrol(client)
    policy_id = enrolled["policy_id"]
    first = client.get(f"/api/admin/policies/{policy_id}").json()["instalments"][0]
    assert client.post(f"/api/admin/instalments/{first['id']}/payment", json={
        "paid_on": date.today().isoformat(), "amount_cents": 25000,
        "method": "cash"}).status_code == 200

    response = client.post(f"/api/admin/policies/{policy_id}/plan",
                           json={"plan_code": "plan_a", "frequency": "monthly"})

    assert response.status_code == 200, response.text
    assert response.json()["premium_cents"] == 35000
    # Same person, same policy number: nothing was enrolled again.
    assert _one(db, "select policy_number, plan_code, premium_cents from policies where id = %s",
                policy_id) == (enrolled["policy_number"], "plan_a", 35000)
    assert _one(db, "select count(*) from people where id = %s", enrolled["person_id"])[0] == 1
    # The paid premium keeps the amount it was paid at; what is still to come is new.
    assert _one(db, "select status, amount_cents from premium_instalments where id = %s",
                first["id"]) == ("paid", 25000)
    assert {amount for _, amount in _due(db, policy_id)} == {35000}

    change = _one(db, "select payload from staff_events where event_type = 'plan_changed' "
                      "and subject = %s order by created_at desc limit 1",
                  enrolled["person_id"])[0]
    assert change["from"]["plan_code"] == "plan_b" and change["to"]["plan_code"] == "plan_a"

    history = client.get(f"/api/admin/policies/{policy_id}/history").json()
    policy = next(e for e in history if e["table_name"] == "policies" and e["operation"] == "update")
    assert {c["field"]: (c["old"], c["new"]) for c in policy["changes"]}["premium_cents"] == (
        "25000", "35000")


def test_changing_to_quarterly_makes_quarterly_premiums(client, db, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]

    response = client.post(f"/api/admin/policies/{policy_id}/plan",
                           json={"plan_code": "plan_b", "frequency": "quarterly"})

    assert response.status_code == 200, response.text
    assert {amount for _, amount in _due(db, policy_id)} == {75000}
    assert len(_due(db, policy_id)) == 4


def test_the_same_plan_at_the_same_price_is_not_a_change(client, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]

    response = client.post(f"/api/admin/policies/{policy_id}/plan",
                           json={"plan_code": "plan_b", "frequency": "monthly"})

    assert response.status_code == 422
    assert "plan_code" in response.json()["field_errors"]


def test_a_cancelled_policy_cannot_change_plan(client, db, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]
    db.execute("update policies set status_code = 'cancelled' where id = %s", (policy_id,))

    response = client.post(f"/api/admin/policies/{policy_id}/plan",
                           json={"plan_code": "plan_a", "frequency": "monthly"})

    assert response.status_code == 409


# --- The history itself ------------------------------------------------------------

def test_the_api_can_read_the_history_but_never_write_it(db):
    assert db.execute("""
        select has_table_privilege(current_user, 'member_book_history', 'SELECT'),
               has_table_privilege(current_user, 'member_book_history', 'INSERT'),
               has_table_privilege(current_user, 'member_book_history', 'UPDATE'),
               has_table_privilege(current_user, 'member_book_history', 'DELETE')
    """).fetchone() == (True, False, False, False)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("insert into member_book_history (changed_by, table_name, row_id, operation) "
                   "values ('forged', 'people', gen_random_uuid(), 'update')")


def test_a_change_made_outside_the_portal_is_still_recorded(client, db, staff_as):
    """An import script or a SQL prompt has no staff email; the login is kept."""
    staff_as("admin")
    enrolled = _enrol(client)

    db.execute("update people set initials = 'TT' where id = %s", (enrolled["person_id"],))

    assert _one(db, """
        select changed_by, old_values ->> 'initials', new_values ->> 'initials'
          from member_book_history
         where table_name = 'people' and row_id = %s and operation = 'update'
         order by id desc limit 1""", enrolled["person_id"]) == ("induduzo_api", None, "TT")


def test_an_unknown_policy_has_no_history_or_form(client, staff_as):
    staff_as("admin")
    missing = "00000000-0000-0000-0000-00000000dead"
    assert client.get(f"/api/admin/policies/{missing}/history").status_code == 404
    assert client.get(f"/api/admin/policies/{missing}/member").status_code == 404


def test_a_member_from_the_paper_book_without_fica_answers_can_be_corrected(client, db, staff_as):
    staff_as("admin")
    enrolled = _enrol(client)
    db.execute("update people set country_of_birth = null, citizenship = null, "
               "employment_status = null, source_of_funds = null, employer_name = null, "
               "industry = null, occupation = null, job_role = null where id = %s",
               (enrolled["person_id"],))

    response = client.patch(f"/api/admin/policies/{enrolled['policy_id']}/member",
                            json=_edit_body(client, enrolled["policy_id"], mobile="082 777 0000"))

    assert response.status_code == 200, response.text
    assert response.json()["mobile"] == "+27827770000"
    assert response.json()["employment_status"] is None


def test_a_foreign_citizen_without_an_id_number_still_needs_a_passport(client, staff_as):
    staff_as("admin")
    policy_id = _enrol(client)["policy_id"]

    response = client.patch(f"/api/admin/policies/{policy_id}/member", json=_edit_body(
        client, policy_id, citizenship="ZW", id_number=None, date_of_birth="1980-01-01",
        passport_number=None))

    assert response.status_code == 422
    assert "passport_number" in response.json()["field_errors"]
