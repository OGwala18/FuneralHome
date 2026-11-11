"""Bit 4: the second step is enforced on every staff route.

docs/feature-2-staff-two-factor.md §8 and §11B. The most important check here is
the guard test: every /api/admin route outside the 2FA allowlist refuses a
session that has passed the password but not the second step. A route added
later without protection fails CI.

Tokens are real ES256 tokens checked by the real dependencies (see the
signed_in fixture); only Supabase's key lookup is stubbed.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest

from app import main
from app.services import two_step
from app.services.two_step_crypto import hash_device_token, new_device_token

# Routes that must work BEFORE the second step: they are how a person gets past
# it. Everything else under /api/admin must refuse. Grow this list only with
# the 2FA endpoints that use require_staff_identity (plan §8, first table).
SECOND_STEP_ALLOWLIST = {
    ("GET", "/api/admin/2fa/status"),
}


def _admin_routes() -> list[tuple[str, str, str]]:
    """(method, template, concrete path) for every /api/admin route, from OpenAPI."""
    found = []
    for path, operations in main.app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            concrete = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
            found += [(method.upper(), path, concrete) for method in sorted(operations)]
    return found


def _guarded() -> list[tuple[str, str]]:
    return [(m, concrete) for m, template, concrete in _admin_routes()
            if (m, template) not in SECOND_STEP_ALLOWLIST]


def test_the_allowlist_names_real_routes():
    templates = {(m, t) for m, t, _ in _admin_routes()}
    assert SECOND_STEP_ALLOWLIST <= templates


def test_there_are_guarded_routes_to_check():
    assert len(_guarded()) >= 9


@pytest.mark.parametrize("method, path", _guarded())
def test_every_staff_route_refuses_a_session_without_the_second_step(
    client, signed_in, method, path
):
    headers, _, _ = signed_in("owner")

    response = client.request(method, path, json={}, headers=headers)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "second_step_required"


# --- Passing ---------------------------------------------------------------------

def test_a_verified_session_gets_in(client, db, signed_in, clock):
    headers, staff_id, session_id = signed_in("admin")
    two_step.record_verification(db, staff_id, session_id, "email_code", clock())

    response = client.get("/api/admin/me", headers=headers)

    assert response.status_code == 200, response.text


def test_a_verification_belongs_to_one_session(client, db, signed_in, clock):
    headers, staff_id, session_id = signed_in("admin")
    two_step.record_verification(db, staff_id, session_id, "email_code", clock())

    # The same person signing in again elsewhere is a new session: asked again.
    email = db.execute("select email from staff_users where id = %s", (staff_id,)).fetchone()[0]
    other_headers, same_person, _ = signed_in("admin", email=email)
    assert same_person == staff_id
    assert client.get("/api/admin/me", headers=other_headers).status_code == 403


def test_another_persons_verification_does_not_count(client, db, signed_in, clock):
    _, someone_else, shared_session = signed_in("admin")
    headers, _, _ = signed_in("admin", session_id=shared_session)
    two_step.record_verification(db, someone_else, shared_session, "email_code", clock())

    assert client.get("/api/admin/me", headers=headers).status_code == 403


def test_a_verified_session_expires_after_12_hours(client, db, signed_in, clock):
    headers, staff_id, session_id = signed_in("admin")
    two_step.record_verification(db, staff_id, session_id, "email_code", clock())

    clock.advance(hours=11, minutes=59)
    assert client.get("/api/admin/me", headers=headers).status_code == 200
    clock.advance(minutes=2)
    assert client.get("/api/admin/me", headers=headers).json()["code"] == "second_step_required"


def test_a_revoked_verification_no_longer_counts(client, db, signed_in, clock):
    headers, staff_id, session_id = signed_in("admin")
    row = two_step.record_verification(db, staff_id, session_id, "email_code", clock())
    db.execute("update staff_session_verifications set revoked_at = now() where id = %s",
               (row[0],))

    assert client.get("/api/admin/me", headers=headers).status_code == 403


# --- Trusted computers (the lookup; issuing tokens is Bit 6) -----------------------

def _trust(db, staff_id: str, at, days: int = 30) -> str:
    token = new_device_token()
    db.execute(
        """
        insert into staff_trusted_devices (staff_user_id, token_hash, label, created_at, expires_at)
        values (%s, %s, 'Test laptop', %s, %s)
        """,
        (staff_id, hash_device_token(token), at, at + timedelta(days=days)),
    )
    return token


def test_a_trusted_computer_skips_the_second_step(client, db, signed_in, clock):
    headers, staff_id, _ = signed_in("admin")
    token = _trust(db, staff_id, clock())

    response = client.get("/api/admin/me", headers={**headers, "X-Induduzo-Device": token})

    assert response.status_code == 200, response.text
    assert client.get("/api/admin/me", headers=headers).status_code == 403


def test_a_trusted_computer_stops_working_on_day_31(client, db, signed_in, clock):
    headers, staff_id, _ = signed_in("admin")
    token = _trust(db, staff_id, clock())

    clock.advance(days=30, seconds=1)

    response = client.get("/api/admin/me", headers={**headers, "X-Induduzo-Device": token})
    assert response.status_code == 403


def test_another_persons_trusted_computer_does_not_count(client, db, signed_in, clock):
    _, someone_else, _ = signed_in("admin")
    headers, _, _ = signed_in("admin")
    token = _trust(db, someone_else, clock())

    response = client.get("/api/admin/me", headers={**headers, "X-Induduzo-Device": token})
    assert response.status_code == 403


# --- The status route works before the second step ---------------------------------

def test_status_answers_before_the_second_step(client, signed_in):
    headers, _, _ = signed_in("viewer")

    response = client.get("/api/admin/2fa/status", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enforced"] is True
    assert body["session_verified"] is False
    assert body["methods"] == {"email_code": True, "authenticator_app": False, "passkeys": 0}
    assert "•••@staff.test" in body["email_hint"]


def test_status_reports_a_passed_session(client, db, signed_in, clock):
    headers, staff_id, session_id = signed_in("viewer")
    two_step.record_verification(db, staff_id, session_id, "passkey", clock())

    body = client.get("/api/admin/2fa/status", headers=headers).json()

    assert body["session_verified"] is True
    assert body["verified_by"] == "passkey"


def test_status_still_needs_a_token(client):
    assert client.get("/api/admin/2fa/status").status_code == 401


# --- Switches ----------------------------------------------------------------------

def test_with_enforcement_off_nothing_changes_for_staff(client, two_step, signed_in):
    two_step("off")
    headers, _, _ = signed_in("admin")

    assert client.get("/api/admin/me", headers=headers).status_code == 200


def test_enforcement_on_but_not_configured_is_503_never_open(client, two_step, signed_in):
    two_step("on", configured=False)
    headers, _, _ = signed_in("admin")

    response = client.get("/api/admin/me", headers=headers)

    assert response.status_code == 503
    assert response.json()["code"] == "two_step_not_configured"


def test_a_token_without_a_session_id_cannot_pass(client, signed_in):
    headers, _, _ = signed_in("admin", session_id="not-a-uuid")

    assert client.get("/api/admin/me", headers=headers).status_code == 403


def test_recent_means_a_real_method_within_15_minutes(clock):
    at = clock()
    assert two_step.is_recent("email_code", at - timedelta(minutes=14), at)
    assert not two_step.is_recent("email_code", at - timedelta(minutes=16), at)
    assert not two_step.is_recent("trusted_device", at, at)
