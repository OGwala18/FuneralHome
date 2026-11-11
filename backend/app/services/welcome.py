"""The welcome a new member gets once staff have enrolled them.

The owner, 11 Nov 2026: "You've been successfully added to the Induduzo family
and it's great to have you", with a link to leave a Google review. Sent on
WhatsApp to the main member's primary phone, and by email if they gave one.

A notification, so it runs after the enrolment has committed, in a background
task, and swallows its own failures: a mail or WhatsApp outage must never undo
or block an enrolment (CLAUDE.md). Nobody who replied STOP is messaged. Nothing
personal reaches the log, only the policy number.

GOOGLE_REVIEW_URL holds the review link. Without it the review sentence is left
out rather than pointing anywhere wrong.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings
from ..db import connection
from . import whatsapp
from .email import send_member_welcome
from .staff import log_staff_event

logger = logging.getLogger(__name__)


def welcome_text(*, first_name: str, policy_number: str, review_url: str | None) -> str:
    name = (first_name or "").split(" ")[0] or "there"
    text = (
        f"Hello {name}, you've been successfully added to the Induduzo family, and "
        f"it's great to have you.\n\n"
        f"Your policy number is {policy_number}. Please use it as the reference whenever "
        "you pay, and keep it somewhere safe. Reply \"pay\" at any time for our bank "
        "details.\n\n"
        "Your cover starts once your first premium is received, and a 3-month waiting "
        "period applies to natural causes."
    )
    if review_url:
        text += ("\n\nIf you have a moment, we'd be grateful for a Google review: "
                 f"{review_url}")
    return text


def _member(conn: Any, policy_id: str) -> dict | None:
    return conn.execute(
        """
        select p.policy_number, pe.first_names, pe.email, ph.number,
               c.id as conversation_id, c.opted_out_at
          from policies p
          join policy_members pm on pm.policy_id = p.id and pm.member_type = 'main_member'
               and pm.archived_at is null
          join people pe on pe.id = pm.person_id
          left join lateral (
                select number from person_phones
                 where person_id = pe.id and archived_at is null
                 order by is_primary desc, created_at desc limit 1) ph on true
          left join whatsapp_conversations c on c.other_number = ph.number
         where p.id = %s
        """,
        (policy_id,),
    ).fetchone()


def send(policy_id: str, staff_email: str = "system") -> dict[str, str]:
    """Send the welcome. Never raises. Returns what happened per channel."""
    from .whatsapp_line import record_outbound  # avoids an import cycle

    outcome = {"whatsapp": "not_tried", "email": "not_tried"}
    try:
        settings = get_settings()
        with connection() as conn:
            member = _member(conn, policy_id)
            if member is None:
                return outcome
            text = welcome_text(first_name=member["first_names"],
                                policy_number=member["policy_number"],
                                review_url=settings.google_review_url)

            if not member["number"]:
                outcome["whatsapp"] = "no_phone"
            elif member["opted_out_at"] is not None:
                outcome["whatsapp"] = "opted_out"
            else:
                result = whatsapp.send_welcome(
                    to_mobile=member["number"], body=text,
                    first_name=(member["first_names"] or "").split(" ")[0],
                    policy_number=member["policy_number"])
                record_outbound(conn, conversation_id=member["conversation_id"],
                                to_number=member["number"], body=text, author="system",
                                result=result, node="welcome")
                outcome["whatsapp"] = "sent" if result.sent else (result.error or "not_sent")

            if member["email"]:
                mail = send_member_welcome(to_email=member["email"],
                                           first_name=member["first_names"],
                                           policy_number=member["policy_number"],
                                           review_url=settings.google_review_url)
                outcome["email"] = "sent" if mail.sent else (mail.error or "not_sent")[:60]
            else:
                outcome["email"] = "no_email"

            log_staff_event(conn, staff_email, "welcome_sent", member["policy_number"],
                            {k: v[:60] for k, v in outcome.items()})
        logger.info("Welcome for %s: %s", member["policy_number"], outcome)
    except Exception:  # noqa: BLE001 - a welcome must never fail an enrolment
        logger.exception("Welcome message failed for a new policy")
    return outcome
