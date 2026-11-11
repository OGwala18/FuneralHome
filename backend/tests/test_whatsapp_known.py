"""WHATSAPP_OUTBOUND=known: the owner's going-live rule (11 Nov 2026).

No fixed list of phones: a number a family gave us on the website form, or one
in the member book, may be messaged, and nobody else. A stranger who writes in
is kept for staff but gets no automatic reply.
"""

from __future__ import annotations

import dataclasses
import random
from datetime import datetime, timezone

import pytest

from app.config import get_settings
from app.services import whatsapp, whatsapp_line


def _number() -> tuple[str, str]:
    digits = "%07d" % random.randint(0, 9_999_999)
    return f"085 {digits[:3]} {digits[3:]}", f"+2785{digits}"


@pytest.fixture
def known_mode(monkeypatch):
    settings = dataclasses.replace(get_settings(), whatsapp_outbound="known",
                                   whatsapp_test_recipients=frozenset({"+27760000000"}))
    for module in (whatsapp, whatsapp_line):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    return settings


def test_known_is_a_valid_mode():
    assert dataclasses.replace(get_settings(), whatsapp_outbound="known").whatsapp_outbound == "known"


def test_a_number_from_the_website_form_may_be_messaged(client, known_mode):
    typed, stored = _number()
    response = client.post("/api/enquiries", json={
        "first_name": "Test", "surname": "Known", "mobile_number": typed,
        "plan_interest": "plan_a", "contact_consent": True})
    assert response.status_code == 201

    assert whatsapp.outbound_refusal(known_mode, stored) is None


def test_a_stranger_may_not_be(known_mode):
    _, stranger = _number()
    assert whatsapp.outbound_refusal(known_mode, stranger) == "whatsapp_unknown_number"


def test_the_staff_test_phones_still_may(known_mode):
    assert whatsapp.outbound_refusal(known_mode, "+27760000000") is None


def test_a_stranger_writing_in_is_kept_but_not_answered(db, known_mode):
    _, stranger = _number()
    message = whatsapp_line.Inbound(
        sid="SM" + "%032x" % random.getrandbits(128), account_sid="ACtest",
        from_number=stranger, to_number="+27737310521", body="hi",
        profile_name=None, media=[])

    import os, psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        delivery = whatsapp_line.handle_inbound(conn, message,
                                                now=datetime(2026, 11, 11, 9, tzinfo=timezone.utc))
        conn.commit()

    assert delivery.replies == []
    assert db.execute("select count(*) from whatsapp_messages where other_number = %s",
                      (stranger,)).fetchone()[0] == 1


def test_someone_who_applied_gets_the_menu(client, known_mode):
    typed, stored = _number()
    client.post("/api/enquiries", json={
        "first_name": "Test", "surname": "Known", "mobile_number": typed,
        "plan_interest": "plan_a", "contact_consent": True})
    message = whatsapp_line.Inbound(
        sid="SM" + "%032x" % random.getrandbits(128), account_sid="ACtest",
        from_number=stored, to_number="+27737310521", body="hi",
        profile_name=None, media=[])

    import os, psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        delivery = whatsapp_line.handle_inbound(conn, message,
                                                now=datetime(2026, 11, 11, 9, tzinfo=timezone.utc))
        conn.rollback()

    assert delivery.replies and "1." in delivery.replies[0][0]


# --- Business-started messages need a template outside the 24-hour window -------------

@pytest.fixture
def twilio_on(monkeypatch):
    settings = dataclasses.replace(
        get_settings(), whatsapp_outbound="on", twilio_account_sid="ACtest",
        twilio_auth_token="test", twilio_whatsapp_from="+27737310521",
        twilio_welcome_sid=None, twilio_payment_due_sid=None, twilio_payment_missed_sid=None)
    monkeypatch.setattr(whatsapp, "get_settings", lambda: settings)
    return settings


def test_a_welcome_without_a_template_is_not_sent_into_a_closed_window(twilio_on):
    # WhatsApp would silently refuse it (63016) after Twilio said "queued".
    result = whatsapp.send_welcome(to_mobile="+27760000000", body="hello",
                                   first_name="Test", policy_number="AA1", window_open=False)
    assert result.sent is False and result.error == "needs_template"


def test_a_reminder_without_a_template_is_not_either(twilio_on):
    result = whatsapp.send_payment_reminder(kind="due", to_mobile="+27760000000", body="x",
                                            first_name="Test", amount="R1.00",
                                            policy_number="AA1", window_open=False)
    assert result.error == "needs_template"
