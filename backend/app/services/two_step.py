"""Has this staff session passed the second step?

docs/feature-2-staff-two-factor.md §5. Supabase proves the password; this module
answers the next question, per Supabase session: did the person also pass a
second step, and until when? It only reads and records; the methods that
produce a pass (emailed code, app, passkey) arrive in later bits.

Every function takes `at`, the current time, from `now()` below and never from
the database's clock. The tests move `now()` to check the 12-hour limit and the
30-day trust without sleeping, and the rows' timestamps then agree with it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .two_step_crypto import hash_device_token

# Decision 4 (owner, 19 Oct 2026): a verified session is asked again after 12 hours.
SESSION_LIFETIME = timedelta(hours=12)

# "Recently" for sensitive actions (removing a method, new recovery codes):
# a real method, not a trusted computer, within this window.
RECENT_WINDOW = timedelta(minutes=15)

TRUSTED_DEVICE = "trusted_device"
METHODS = ("email_code", "authenticator_app", "passkey", "recovery_code", TRUSTED_DEVICE)


def now() -> datetime:
    """The one clock every two-step decision reads. Tests replace it."""
    return datetime.now(timezone.utc)


def record_verification(
    conn: Any, staff_id: str, session_id: str, method: str, at: datetime
) -> dict:
    """Record that this session passed, for SESSION_LIFETIME from `at`."""
    if method not in METHODS:
        raise ValueError("Unknown second-step method.")
    return conn.execute(
        """
        insert into staff_session_verifications
            (staff_user_id, session_id, method, verified_at, expires_at)
        values (%s, %s, %s, %s, %s)
        returning id, method, verified_at, expires_at
        """,
        (staff_id, session_id, method, at, at + SESSION_LIFETIME),
    ).fetchone()


def find_verification(conn: Any, staff_id: str, session_id: str, at: datetime) -> dict | None:
    """The latest pass for this session that is still good at `at`, if any."""
    return conn.execute(
        """
        select id, method, verified_at, expires_at
          from staff_session_verifications
         where session_id = %s
           and staff_user_id = %s
           and revoked_at is null
           and verified_at <= %s
           and expires_at > %s
         order by verified_at desc
         limit 1
        """,
        (session_id, staff_id, at, at),
    ).fetchone()


def find_trusted_device(conn: Any, staff_id: str, token: str | None, at: datetime) -> dict | None:
    """The trusted computer this token belongs to, if it is this person's and live.

    A token from another person, a forgotten computer or one past its 30 days
    matches nothing. Only the hash is compared; the token is never stored.
    """
    if not token:
        return None
    return conn.execute(
        """
        select id, label, created_at, expires_at
          from staff_trusted_devices
         where token_hash = %s
           and staff_user_id = %s
           and revoked_at is null
           and created_at <= %s
           and expires_at > %s
        """,
        (hash_device_token(token), staff_id, at, at),
    ).fetchone()


def methods_set_up(conn: Any, staff_id: str) -> dict:
    """What this person can use. The emailed code is always available (decision 1)."""
    row = conn.execute(
        """
        select
          (select count(*) from staff_totp_factors
            where staff_user_id = %(id)s and status = 'active')   as apps,
          (select count(*) from staff_passkeys
            where staff_user_id = %(id)s and removed_at is null)  as passkeys
        """,
        {"id": staff_id},
    ).fetchone()
    return {
        "email_code": True,
        "authenticator_app": row["apps"] > 0,
        "passkeys": row["passkeys"],
    }


def is_recent(method: str | None, verified_at: datetime | None, at: datetime) -> bool:
    """A real method passed within RECENT_WINDOW. A trusted computer never counts."""
    if method is None or method == TRUSTED_DEVICE or verified_at is None:
        return False
    return at - verified_at <= RECENT_WINDOW
