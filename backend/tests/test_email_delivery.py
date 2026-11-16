"""Email, end to end through smtplib: what arrives, and every way it fails.

A failure here must never cost a lead (CLAUDE.md), so each failing case checks
three things: the enquiry is still saved, the failure is recorded on the
enquiry as a code from app/errors.py, and no personal data reached the log.
The 12 Nov 2026 production failure ("550 SMTP AUTH is required", login
variables missing on Railway) is the first case below.
"""

from __future__ import annotations

import dataclasses
import json
import random
import socket
import uuid

import pytest

from app.errors import describe
from app.schemas import valid_sa_id


def _lead(**overrides) -> dict:
    payload = {
        "first_name": "Mail",
        "surname": "Tester",
        "mobile_number": "082 000 0002",
        "plan_interest": "plan_b",
        "contact_consent": True,
    }
    payload.update(overrides)
    return payload


def _id_number() -> str:
    body = "%02d%02d%02d%04d08" % (random.randint(30, 49), random.randint(1, 12),
                                   random.randint(1, 28), random.randint(0, 9999))
    return next(body + str(d) for d in range(10) if valid_sa_id(body + str(d)))


def _events(db, enquiry_id: str, event_type: str) -> list[dict]:
    rows = db.execute(
        "select payload from enquiry_events where enquiry_id = %s and event_type = %s",
        (enquiry_id, event_type),
    ).fetchall()
    return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- What arrives ------------------------------------------------------------------

def test_a_lead_email_reaches_the_office_logged_in_and_threaded(client, db, smtp_sink):
    lead = client.post("/api/enquiries", json=_lead()).json()

    assert len(smtp_sink.received) == 1
    mail = smtp_sink.received[0]
    assert mail.login == smtp_sink.username
    assert mail.rcpt_to == ["office@induduzo.test"]
    message = mail.message
    # The office threads stage 1 and stage 2 by this header.
    assert message["X-Induduzo-Reference"] == lead["reference"]
    assert lead["reference"] in message.get_body(("plain",)).get_content()
    assert _events(db, lead["id"], "lead_email_sent") == [{"error": None, "smtp_status": None}]


def test_markup_typed_into_the_form_arrives_as_text_not_html(client, smtp_sink):
    client.post("/api/enquiries", json=_lead(how_heard='<img src=x onerror="alert(1)">'))

    html = smtp_sink.received[0].message.get_body(("html",)).get_content()
    assert "<img" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html


def test_a_full_application_sends_the_office_and_the_applicant_one_each(client, db, smtp_sink):
    lead = client.post("/api/enquiries", json=_lead(email="family@example.test")).json()
    smtp_sink.clear()

    response = client.patch(f"/api/enquiries/{lead['id']}/application", json={
        "id_number": _id_number(), "plan_selected": "plan_b", "terms_accepted": True,
        "notes": "Line one\nLine two & <b>three</b>"})

    assert response.status_code == 200
    by_recipient = {tuple(mail.rcpt_to): mail.message for mail in smtp_sink.received}
    assert set(by_recipient) == {("office@induduzo.test",), ("family@example.test",)}
    office_html = by_recipient[("office@induduzo.test",)].get_body(("html",)).get_content()
    assert "&lt;b&gt;three&lt;/b&gt;" in office_html
    for message in by_recipient.values():
        assert message["X-Induduzo-Reference"] == lead["reference"]


# --- Every way it fails ---------------------------------------------------------------

FAILURES = [
    # (sink mode, settings change, expected code, expected SMTP status)
    ("ok", {"smtp_username": None, "smtp_password": None}, "email_auth_required", 550),
    ("auth_required", {}, "email_auth_required", 550),
    ("auth_failed", {}, "email_auth_failed", 535),
    ("sender_refused", {}, "email_sender_refused", 553),
    ("reject_data", {}, "email_rejected", 554),
    ("drop", {}, "email_connect_failed", None),
    ("silent", {"smtp_timeout": 1}, "email_timeout", None),
    ("ok", {"smtp_port": "closed"}, "email_connect_failed", None),
]


@pytest.mark.parametrize("mode, change, code, smtp_status", FAILURES,
                         ids=[f"{f[2]}-{f[0]}" for f in FAILURES])
def test_a_mail_failure_keeps_the_lead_and_records_why(
    client, db, smtp_sink, caplog, mode, change, code, smtp_status
):
    smtp_sink.mode = mode
    if change.get("smtp_port") == "closed":
        # Windows takes up to ~2 s to refuse a localhost port; Linux, none.
        change = {"smtp_port": _free_port(), "smtp_timeout": 6}
    smtp_sink.settings = dataclasses.replace(smtp_sink.settings, **change)

    with caplog.at_level("INFO"):
        response = client.post("/api/enquiries", json=_lead(email="private@example.test"))

    assert response.status_code == 201, "a mail failure must never cost a lead"
    enquiry_id = response.json()["id"]
    assert db.execute("select count(*) from plan_enquiries where id = %s",
                      (enquiry_id,)).fetchone()[0] == 1
    assert _events(db, enquiry_id, "lead_email_failed") == [
        {"error": code, "smtp_status": smtp_status}]
    assert describe(code) is not None, f"{code} must be in app/errors.py CATALOG"
    assert code in caplog.text
    assert "private@example.test" not in caplog.text


def test_starttls_missing_on_the_server_is_a_tls_failure(client, db, smtp_sink, monkeypatch):
    smtp_sink.mode = "no_starttls"
    monkeypatch.setenv("SMTP_STARTTLS", "1")

    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]

    assert _events(db, enquiry_id, "lead_email_failed") == [
        {"error": "email_tls_failed", "smtp_status": None}]


def test_a_refused_applicant_address_is_never_logged_or_stored(client, db, smtp_sink, caplog):
    """A refusal quotes the address back; it used to be logged and stored as-is."""
    address = f"refused-{uuid.uuid4().hex[:8]}@example.test"
    lead = client.post("/api/enquiries", json=_lead(email=address)).json()
    smtp_sink.mode = "recipient_refused"

    with caplog.at_level("INFO"):
        client.patch(f"/api/enquiries/{lead['id']}/application", json={
            "id_number": _id_number(), "plan_selected": "plan_a", "terms_accepted": True})

    assert _events(db, lead["id"], "applicant_email_failed") == [
        {"error": "email_recipient_refused", "smtp_status": 550}]
    stored = db.execute("select payload::text from enquiry_events where enquiry_id = %s",
                        (lead["id"],)).fetchall()
    assert all(address not in row[0] for row in stored)
    assert address not in caplog.text


def test_no_mail_server_configured_is_recorded_not_raised(client, db):
    # conftest leaves SMTP_HOST blank: the laptop and test default.
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]

    assert _events(db, enquiry_id, "lead_email_failed") == [
        {"error": "email_not_configured", "smtp_status": None}]
