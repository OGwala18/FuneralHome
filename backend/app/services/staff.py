"""Staff account management.

Supabase Auth answers "who is this?". This module answers "what may they do?",
which is the question that actually matters for authorisation.

The bootstrap rule is deliberate: if the staff table is empty, the addresses in
STAFF_EMAILS are provisioned as owners on first sign-in. Without it, a fresh
deployment would have a staff table nobody could add themselves to — a locked
door with the key inside.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from ..config import get_settings

logger = logging.getLogger(__name__)

Role = Literal["viewer", "admin", "owner"]

# Ordered least to most privileged. Comparing positions is how permission checks
# are expressed, so adding a tier later means editing this list and nothing else.
ROLE_ORDER: list[Role] = ["viewer", "admin", "owner"]


def role_at_least(role: str, minimum: Role) -> bool:
    try:
        return ROLE_ORDER.index(role) >= ROLE_ORDER.index(minimum)
    except ValueError:
        # An unknown role is never privileged.
        return False


def log_staff_event(
    conn: Any, actor_email: str, event_type: str, subject: str | None = None,
    payload: dict | None = None,
) -> None:
    """Append to the staff audit trail, inside the caller's transaction."""
    conn.execute(
        """
        insert into staff_events (actor_email, event_type, subject, payload)
        values (%s, %s, %s, %s::jsonb)
        """,
        (actor_email, event_type, subject, json.dumps(payload or {})),
    )


def find_by_email(conn: Any, email: str) -> dict | None:
    return conn.execute(
        """
        select id, email, full_name, role::text as role, is_active,
               supabase_user_id, invited_by, last_seen_at, created_at
          from staff_users
         where lower(email) = lower(%s)
           and archived_at is null
        """,
        (email,),
    ).fetchone()


def count_active(conn: Any) -> int:
    return conn.execute(
        "select count(*) as n from staff_users where archived_at is null"
    ).fetchone()["n"]


def resolve_or_bootstrap(conn: Any, email: str, supabase_user_id: str) -> dict | None:
    """Return the staff record for a verified identity, provisioning the first
    owners if the table is still empty.

    Returns None when the person is not staff at all.
    """
    settings = get_settings()
    record = find_by_email(conn, email)

    if record is None:
        # Only the configured bootstrap addresses may self-provision, and only
        # while no staff exist. After that, access is by invitation.
        if email.lower() in settings.staff_emails and count_active(conn) == 0:
            record = conn.execute(
                """
                insert into staff_users (email, role, is_active, supabase_user_id, invited_by)
                values (%s, 'owner', true, %s, 'bootstrap')
                returning id, email, full_name, role::text as role, is_active,
                          supabase_user_id, invited_by, last_seen_at, created_at
                """,
                (email.lower(), supabase_user_id),
            ).fetchone()
            log_staff_event(
                conn, email, "staff_bootstrapped", email, {"role": "owner"}
            )
            logger.info("Bootstrapped first owner account")
        else:
            return None

    if not record["is_active"]:
        return record  # caller turns this into a 403; the row is still returned

    # Record the sighting and bind the Supabase identity on first use.
    conn.execute(
        """
        update staff_users
           set last_seen_at = now(),
               supabase_user_id = coalesce(supabase_user_id, %s)
         where id = %s
        """,
        (supabase_user_id, record["id"]),
    )
    return record


def list_staff(conn: Any) -> list[dict]:
    return conn.execute(
        """
        select id, email, full_name, role::text as role, is_active,
               supabase_user_id is not null as has_signed_in,
               invited_by, last_seen_at, created_at
          from staff_users
         where archived_at is null
         order by array_position(array['owner','admin','viewer']::text[], role::text),
                  lower(email)
        """
    ).fetchall()
