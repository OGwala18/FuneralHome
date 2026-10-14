"""The premium schedule: one row per expected payment.

Generation only ever looks forward. It starts at today (or a later entry date)
and keeps MONTHS_AHEAD instalments ahead of today, so running it again tomorrow
adds at most the next month and never back-fills years of fictitious arrears for
a policy that came in by import with no payment history.

Re-running is harmless: the unique index on (policy_id, due_date) turns a
second insert of the same month into a no-op. That is what lets the roll-forward
job (app/jobs/schedule_instalments.py) run on any schedule, or by hand.

Nothing here touches bank or card details. Recording that a premium was paid is
the office's book-keeping; collecting it is the payment provider's job.
"""

from __future__ import annotations

import calendar
import json
from datetime import date
from typing import Any

MONTHS_AHEAD = 12

# Policy states that still owe premiums. 'lapsed' is not terminal (it can be
# reinstated), but it does not accrue new instalments while lapsed.
_LIVE_STATUSES = ("pending", "active")


def _on_day(year: int, month: int, day: int) -> date:
    """The debit day in that month, clamped: day 31 in February is the 28th or 29th."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def due_dates(start: date, debit_day: int | None, frequency: str, count: int) -> list[date]:
    """The next `count` due dates on or after `start`.

    No debit day (cash, EFT) means the day of the month the policy started.
    A once-off premium is a single payment on `start`.
    """
    if frequency == "once_off":
        return [start]

    day = debit_day or start.day
    year, month = start.year, start.month
    if _on_day(year, month, day) < start:
        year, month = _next_month(year, month)

    dates = []
    for _ in range(count):
        dates.append(_on_day(year, month, day))
        year, month = _next_month(year, month)
    return dates


def generate(conn: Any, policy_id: str, *, ahead: int = MONTHS_AHEAD,
             today: date | None = None) -> int:
    """Make sure the policy has `ahead` instalments scheduled. Returns rows added.

    Runs inside the caller's transaction. A policy with no premium recorded has
    nothing to schedule and is skipped rather than given R0.00 instalments.
    """
    today = today or date.today()
    row = conn.execute(
        """
        select p.premium_cents, p.currency, p.entry_date, p.status_code,
               pay.debit_day,
               coalesce(pay.frequency::text, 'monthly') as frequency,
               exists (select 1 from premium_instalments i
                        where i.policy_id = p.id and i.archived_at is null) as has_any
          from policies p
          left join policy_payments pay
            on pay.policy_id = p.id and pay.is_active and pay.archived_at is null
         where p.id = %s and p.archived_at is null
        """,
        (policy_id,),
    ).fetchone()

    if row is None or row["premium_cents"] is None:
        return 0
    if row["status_code"] not in _LIVE_STATUSES:
        return 0
    # A once-off premium is owed once. Re-running must not invent a second one
    # on whichever day the job happens to run.
    if row["frequency"] == "once_off" and row["has_any"]:
        return 0

    start = max(row["entry_date"] or today, today)
    added = 0
    for due in due_dates(start, row["debit_day"], row["frequency"], ahead):
        cursor = conn.execute(
            """
            insert into premium_instalments (policy_id, due_date, amount_cents, currency)
            values (%s, %s, %s, %s)
            on conflict (policy_id, due_date) where archived_at is null do nothing
            """,
            (policy_id, due, row["premium_cents"], row["currency"]),
        )
        added += cursor.rowcount
    return added


def generate_all(conn: Any, *, ahead: int = MONTHS_AHEAD, today: date | None = None) -> tuple[int, int]:
    """Roll every live policy forward. Returns (policies checked, rows added)."""
    ids = [
        r["id"]
        for r in conn.execute(
            "select id from policies where archived_at is null and status_code = any(%s)",
            (list(_LIVE_STATUSES),),
        ).fetchall()
    ]
    added = sum(generate(conn, str(policy_id), ahead=ahead, today=today) for policy_id in ids)
    return len(ids), added


_INSTALMENT_COLUMNS = """
    id, policy_id, due_date, amount_cents, currency, status, paid_at,
    paid_amount_cents, paid_method, recorded_by, notes
"""


def record_payment(conn: Any, instalment_id: str, *, paid_on: date, amount_cents: int,
                   method: str, notes: str | None, staff_email: str) -> dict | None:
    """Mark a due instalment paid. Returns the row, or None if it was not due.

    The first payment on a pending policy is what brings it into force, so the
    policy, and the enquiry it came from, move to active here.
    """
    row = conn.execute(
        f"""
        update premium_instalments
           set status = 'paid',
               paid_at = (%s::date)::timestamptz,
               paid_amount_cents = %s,
               paid_method = %s,
               recorded_by = %s,
               notes = coalesce(%s, notes)
         where id = %s and status = 'due' and archived_at is null
        returning {_INSTALMENT_COLUMNS}
        """,
        (paid_on, amount_cents, method, staff_email, notes, instalment_id),
    ).fetchone()
    if row is None:
        return None

    policy = conn.execute(
        """
        update policies set status_code = 'active'
         where id = %s and status_code = 'pending'
        returning id, enquiry_id
        """,
        (row["policy_id"],),
    ).fetchone()

    if policy is not None and policy["enquiry_id"] is not None:
        conn.execute(
            "update plan_enquiries set status = 'active' where id = %s and archived_at is null",
            (policy["enquiry_id"],),
        )
        conn.execute(
            """
            insert into enquiry_events (enquiry_id, event_type, actor, payload)
            values (%s, 'policy_activated', %s, %s::jsonb)
            """,
            (policy["enquiry_id"], staff_email, json.dumps({"first_due_date": row["due_date"].isoformat()})),
        )
    return row


def waive(conn: Any, instalment_id: str, *, reason: str, staff_email: str) -> dict | None:
    """Excuse a due instalment. Returns the row, or None if it was not due."""
    return conn.execute(
        f"""
        update premium_instalments
           set status = 'waived', recorded_by = %s, notes = %s
         where id = %s and status = 'due' and archived_at is null
        returning {_INSTALMENT_COLUMNS}
        """,
        (staff_email, reason, instalment_id),
    ).fetchone()
