"""WhatsApp payment reminders: on the payment day, and the day after if unpaid.

The owner, 11 Nov 2026. A family pays on the 1st, the 25th or the 30th (their
payment day, policy_payments.debit_day). On that day every premium still unpaid
gets a reminder with our bank details and the policy number as the reference;
the day after, one still unpaid gets one more ("we haven't received it"). So
the 1st -> the 2nd, the 25th -> the 26th, the 30th -> the 31st (or the 1st of
the next month when the month has 30 days).

RULES
- Once each: a payment_reminders row is written as 'pending' BEFORE sending,
  under a unique (instalment, kind) index (migration 0022). A rerun sends
  nothing twice, even after a failed send.
- Never to someone who replied STOP on the WhatsApp line.
- Only to the policy's MAIN member, on their primary phone.
- Nothing personal in the logs: counts and outcomes only.

Outside a 24-hour conversation, WhatsApp only delivers a business-initiated
message as an approved template (TWILIO_PAYMENT_DUE_SID / _MISSED_SID). Without
one, the plain text below goes out, which only works in the sandbox or inside
an open conversation, exactly like the registration confirmation.
"""

from __future__ import annotations

import collections
import logging
from datetime import date, timedelta
from typing import Any, Callable

from . import banking, whatsapp

logger = logging.getLogger(__name__)

KINDS = ("due", "missed")
# The names 0013 gave these kinds in payment_reminders.
TABLE_KIND = {"due": "upcoming", "missed": "overdue"}


def money(cents: int, currency: str = "ZAR") -> str:
    return f"R{cents // 100:,}.{cents % 100:02d}".replace(",", " ") if currency == "ZAR" \
        else f"{currency} {cents / 100:.2f}"


def reminder_text(kind: str, *, first_name: str, amount_cents: int, currency: str,
                  policy_number: str) -> str:
    """The plain-text message. The approved templates carry the same words."""
    amount = money(amount_cents, currency)
    name = (first_name or "").split(" ")[0] or "there"
    if kind == "due":
        head = (f"Hello {name}, your Induduzo premium of {amount} for policy "
                f"{policy_number} is due today.")
        tail = "Already paid? Thank you, please ignore this message."
    else:
        head = (f"Hello {name}, we haven't yet received your Induduzo premium of {amount} "
                f"for policy {policy_number}, which was due yesterday. Please pay as soon "
                "as you can so your cover stays in place.")
        tail = "Already paid? Thank you: the proof of payment is all we need."
    return (
        f"{head}\n\n"
        "Please pay into our official account:\n"
        f"{banking.details_block(policy_number)}\n\n"
        f"Send your proof of payment here, or to {banking.PROOF_OF_PAYMENT_EMAIL}. {tail}\n\n"
        "Received different banking details? Don't pay. Contact us first.\n"
        "Reply STOP to stop these messages."
    )


def candidates(conn: Any, due_on: date) -> list[dict]:
    """Unpaid instalments due on `due_on`, with whom to remind and where."""
    return conn.execute(
        """
        select i.id as instalment_id, i.amount_cents, i.currency, p.policy_number,
               pe.id as person_id, pe.first_names, ph.number,
               c.id as conversation_id, c.opted_out_at
          from premium_instalments i
          join policies p on p.id = i.policy_id
          join policy_members pm on pm.policy_id = p.id
               and pm.member_type = 'main_member'
               and pm.archived_at is null and pm.left_at is null
          join people pe on pe.id = pm.person_id
          left join lateral (
                select number from person_phones
                 where person_id = pe.id and archived_at is null
                 order by is_primary desc, created_at desc
                 limit 1) ph on true
          left join whatsapp_conversations c on c.other_number = ph.number
         where i.archived_at is null
           and i.status = 'due'
           and i.due_date = %s
           and p.archived_at is null
           and p.status_code in ('pending', 'active')
         order by p.policy_number
        """,
        (due_on,),
    ).fetchall()


def _claim(conn: Any, row: dict, kind: str) -> Any:
    """Write the row first. None means another run already has this reminder."""
    claimed = conn.execute(
        """
        insert into payment_reminders (instalment_id, kind, channel, status)
        values (%s, %s, 'whatsapp', 'pending')
        on conflict (instalment_id, kind) do nothing
        returning id
        """,
        (row["instalment_id"], TABLE_KIND[kind]),
    ).fetchone()
    return claimed["id"] if claimed else None


def _finish(conn: Any, reminder_id: Any, status: str, detail: str | None = None,
            sid: str | None = None) -> None:
    conn.execute(
        """
        update payment_reminders
           set status = %s, detail = %s, provider_reference = %s,
               sent_at = case when %s = 'sent' then now() end
         where id = %s
        """,
        (status, (detail or None) and detail[:60], sid, status, reminder_id),
    )


def run(conn: Any, today: date,
        send: Callable[..., whatsapp.WhatsAppResult] | None = None) -> dict[str, int]:
    """Send today's reminders. Returns outcome counts. Safe to run repeatedly.

    Each reminder is claimed and committed before it is sent, so a crash
    mid-run never leads to a second message.
    """
    from .whatsapp_line import record_outbound  # avoids an import cycle

    send = send or whatsapp.send_payment_reminder
    counts: collections.Counter[str] = collections.Counter()
    for kind, due_on in (("due", today), ("missed", today - timedelta(days=1))):
        for row in candidates(conn, due_on):
            reminder_id = _claim(conn, row, kind)
            conn.commit()
            if reminder_id is None:
                counts["already_done"] += 1
                continue
            if not row["number"]:
                _finish(conn, reminder_id, "skipped", "no_phone")
                counts["no_phone"] += 1
            elif row["opted_out_at"] is not None:
                _finish(conn, reminder_id, "skipped", "opted_out")
                counts["opted_out"] += 1
            else:
                body = reminder_text(kind, first_name=row["first_names"],
                                     amount_cents=row["amount_cents"],
                                     currency=row["currency"],
                                     policy_number=row["policy_number"])
                result = send(kind=kind, to_mobile=row["number"], body=body,
                              first_name=(row["first_names"] or "").split(" ")[0],
                              amount=money(row["amount_cents"], row["currency"]),
                              policy_number=row["policy_number"])
                record_outbound(conn, conversation_id=row["conversation_id"],
                                to_number=row["number"], body=body, author="system",
                                result=result, node=f"payment_{kind}")
                if result.sent:
                    _finish(conn, reminder_id, "sent", sid=result.message_sid)
                else:
                    _finish(conn, reminder_id, "failed", result.error or "not_sent")
                counts[f"{kind}_{'sent' if result.sent else 'failed'}"] += 1
            conn.commit()
    logger.info("Payment reminders for %s: %s", today, dict(counts))
    return dict(counts)
