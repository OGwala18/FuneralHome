"""Bit 5: the emailed code (docs/feature-2-staff-two-factor.md §5, §9, §11B).

Real tokens, a frozen clock and a mailbox instead of SMTP, so each rule in "the
code's life" is checked exactly: five minutes, five tries, one send a minute,
five an hour, replaced by a newer code, bound to its session, and never logged.
"""

from __future__ import annotations

import json
import re

import pytest

from app.services import email as email_service
from app.services.email import EmailResult

SEND = "/api/admin/2fa/email/send"
VERIFY = "/api/admin/2fa/email/verify"


def _code_in(message) -> str:
    return re.search(r"\b(\d{6})\b", message.get_body(("plain",)).get_content()).group(1)


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


@pytest.fixture
def person(signed_in, clock, mailbox):
    """A signed-in admin with the second step enforced: (headers, staff_id, session_id)."""
    return signed_in("admin")


def _send(client, headers):
    return client.post(SEND, headers=headers)


def _verify(client, headers, challenge_id, code):
    return client.post(VERIFY, headers=headers,
                       json={"challenge_id": challenge_id, "code": code})


def test_sending_then_verifying_passes_and_opens_the_portal(client, db, person, mailbox):
    headers, staff_id, _ = person
    address = db.execute("select email from staff_users where id = %s", (staff_id,)).fetchone()[0]

    sent = _send(client, headers)
    assert sent.status_code == 200, sent.text
    assert len(mailbox) == 1
    message = mailbox[0]
    assert message["To"] == address
    assert message["Subject"] == "Your Induduzo sign-in code"
    assert not re.search(r"\d", message["Subject"])
    assert "http" not in message.get_body(("plain",)).get_content()
    assert sent.json()["email_hint"].endswith("@staff.test")

    assert client.get("/api/admin/me", headers=headers).status_code == 403
    verified = _verify(client, headers, sent.json()["challenge_id"], _code_in(message))
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified_by"] == "email_code"
    assert client.get("/api/admin/me", headers=headers).status_code == 200


def test_a_code_works_only_once(client, person, mailbox):
    headers, _, _ = person
    challenge = _send(client, headers).json()["challenge_id"]
    code = _code_in(mailbox[0])

    assert _verify(client, headers, challenge, code).status_code == 200
    again = _verify(client, headers, challenge, code)
    assert again.status_code == 400
    assert again.json()["code"] == "code_used_up"


def test_five_wrong_codes_kill_it_and_then_even_the_right_one_is_refused(client, person, mailbox):
    headers, _, _ = person
    challenge = _send(client, headers).json()["challenge_id"]
    code = _code_in(mailbox[0])

    for _ in range(5):
        wrong = _verify(client, headers, challenge, _wrong(code))
        assert wrong.status_code == 400
        assert wrong.json()["code"] == "code_wrong"

    dead = _verify(client, headers, challenge, code)
    assert dead.status_code == 400
    assert dead.json()["code"] == "code_used_up"


def test_after_five_minutes_it_is_refused_and_no_new_email_is_sent(client, person, mailbox, clock):
    headers, _, _ = person
    challenge = _send(client, headers).json()["challenge_id"]
    code = _code_in(mailbox[0])

    clock.advance(minutes=5)
    expired = _verify(client, headers, challenge, code)

    assert expired.status_code == 400
    assert expired.json()["code"] == "code_expired"
    assert len(mailbox) == 1


def test_a_resend_inside_60_seconds_is_429(client, person, mailbox, clock):
    headers, _, _ = person
    _send(client, headers)

    clock.advance(seconds=30)
    too_soon = _send(client, headers)
    assert too_soon.status_code == 429
    assert too_soon.json()["code"] == "resend_too_soon"
    assert int(too_soon.headers["retry-after"]) > 0
    assert len(mailbox) == 1

    clock.advance(seconds=31)
    assert _send(client, headers).status_code == 200


def test_the_sixth_code_in_an_hour_is_429(client, person, mailbox, clock):
    headers, _, _ = person
    for _ in range(5):
        assert _send(client, headers).status_code == 200
        clock.advance(seconds=61)

    sixth = _send(client, headers)
    assert sixth.status_code == 429
    assert sixth.json()["code"] == "resend_too_soon"
    assert len(mailbox) == 5

    clock.advance(hours=1)
    assert _send(client, headers).status_code == 200


