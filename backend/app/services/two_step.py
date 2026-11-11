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


# --- Emailed code (Bit 5; plan §5 "the code's life", §9) --------------------------

CODE_LIFETIME = timedelta(minutes=5)
RESEND_GAP = timedelta(seconds=60)
SENDS_PER_HOUR = 5
ATTEMPTS_PER_CODE = 5

# Across every method: this many wrong answers inside the window locks the
# person out of the second step until the window has passed (plan §8).
LOCK_FAILURES = 10
LOCK_WINDOW = timedelta(minutes=15)


def log_event(conn: Any, actor_email: str, event_type: str, subject: str,
              at: datetime, payload: dict | None = None) -> None:
    """A staff_events row stamped from the two-step clock.

    Payloads never hold a code, a secret, a device token or an IP address
    (ARCHITECTURE.md rule 9); only the method and a reason word.
    """
    import json

    conn.execute(
        """
        insert into staff_events (actor_email, event_type, subject, payload, created_at)
        values (%s, %s, %s, %s::jsonb, %s)
        """,
        (actor_email, event_type, subject, json.dumps(payload or {}), at),
    )


def locked_for(conn: Any, email: str, at: datetime) -> int:
    """Seconds until this person may try the second step again; 0 if not locked.

    Counted from staff_events, so there is no lockout flag to get stuck.
    """
    rows = conn.execute(
        """
        select created_at from staff_events
         where subject = %s
           and event_type = '2fa_failed'
           and created_at > %s
           and created_at <= %s
         order by created_at desc
         limit %s
        """,
        (email, at - LOCK_WINDOW, at, LOCK_FAILURES),
    ).fetchall()
    if len(rows) < LOCK_FAILURES:
        return 0
    # Locked until the oldest of the last ten failures leaves the window.
    oldest = rows[-1]["created_at"]
    return max(int((oldest + LOCK_WINDOW - at).total_seconds()) + 1, 1)


def record_failure(conn: Any, email: str, method: str, reason: str, at: datetime) -> bool:
    """Log a wrong answer. Returns True when this failure is the one that locks."""
    log_event(conn, email, "2fa_failed", email, at, {"method": method, "reason": reason})
    if locked_for(conn, email, at):
        log_event(conn, email, "2fa_locked", email, at, {"minutes": 15})
        return True
    return False


def resend_wait(conn: Any, staff_id: str, at: datetime) -> int:
    """Seconds before another code may be sent; 0 if one may go now."""
    rows = conn.execute(
        """
        select created_at from staff_mfa_challenges
         where staff_user_id = %s
           and kind = 'email_code'
           and created_at > %s
           and created_at <= %s
         order by created_at desc
        """,
        (staff_id, at - timedelta(hours=1), at),
    ).fetchall()
    if not rows:
        return 0
    waits = [int((rows[0]["created_at"] + RESEND_GAP - at).total_seconds()) + 1]
    if len(rows) >= SENDS_PER_HOUR:
        waits.append(int((rows[SENDS_PER_HOUR - 1]["created_at"] + timedelta(hours=1) - at)
                         .total_seconds()) + 1)
    wait = max(waits)
    return wait if wait > 0 else 0


def issue_email_code(conn: Any, staff_id: str, session_id: str, code_hash_for, at: datetime
                     ) -> tuple[str, datetime]:
    """Replace any live code with a new one. Returns (challenge_id, expires_at).

    `code_hash_for(challenge_id)` hashes the new code against its own id, so the
    same six digits never hash the same way twice.
    """
    import uuid as _uuid

    conn.execute(
        """
        update staff_mfa_challenges
           set replaced_at = %s
         where staff_user_id = %s
           and kind = 'email_code'
           and used_at is null
           and replaced_at is null
        """,
        (at, staff_id),
    )
    challenge_id = str(_uuid.uuid4())
    expires_at = at + CODE_LIFETIME
    conn.execute(
        """
        insert into staff_mfa_challenges
            (id, staff_user_id, session_id, kind, code_hash, created_at, expires_at)
        values (%s, %s, %s, 'email_code', %s, %s, %s)
        """,
        (challenge_id, staff_id, session_id, code_hash_for(challenge_id), at, expires_at),
    )
    return challenge_id, expires_at


def why_dead(challenge: dict, at: datetime) -> str | None:
    """None if the code can still be tried, else the error code to give.

    Worked out from the clock and the row every time; nothing stores "expired".
    """
    if challenge["used_at"] is not None or challenge["attempts"] >= ATTEMPTS_PER_CODE:
        return "code_used_up"
    if challenge["replaced_at"] is not None or at >= challenge["expires_at"]:
        return "code_expired"
    return None
