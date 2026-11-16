"""A forgotten staff password: the emailed, one-use temporary password.

The owner's request (16 Nov 2026): "Forgot your password?" emails a temporary
password that works once; the person types it as the old password beside a new
one of their own, and is signed in with the new one.

How the pieces fit:

* The temporary password lives only here, as an HMAC keyed with
  TWO_STEP_CODE_PEPPER and bound to its row id (db/migrations/0029). It is never
  put into Supabase, so asking for one changes nothing about the person's real
  password, and a stranger typing someone's address locks nobody out.
* It lasts 30 minutes, survives five wrong tries, and a newer one replaces it.
* Only the right temporary password with an acceptable new password changes
  anything: the API then sets the new password in Supabase (service key) and
  stamps used_at, in the same transaction.

Every time comes from two_step.now(), the one clock the tests move.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from . import two_step
from .two_step_crypto import hash_code, hash_device_token, new_device_token

logger = logging.getLogger(__name__)

LIFETIME = timedelta(minutes=30)
ATTEMPTS = 5
# Per person: one email a minute and five an hour, like the sign-in codes.
SEND_GAP = timedelta(seconds=60)
SENDS_PER_HOUR = 5

# No 0/O, 1/I/L: a password read off a phone screen and typed on a PC. Twelve
# characters from 31 is about 59 bits, against five guesses before it dies.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 12
GROUP = 4

# What Supabase can store: it hashes with bcrypt, which reads 72 bytes.
MIN_PASSWORD = 12
MAX_PASSWORD_BYTES = 72


def new_temporary_password() -> str:
    """ABCD-EFGH-JKMN: twelve random characters in groups of four."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return "-".join(raw[i:i + GROUP] for i in range(0, LENGTH, GROUP))


def normalise(typed: str) -> str:
    """What was typed, as it is hashed: capitals, no spaces or dashes.

    So 'abcd efgh jkmn', 'ABCD-EFGH-JKMN' and 'abcdefghjkmn' are all the same.
    """
    return "".join(ch for ch in typed.upper() if ch not in " -\t\r\n")


def find_staff(conn: Any, email: str) -> dict | None:
    """The active, unarchived staff row for this address, if there is one."""
    return conn.execute(
        """
        select id, email, supabase_user_id
          from staff_users
         where lower(email) = lower(%s)
           and archived_at is null
           and is_active
        """,
        (email.strip(),),
    ).fetchone()


def send_wait(conn: Any, staff_id: str, at: datetime) -> int:
    """Seconds before another temporary password may be emailed; 0 if now."""
    rows = conn.execute(
        """
        select created_at from staff_password_resets
         where staff_user_id = %s
           and created_at > %s
           and created_at <= %s
         order by created_at desc
        """,
        (staff_id, at - timedelta(hours=1), at),
    ).fetchall()
    if not rows:
        return 0
    waits = [int((rows[0]["created_at"] + SEND_GAP - at).total_seconds()) + 1]
    if len(rows) >= SENDS_PER_HOUR:
        waits.append(int((rows[SENDS_PER_HOUR - 1]["created_at"] + timedelta(hours=1) - at)
                         .total_seconds()) + 1)
    return max(max(waits), 0)


def issue(conn: Any, staff_id: str, temporary: str, pepper: str | None,
          at: datetime) -> tuple[str, datetime]:
    """Replace any live temporary password with this one. Returns (id, expires_at)."""
    conn.execute(
        """
        update staff_password_resets
           set replaced_at = %s
         where staff_user_id = %s
           and used_at is null
           and replaced_at is null
        """,
        (at, staff_id),
    )
    reset_id = str(uuid.uuid4())
    expires_at = at + LIFETIME
    conn.execute(
        """
        insert into staff_password_resets
            (id, staff_user_id, temp_hash, created_at, expires_at)
        values (%s, %s, %s, %s, %s)
        """,
        (reset_id, staff_id, hash_code(pepper, reset_id, normalise(temporary)), at, expires_at),
    )
    return reset_id, expires_at


def live(conn: Any, staff_id: str, at: datetime) -> dict | None:
    """This person's temporary password that can still be tried, locked for
    this transaction so two tries at once cannot both count as the first."""
    return conn.execute(
        """
        select id, temp_hash, attempts, created_at, expires_at
          from staff_password_resets
         where staff_user_id = %s
           and used_at is null
           and replaced_at is null
           and attempts < %s
           and created_at <= %s
           and expires_at > %s
         order by created_at desc
         limit 1
         for update
        """,
        (staff_id, ATTEMPTS, at, at),
    ).fetchone()


def count_wrong(conn: Any, reset_id: str) -> None:
    conn.execute(
        "update staff_password_resets set attempts = attempts + 1 where id = %s",
        (reset_id,),
    )


def mark_used(conn: Any, reset_id: str, at: datetime) -> None:
    conn.execute(
        "update staff_password_resets set used_at = %s where id = %s",
        (at, reset_id),
    )


# --- The sign-in straight after a reset (0030) ---------------------------------
#
# The temporary password came from the same mailbox as the emailed sign-in code,
# so asking for a code straight after a reset asks twice for the same proof. A
# finished reset therefore gives the browser a one-time token; the sign-in that
# follows may spend it, once and within ten minutes, as its second step.

SECOND_STEP_WINDOW = timedelta(minutes=10)


def issue_second_step(conn: Any, reset_id: str) -> str | None:
    """A one-time token for the sign-in after this reset. Only its hash is kept.

    In its own savepoint: if the column is missing (the API deployed a moment
    before migration 0030), the reset still succeeds and the person simply gets
    the usual "Confirm it's you" screen.
    """
    token = new_device_token()
    try:
        with conn.transaction():
            conn.execute(
                "update staff_password_resets set second_step_hash = %s where id = %s",
                (hash_device_token(token), reset_id),
            )
    except Exception as exc:  # noqa: BLE001 - a missing shortcut, not a failure
        logger.warning("Reset second-step token not stored: %s", type(exc).__name__)
        return None
    return token


def spend_second_step(conn: Any, staff_id: str, token: str, at: datetime) -> bool:
    """True, once, for this person's token within ten minutes of their reset."""
    row = conn.execute(
        """
        select id from staff_password_resets
         where staff_user_id = %s
           and second_step_hash = %s
           and second_step_used_at is null
           and used_at is not null
           and used_at <= %s
           and used_at > %s
         for update
        """,
        (staff_id, hash_device_token(token), at, at - SECOND_STEP_WINDOW),
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        "update staff_password_resets set second_step_used_at = %s where id = %s",
        (at, row["id"]),
    )
    return True


def now() -> datetime:
    return two_step.now()
