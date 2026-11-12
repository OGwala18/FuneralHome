"""The owner's enrolment requests of 11 Nov 2026.

- The last day of the month is a payment day, and lands on the last day.
- Cash or card in person names one of the three branches.
- The beneficiary is one of the policy's lives, or someone not covered with
  full details, and may be chosen after the dependants are added.
- A new member is welcomed on WhatsApp and by email.
"""

from __future__ import annotations

import calendar
import os
import random

import psycopg
import pytest
from psycopg.rows import dict_row

from app.services import welcome
from app.services.whatsapp import WhatsAppResult
from app.services.email import EmailResult
from test_enrolment import _adult_id_number, _enrolment


@pytest.fixture
def api_conn():
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        yield conn


def _mobile() -> str:
    digits = "%07d" % random.randint(0, 9_999_999)
    return f"084 {digits[:3]} {digits[3:]}"


def _enrol(client, **overrides) -> dict:
    response = client.post("/api/admin/members", json=_enrolment(mobile=_mobile(), **overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --- The last day of the month ------------------------------------------------------

def test_the_last_day_option_lands_on_the_last_day_of_each_month(client, staff_as, api_conn):
    staff_as("admin")
    enrolled = _enrol(client, debit_day=31)

    dates = [r["due_date"] for r in api_conn.execute(
        "select due_date from premium_instalments where policy_id = %s order by due_date",
        (enrolled["policy_id"],))]

    assert len(dates) >= 12
    for due in dates:
        assert due.day == calendar.monthrange(due.year, due.month)[1], due


# --- Paying at a branch -------------------------------------------------------------

@pytest.mark.parametrize("method", ["cash", "card"])
def test_paying_in_person_needs_a_branch(client, staff_as, method):
    staff_as("admin")
    response = client.post("/api/admin/members",
                           json=_enrolment(payment_method=method, pay_branch_code=None))
    assert response.status_code == 422
    assert "pay_branch_code" in response.json()["field_errors"]


@pytest.mark.parametrize("branch, label", [
    ("edendale", "Edendale Main Road (Head Office)"),
    ("boshoff", "161 Boshoff Street"),
    ("langalibalele", "171 Langalibalele Street"),
])
def test_the_branch_is_kept_and_shown(client, staff_as, branch, label):
    staff_as("admin")
    enrolled = _enrol(client, payment_method="cash", pay_branch_code=branch)

    payment = client.get(f"/api/admin/policies/{enrolled['policy_id']}").json()["payment"]

    assert payment["method"] == "cash"
    assert payment["pay_branch_code"] == branch and payment["pay_branch_label"] == label


def test_a_branch_is_ignored_for_other_methods(client, staff_as):
    staff_as("admin")
    enrolled = _enrol(client, payment_method="eft", pay_branch_code="boshoff")
    payment = client.get(f"/api/admin/policies/{enrolled['policy_id']}").json()["payment"]
    assert payment["pay_branch_code"] is None


# --- Beneficiaries ------------------------------------------------------------------

def test_the_beneficiary_can_wait_for_the_dependants(client, staff_as):
    staff_as("admin")
    enrolled = _enrol(client, beneficiary=None)
    assert client.get(f"/api/admin/policies/{enrolled['policy_id']}").json()["beneficiaries"] == []


def test_a_dependant_can_be_made_the_beneficiary(client, staff_as):
    staff_as("admin")
    enrolled = _enrol(client, beneficiary=None)
    policy = enrolled["policy_id"]
    child = client.post(f"/api/admin/policies/{policy}/members", json={
        "surname": "Testperson", "first_names": "Lwazi", "member_type": "child",
        "date_of_birth": "2012-04-05"}).json()

    response = client.post(f"/api/admin/policies/{policy}/beneficiaries",
                           json={"person_id": child["person_id"], "relationship": "Son"})

    assert response.status_code == 201, response.text
    detail = client.get(f"/api/admin/policies/{policy}").json()
    assert [(b["first_names"], b["covered_life"], b["relationship"])
            for b in detail["beneficiaries"]] == [("Lwazi", True, "Son")]
    # Still a covered life, once.
    assert sum(1 for life in detail["lives"] if life["person_id"] == child["person_id"]) == 1


def test_someone_not_covered_can_be_the_beneficiary_with_full_details(client, staff_as, api_conn):
    staff_as("admin")
    enrolled = _enrol(client, beneficiary=None)
    brother = {
        "surname": "Testperson", "first_names": "Sipho", "id_number": _adult_id_number(),
        "mobile": _mobile(), "email": "sipho@example.test",
        "address_line1": "12 Test Road", "suburb": "Edendale", "city": "Pietermaritzburg",
        "postal_code": "3201", "relationship": "Brother",
    }

    response = client.post(f"/api/admin/policies/{enrolled['policy_id']}/beneficiaries",
                           json={"person": brother})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["covered_life"] is False
    person = api_conn.execute(
        "select email from people where id = %s", (body["person_id"],)).fetchone()
    assert person["email"] == "sipho@example.test"
    assert api_conn.execute(
        "select count(*) as n from addresses where person_id = %s", (body["person_id"],)
    ).fetchone()["n"] == 1
    detail = client.get(f"/api/admin/policies/{enrolled['policy_id']}").json()
    assert all(life["person_id"] != body["person_id"] for life in detail["lives"])
    assert detail["beneficiaries"][0]["relationship"] == "Brother"


def test_choose_one_way_or_the_other(client, staff_as):
    staff_as("admin")
    enrolled = _enrol(client, beneficiary=None)
    response = client.post(f"/api/admin/policies/{enrolled['policy_id']}/beneficiaries", json={})
    assert response.status_code == 422


def test_someone_off_the_policy_cannot_be_picked_as_a_life(client, staff_as):
    staff_as("admin")
    first = _enrol(client, beneficiary=None)
    second = _enrol(client, beneficiary=None)

    response = client.post(f"/api/admin/policies/{first['policy_id']}/beneficiaries",
                           json={"person_id": second["person_id"]})

    assert response.status_code == 404


def test_the_same_beneficiary_twice_is_a_conflict_and_removal_works(client, staff_as):
    staff_as("admin")
    enrolled = _enrol(client, beneficiary=None)
    policy = enrolled["policy_id"]
    url = f"/api/admin/policies/{policy}/beneficiaries"
    added = client.post(url, json={"person_id": enrolled["person_id"]}).json()

    assert client.post(url, json={"person_id": enrolled["person_id"]}).status_code == 409
    assert client.post(f"{url}/{added['beneficiary_id']}/remove").status_code == 204
    assert client.get(f"/api/admin/policies/{policy}").json()["beneficiaries"] == []


def test_a_beneficiary_given_at_enrolment_is_recorded(client, staff_as):
    staff_as("admin")
    enrolled = _enrol(client)  # the default form names a beneficiary
    detail = client.get(f"/api/admin/policies/{enrolled['policy_id']}").json()
    assert len(detail["beneficiaries"]) == 1
    assert detail["beneficiaries"][0]["covered_life"] is False


# --- The welcome ----------------------------------------------------------------------

def test_a_new_member_is_welcomed_on_whatsapp_and_by_email(client, staff_as, monkeypatch):
    sent = {}

    def fake_whatsapp(**kwargs):
        sent["whatsapp"] = kwargs
        return WhatsAppResult(sent=True, message_sid="SM" + "%032x" % random.getrandbits(128))

    def fake_email(**kwargs):
        sent["email"] = kwargs
        return EmailResult(sent=True)

    monkeypatch.setattr(welcome.whatsapp, "send_welcome", fake_whatsapp)
    monkeypatch.setattr(welcome, "send_member_welcome", fake_email)
    staff_as("admin")

    enrolled = _enrol(client, email="new.member@example.test")

    assert sent["whatsapp"]["policy_number"] == enrolled["policy_number"]
    assert "successfully added to the Induduzo family" in sent["whatsapp"]["body"]
    assert sent["email"]["to_email"] == "new.member@example.test"
    assert sent["email"]["policy_number"] == enrolled["policy_number"]


def test_the_review_link_is_included_only_when_set():
    with_link = welcome.welcome_text(first_name="Thandi", policy_number="AA1",
                                     review_url="https://g.page/r/test/review")
    without = welcome.welcome_text(first_name="Thandi", policy_number="AA1", review_url=None)
    assert "https://g.page/r/test/review" in with_link
    assert "review" not in without.lower()


def test_a_failed_welcome_never_fails_the_enrolment(client, staff_as, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("twilio down")

    monkeypatch.setattr(welcome.whatsapp, "send_welcome", broken)
    staff_as("admin")
    response = client.post("/api/admin/members", json=_enrolment(mobile=_mobile()))
    assert response.status_code == 201


# --- Enrolling from an enquiry carries everything across -------------------------

def test_the_enquiry_page_returns_everything_the_website_asked(client, staff_as):
    lead = client.post("/api/enquiries", json={
        "first_name": "Zanele", "surname": "Testperson", "mobile_number": _mobile(),
        "contact_consent": True, "best_contact_time": "evening",
    })
    assert lead.status_code == 201, lead.text
    enquiry_id = lead.json()["id"]
    application = client.patch(f"/api/enquiries/{enquiry_id}/application", json={
        "marital_status": "married", "cover_area": "emakhaya", "plan_selected": "plan_c",
        "coffin_choice": "casket", "age_band": "21-45", "number_of_dependants": 2,
        "next_of_kin_name": "Sipho Testperson", "next_of_kin_mobile": _mobile(),
        "next_of_kin_relationship": "Husband", "beneficiary_name": "Sipho Testperson",
        "beneficiary_mobile": _mobile(), "beneficiary_relationship": "Husband",
        "notes": "Please phone after five.", "terms_accepted": True,
    })
    assert application.status_code == 200, application.text

    staff_as("admin")
    detail = client.get(f"/api/admin/enquiries/{enquiry_id}").json()

    assert detail["marital_status"] == "married"
    assert detail["cover_area"] == "emakhaya"
    assert detail["coffin_choice"] == "casket"
    assert detail["age_band"] == "21-45"
    assert detail["next_of_kin_name"] == "Sipho Testperson"
    assert detail["next_of_kin_relationship"] == "Husband"
    assert detail["next_of_kin_mobile"].startswith("+27")
    assert detail["beneficiary_mobile"].startswith("+27")
    assert detail["best_contact_time"] == "evening"
    assert detail["notes"] == "Please phone after five."


def test_enrolment_notes_are_kept_on_the_policy(client, staff_as):
    staff_as("admin")
    note = "From website enquiry IND-TEST:\nNext of kin: Sipho Testperson (Husband)"
    enrolled = _enrol(client, notes=f"  {note}  ")

    policy = client.get(f"/api/admin/policies/{enrolled['policy_id']}").json()
    assert policy["notes"] == note

    # Blank notes are stored as nothing, not as an empty string.
    bare = _enrol(client, notes="   ")
    assert client.get(f"/api/admin/policies/{bare['policy_id']}").json()["notes"] is None
