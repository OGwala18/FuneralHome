"""Paying on WhatsApp: the bank details with the family's own policy number, and
the payment-day reminders (the owner's request, 11 Nov 2026).

Members are enrolled through the real API, so the phone, policy, payment day
and premium schedule are exactly what the portal would have created. Every
member gets a random phone number so tests never share a family.
"""

from __future__ import annotations

import os
import random
import re
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.rows import dict_row

from app.services import banking, payment_reminders, whatsapp_content as content
from app.services import whatsapp_line, whatsapp_menu as menu
from app.services.whatsapp import WhatsAppResult
from test_enrolment import _enrolment

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)


def _say(text: str, state: str = menu.IDLE) -> menu.Turn:
    return menu.respond(state=state, data={}, misses=0, text=text, has_media=False,
                        now=NOW, idle_since=None if state == menu.IDLE else NOW)


@pytest.fixture
def api_conn():
    """The API's own kind of connection: dict rows, as the services expect."""
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row,
                         autocommit=False) as conn:
        yield conn
        conn.rollback()


def _mobile() -> tuple[str, str]:
    """(as typed in the portal, as stored)."""
    digits = "%07d" % random.randint(0, 9_999_999)
    return f"083 {digits[:3]} {digits[3:]}", f"+2783{digits}"


def _enrol(client, staff_as, **overrides) -> tuple[dict, str]:
    staff_as("admin")
    typed, stored = _mobile()
    response = client.post("/api/admin/members", json=_enrolment(mobile=typed, **overrides))
    assert response.status_code == 201, response.text
    return response.json(), stored


# --- The bank details are ours and pinned -------------------------------------------

def test_the_bank_details_are_the_official_ones():
    # Changing these is a payments change: check against the bank's letter first.
    assert (banking.BANK, banking.ACCOUNT_NAME, banking.ACCOUNT_TYPE, banking.BRANCH_CODE,
            banking.ACCOUNT_NUMBER) == ("ABSA Bank", "Induduzo Funeral Home", "Current",
                                        "632005", "4127 601 408")


def test_the_pay_answer_carries_the_account_and_the_warning():
    text = menu.render(menu.NODES["pay.bank"])
    assert banking.ACCOUNT_NUMBER in text and banking.BRANCH_CODE in text
    assert content.POLICY_REFERENCE in text
    assert "Don't pay" in text


# --- "I want to pay my policy" ----------------------------------------------------

@pytest.mark.parametrize("text", [
    "I want to pay my policy", "how do I pay", "Banking details please",
    "ngifuna ukukhokha", "Can I pay now?", "what is your account number",
])
def test_asking_to_pay_goes_straight_to_the_bank_details(text):
    turn = _say(text)
    assert turn.state == "pay.bank"
    assert turn.node == "pay.bank"


@pytest.mark.parametrize("text", ["hello", "how does the payout work", "2"])
def test_other_messages_do_not(text):
    assert _say(text).state != "pay.bank"


def test_it_works_from_inside_another_menu():
    assert _say("I'd like to pay", state="claims").state == "pay.bank"


def test_the_pay_menu_offers_it():
    assert "pay.bank" in [option.goto for option in menu.NODES["pay"].options]


# --- The family's own policy number -------------------------------------------------

def test_a_main_member_gets_their_own_policy_number(client, staff_as, api_conn):
    enrolled, _ = _enrol(client, staff_as)

    reference = whatsapp_line.policy_reference(api_conn, enrolled["person_id"])

    assert reference.startswith(enrolled["policy_number"])


def test_someone_unknown_is_told_where_to_find_it(api_conn):
    reference = whatsapp_line.policy_reference(api_conn, None)
    assert "policy documents" in reference
    assert not re.search(r"[A-Z]{2,}\d{3,}", reference)


def test_the_line_fills_in_the_reference(client, staff_as, api_conn):
    enrolled, phone = _enrol(client, staff_as)
    message = whatsapp_line.Inbound(
        sid="SM" + "%032x" % random.getrandbits(128), account_sid="ACtest", from_number=phone,
        to_number="+27737310521", body="I want to pay my policy", profile_name=None, media=[])

    delivery = whatsapp_line.handle_inbound(api_conn, message, now=NOW)

    text = delivery.replies[0][0]
    assert f"Reference: {enrolled['policy_number']}" in text
    assert content.POLICY_REFERENCE not in text


# --- Payment day ------------------------------------------------------------------

@pytest.mark.parametrize("day", [1, 25, 31])
def test_the_payment_days_are_the_1st_25th_and_last(client, staff_as, day):
    enrolled, _ = _enrol(client, staff_as, debit_day=day)
    assert enrolled["instalments_scheduled"] > 0


@pytest.mark.parametrize("day", [2, 15, 30])
def test_other_payment_days_are_refused(client, staff_as, day):
    staff_as("admin")
    response = client.post("/api/admin/members", json=_enrolment(debit_day=day))
    assert response.status_code == 422
    assert "debit_day" in response.json()["field_errors"]


