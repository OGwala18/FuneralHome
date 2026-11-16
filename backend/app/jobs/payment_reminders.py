"""Send today's WhatsApp payment reminders (the payment day, and the day after).

    cd backend && python -m app.jobs.payment_reminders            # today (SAST)
    cd backend && python -m app.jobs.payment_reminders 2026-12-25 # a given day

Run once a day, in the morning (the Railway `jobs` cron runs it through
app/jobs/daily.py on the days in REMINDER_DAYS). It refuses, claiming nothing,
until WhatsApp and the approved templates are configured (not_ready). Safe to run again: every reminder is claimed
in payment_reminders before it is sent, so nothing goes out twice
(app/services/payment_reminders.py).

Prints counts only. No names, numbers or amounts reach the output.
"""

from __future__ import annotations

import sys
from datetime import date, datetime

from dotenv import load_dotenv

# Before app.config is imported: it reads the environment once, at import.
load_dotenv()

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from ..config import get_settings  # noqa: E402
from ..services import payment_reminders  # noqa: E402
from ..services.whatsapp_content import SAST  # noqa: E402


def main() -> int:
    today = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(SAST).date()
    missing = payment_reminders.not_ready(get_settings())
    if missing:
        # Claim nothing: a claimed reminder that fails is never sent again.
        print(f"Payment reminders for {today} not sent; WhatsApp is not ready: "
              + ", ".join(missing) + ". Nothing was claimed.")
        return 0
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
        counts = payment_reminders.run(conn, today)
    print(f"Payment reminders for {today}: {counts or 'none due'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
