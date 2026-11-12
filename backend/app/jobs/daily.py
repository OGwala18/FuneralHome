"""Every scheduled job, once a day. The Railway `jobs` cron service runs this.

    python -m backend.app.jobs.daily        # in the API image (Railway)
    cd backend && python -m app.jobs.daily  # locally

Railway's cron is in UTC; the schedule is `0 6 * * *`, 08:00 in South Africa,
so a reminder never reaches a family at night.

WHAT IT RUNS
1. The backup (db/backup.py), every day. Supabase's free tier keeps none.
   Needs DATABASE_OWNER_URL and a volume at BACKUP_DIR (default /backups).
   It also counts as activity, so the free project is never paused for being
   idle; db/keepalive.py is no longer something a person has to remember.
2. The premium schedule (schedule_instalments), every day. Forward-only and
   idempotent, so a daily run only adds what a new policy or a new month needs.
3. Payment reminders (payment_reminders), only on the days of the month in
   REMINDER_DAYS (default "25", the owner's choice on 13 Nov 2026). That job
   refuses, claiming nothing, until WhatsApp and its approved templates are
   configured, so running it early costs no reminder.

One step failing never stops the next. The run exits 1 if any step failed, so
Railway shows the run as failed and the owner can look.

Prints only step names, counts and error TYPES: never a row, a name, a number,
or an exception message (a connection error can carry the host).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Before app.config is imported: it reads the environment once, at import.
load_dotenv()

from ..services.whatsapp_content import SAST  # noqa: E402
from . import payment_reminders, schedule_instalments  # noqa: E402

# backend/app/jobs/daily.py -> the repository (or image) root.
ROOT = Path(__file__).resolve().parents[3]


def reminder_days() -> set[int]:
    raw = os.getenv("REMINDER_DAYS", "25")
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def backup() -> int:
    # A separate process: backup.py reads its own variables and never imports
    # app.config, and its output stays its own.
    return subprocess.run([sys.executable, str(ROOT / "db" / "backup.py")], check=False).returncode


def main() -> int:
    today = datetime.now(SAST).date()
    steps = [("backup", backup), ("premium schedule", schedule_instalments.main)]
    if today.day in reminder_days():
        steps.append(("payment reminders", payment_reminders.main))

    failed = []
    for name, step in steps:
        try:
            code = step()
        except Exception as exc:  # noqa: BLE001 - one failure must not stop the rest
            print(f"{name}: failed ({type(exc).__name__})")
            code = 1
        if code:
            failed.append(name)
        sys.stdout.flush()

    print(f"Daily jobs for {today}: " + (f"failed: {', '.join(failed)}" if failed else "all done"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