def test_after_a_new_code_the_old_one_is_refused(client, person, mailbox, clock):
    headers, _, _ = person
    first = _send(client, headers).json()["challenge_id"]
    old_code = _code_in(mailbox[0])
    clock.advance(seconds=61)
    _send(client, headers)

    response = _verify(client, headers, first, old_code)

    assert response.status_code == 400
    assert response.json()["code"] == "code_expired"


def test_a_code_from_session_a_is_refused_in_session_b(client, db, signed_in, clock, mailbox):
    headers_a, staff_id, _ = signed_in("admin")
    address = db.execute("select email from staff_users where id = %s", (staff_id,)).fetchone()[0]
    headers_b, _, _ = signed_in("admin", email=address)

    challenge = _send(client, headers_a).json()["challenge_id"]
    response = _verify(client, headers_b, challenge, _code_in(mailbox[0]))

    assert response.status_code == 400
    assert response.json()["code"] == "code_wrong"
    assert client.get("/api/admin/me", headers=headers_b).status_code == 403


def test_another_persons_code_is_refused(client, signed_in, clock, mailbox):
    owner_headers, _, _ = signed_in("owner")
    other_headers, _, _ = signed_in("admin")

    challenge = _send(client, owner_headers).json()["challenge_id"]
    response = _verify(client, other_headers, challenge, _code_in(mailbox[0]))

    assert response.status_code == 400
    assert response.json()["code"] == "code_wrong"


def test_a_malformed_challenge_id_is_just_a_wrong_code(client, person):
    headers, _, _ = person
    response = _verify(client, headers, "not-a-uuid", "123456")
    assert response.status_code == 400
    assert response.json()["code"] == "code_wrong"


def test_ten_failures_lock_the_second_step_for_15_minutes(client, person, mailbox, clock):
    headers, _, _ = person
    challenge = _send(client, headers).json()["challenge_id"]
    code = _code_in(mailbox[0])

    statuses = [_verify(client, headers, challenge, _wrong(code)).status_code for _ in range(10)]
    assert statuses == [400] * 9 + [429]

    locked_send = _send(client, headers)
    assert locked_send.status_code == 429
    assert locked_send.json()["code"] == "too_many_attempts"

    clock.advance(minutes=15, seconds=1)
    fresh = _send(client, headers)
    assert fresh.status_code == 200
    assert _verify(client, headers, fresh.json()["challenge_id"],
                   _code_in(mailbox[-1])).status_code == 200


def test_a_failed_send_is_502_and_says_so(client, person, monkeypatch):
    headers, _, _ = person
    monkeypatch.setattr(email_service, "_send",
                        lambda _message: EmailResult(sent=False, error="smtp down"))

    response = _send(client, headers)

    assert response.status_code == 502
    assert response.json()["code"] == "email_send_failed"


def test_no_code_appears_in_logs_or_staff_events(client, db, person, mailbox, caplog):
    headers, staff_id, _ = person
    with caplog.at_level("DEBUG"):
        challenge = _send(client, headers).json()["challenge_id"]
        code = _code_in(mailbox[0])
        _verify(client, headers, challenge, _wrong(code))
        _verify(client, headers, challenge, code)

    assert code not in caplog.text
    assert _wrong(code) not in caplog.text
    payloads = [json.dumps(row[0]) for row in db.execute(
        "select payload from staff_events where subject = "
        "(select email from staff_users where id = %s)", (staff_id,))]
    assert payloads
    assert not any(code in p or _wrong(code) in p for p in payloads)


def test_every_step_is_audited(client, db, person, mailbox):
    headers, staff_id, _ = person
    challenge = _send(client, headers).json()["challenge_id"]
    code = _code_in(mailbox[0])
    _verify(client, headers, challenge, _wrong(code))
    _verify(client, headers, challenge, code)

    events = [row[0] for row in db.execute(
        "select event_type from staff_events where subject = "
        "(select email from staff_users where id = %s) order by created_at, id",
        (staff_id,))]
    assert events.count("2fa_code_sent") == 1
    assert events.count("2fa_failed") == 1
    assert events.count("2fa_passed") == 1


def test_sending_needs_a_signed_in_person(client):
    assert client.post(SEND).status_code == 401
