"""Bit 6: trusted computers (docs/feature-2-staff-two-factor.md §5, §9, §11B).

Ticking "Trust this computer for 30 days" returns a token once. A NEW sign-in
on that computer then skips the second step; a different computer, day 31, a
forgotten computer or another person's token does not.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

import pytest

SEND = "/api/admin/2fa/email/send"
VERIFY = "/api/admin/2fa/email/verify"
CHROME_ON_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def _code_in(message) -> str:
    return re.search(r"\b(\d{6})\b", message.get_body(("plain",)).get_content()).group(1)


def _pass(client, headers, mailbox, trust: bool):
    challenge = client.post(SEND, headers=headers).json()["challenge_id"]
    return client.post(
        VERIFY,
        headers={**headers, "User-Agent": CHROME_ON_WINDOWS},
        json={"challenge_id": challenge, "code": _code_in(mailbox[-1]), "trust_device": trust},
    )


@pytest.fixture
def trusted(client, db, signed_in, clock, mailbox):
    """A person who passed with the trust box ticked: (email, token, staff_id)."""
    headers, staff_id, _ = signed_in("admin")
    response = _pass(client, headers, mailbox, trust=True)
    assert response.status_code == 200, response.text
    email = db.execute("select email from staff_users where id = %s", (staff_id,)).fetchone()[0]
    return email, response.json()["device_token"], staff_id


def test_trust_unticked_returns_no_token(client, signed_in, clock, mailbox):
    headers, _, _ = signed_in("admin")
    body = _pass(client, headers, mailbox, trust=False).json()
    assert body["device_token"] is None
    assert body["trusted_until"] is None


def test_ticking_trust_returns_a_token_for_30_days(client, db, trusted, clock):
    _, token, staff_id = trusted
    expires_at, label, token_hash = db.execute(
        "select expires_at, label, token_hash from staff_trusted_devices "
        "where staff_user_id = %s", (staff_id,)
    ).fetchone()
    assert expires_at == clock() + timedelta(days=30)
    assert label == "Chrome on Windows"
    # Only the SHA-256 of the token is stored, never the token.
    assert bytes(token_hash) == hashlib.sha256(token.encode()).digest()
    assert token.encode() != bytes(token_hash)


def test_a_new_sign_in_on_a_trusted_computer_skips_the_second_step(client, signed_in, trusted):
    email, token, _ = trusted
    new_session, _, _ = signed_in("admin", email=email)

    assert client.get("/api/admin/me", headers=new_session).status_code == 403
    assert client.get(
        "/api/admin/me", headers={**new_session, "X-Induduzo-Device": token}
    ).status_code == 200


def test_trust_lasts_30_days_and_use_does_not_extend_it(client, signed_in, trusted, clock):
    email, token, _ = trusted
    headers = {**signed_in("admin", email=email)[0], "X-Induduzo-Device": token}

    clock.advance(days=29, hours=23)
    assert client.get("/api/admin/me", headers=headers).status_code == 200
    clock.advance(hours=1, seconds=1)
    assert client.get("/api/admin/me", headers=headers).status_code == 403


def test_a_forgotten_computer_is_asked_again(client, signed_in, trusted):
    email, token, _ = trusted
    headers = {**signed_in("admin", email=email)[0], "X-Induduzo-Device": token}

    listed = client.get("/api/admin/2fa/devices", headers=headers).json()
    assert len(listed) == 1 and listed[0]["this_computer"] is True

    forgot = client.post(f"/api/admin/2fa/devices/{listed[0]['id']}/forget", headers=headers)
    assert forgot.json() == {"forgotten": 1}
    assert client.get("/api/admin/me", headers=headers).status_code == 403


def test_you_cannot_forget_someone_elses_computer(client, signed_in, trusted, clock, mailbox):
    email, token, staff_id = trusted
    victim_device = client.get(
        "/api/admin/2fa/devices",
        headers={**signed_in("admin", email=email)[0], "X-Induduzo-Device": token},
    ).json()[0]["id"]

    attacker, _, _ = signed_in("admin")
    _pass(client, attacker, mailbox, trust=False)
    response = client.post(f"/api/admin/2fa/devices/{victim_device}/forget", headers=attacker)

    assert response.json() == {"forgotten": 0}
    assert client.get(
        "/api/admin/me",
        headers={**signed_in("admin", email=email)[0], "X-Induduzo-Device": token},
    ).status_code == 200


def test_forget_all_others_keeps_this_computer(client, db, signed_in, clock, mailbox):
    headers, staff_id, _ = signed_in("admin")
    email = db.execute("select email from staff_users where id = %s", (staff_id,)).fetchone()[0]
    first = _pass(client, headers, mailbox, trust=True).json()["device_token"]
    clock.advance(seconds=61)
    second_session, _, _ = signed_in("admin", email=email)
    second = _pass(client, second_session, mailbox, trust=True).json()["device_token"]

    on_second = {**signed_in("admin", email=email)[0], "X-Induduzo-Device": second}
    assert client.post("/api/admin/2fa/devices/forget-others",
                       headers=on_second).json() == {"forgotten": 1}

    assert client.get("/api/admin/me", headers=on_second).status_code == 200
    on_first = {**signed_in("admin", email=email)[0], "X-Induduzo-Device": first}
    assert client.get("/api/admin/me", headers=on_first).status_code == 403


def test_using_a_trusted_computer_records_when(client, db, signed_in, trusted, clock):
    email, token, staff_id = trusted
    clock.advance(days=2)
    client.get("/api/admin/me",
               headers={**signed_in("admin", email=email)[0], "X-Induduzo-Device": token})

    assert db.execute(
        "select last_used_at from staff_trusted_devices where staff_user_id = %s", (staff_id,)
    ).fetchone()[0] == clock()


def test_trusting_and_forgetting_are_audited_without_the_token(client, db, signed_in, trusted):
    email, token, _ = trusted
    headers = {**signed_in("admin", email=email)[0], "X-Induduzo-Device": token}
    device = client.get("/api/admin/2fa/devices", headers=headers).json()[0]["id"]
    client.post(f"/api/admin/2fa/devices/{device}/forget", headers=headers)

    rows = db.execute(
        "select event_type, payload::text from staff_events where subject = %s", (email,)
    ).fetchall()
    types = [r[0] for r in rows]
    assert "2fa_device_trusted" in types and "2fa_device_revoked" in types
    assert not any(token in r[1] for r in rows)