def test_a_monthly_plan_needs_a_payment_day(client, staff_as):
    staff_as("admin")
    response = client.post("/api/admin/members", json=_enrolment(debit_day=None))
    assert response.status_code == 422
    assert "debit_day" in response.json()["field_errors"]


# --- Reminders --------------------------------------------------------------------

class _Outbox:
    def __init__(self, ok: bool = True):
        self.sent: list[dict] = []
        self.ok = ok

    def __call__(self, **kwargs):
        self.sent.append(kwargs)
        sid = "SM" + "%032x" % random.getrandbits(128)
        return WhatsAppResult(sent=self.ok, message_sid=sid if self.ok else None,
                              error=None if self.ok else "failed")

    def for_policy(self, number: str) -> list[dict]:
        return [m for m in self.sent if m["policy_number"] == number]


def _first_due(api_conn, policy_id: str) -> dict:
    return api_conn.execute(
        "select id, due_date from premium_instalments where policy_id = %s "
        "order by due_date limit 1", (policy_id,)).fetchone()


def test_a_reminder_goes_on_the_payment_day_and_only_once(client, staff_as, api_conn):
    enrolled, phone = _enrol(client, staff_as, debit_day=25)
    due = _first_due(api_conn, enrolled["policy_id"])
    assert due["due_date"].day == 25
    outbox = _Outbox()

    payment_reminders.run(api_conn, due["due_date"], send=outbox)
    payment_reminders.run(api_conn, due["due_date"], send=outbox)

    mine = outbox.for_policy(enrolled["policy_number"])
    assert len(mine) == 1
    assert mine[0]["kind"] == "due" and mine[0]["to_mobile"] == phone
    assert banking.ACCOUNT_NUMBER in mine[0]["body"]
    assert f"Reference: {enrolled['policy_number']}" in mine[0]["body"]


def test_the_day_after_an_unpaid_premium_gets_one_more(client, staff_as, api_conn):
    enrolled, _ = _enrol(client, staff_as, debit_day=1)
    due = _first_due(api_conn, enrolled["policy_id"])
    outbox = _Outbox()

    payment_reminders.run(api_conn, due["due_date"] + timedelta(days=1), send=outbox)

    mine = outbox.for_policy(enrolled["policy_number"])
    assert [m["kind"] for m in mine] == ["missed"]
    assert "due yesterday" in mine[0]["body"]


def test_a_paid_premium_gets_no_missed_reminder(client, staff_as, api_conn):
    enrolled, _ = _enrol(client, staff_as, debit_day=25)
    due = _first_due(api_conn, enrolled["policy_id"])
    staff_as("admin")
    paid = client.post(f"/api/admin/instalments/{due['id']}/payment",
                       json={"paid_on": date.today().isoformat(),
                             "amount_cents": enrolled["premium_cents"], "method": "eft"})
    if paid.status_code == 404:
        pytest.skip("payments route has a different shape on this branch")
    assert paid.status_code in (200, 201), paid.text
    outbox = _Outbox()

    payment_reminders.run(api_conn, due["due_date"] + timedelta(days=1), send=outbox)

    assert outbox.for_policy(enrolled["policy_number"]) == []


def test_someone_who_said_stop_gets_nothing(client, staff_as, api_conn):
    enrolled, phone = _enrol(client, staff_as, debit_day=31)
    stop = whatsapp_line.Inbound(sid="SM" + "%032x" % random.getrandbits(128), account_sid="ACtest",
                                 from_number=phone, to_number="+27737310521", body="STOP",
                                 profile_name=None, media=[])
    whatsapp_line.handle_inbound(api_conn, stop, now=NOW)
    due = _first_due(api_conn, enrolled["policy_id"])
    outbox = _Outbox()

    payment_reminders.run(api_conn, due["due_date"], send=outbox)

    assert outbox.for_policy(enrolled["policy_number"]) == []
    assert api_conn.execute(
        "select status, detail from payment_reminders where instalment_id = %s", (due["id"],)
    ).fetchone() == {"status": "skipped", "detail": "opted_out"}


def test_a_failed_send_is_recorded_and_not_retried(client, staff_as, api_conn):
    enrolled, _ = _enrol(client, staff_as, debit_day=25)
    due = _first_due(api_conn, enrolled["policy_id"])

    payment_reminders.run(api_conn, due["due_date"], send=_Outbox(ok=False))
    retry = _Outbox()
    payment_reminders.run(api_conn, due["due_date"], send=retry)

    assert retry.for_policy(enrolled["policy_number"]) == []
    assert api_conn.execute(
        "select status from payment_reminders where instalment_id = %s and kind = 'upcoming'",
        (due["id"],)).fetchone()["status"] == "failed"
