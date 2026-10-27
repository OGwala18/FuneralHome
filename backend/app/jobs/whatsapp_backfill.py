"""The WhatsApp line's safety net. docs/feature-3-whatsapp-line.md §4.

    cd backend && python -m app.jobs.whatsapp_backfill            # locally
    python -m backend.app.jobs.whatsapp_backfill                  # in the API image
    python -m app.jobs.whatsapp_backfill --hours 24               # look further back

Two jobs in one:

1. Emails the office about any open escalation whose email didn't go, for
   example because the mail server was down. A family who asked for a person
   must reach one.
2. Asks Twilio for the messages families sent in the last few hours and stores
   any the webhook missed, for example while the API was restarting. Twilio
   doesn't retry a webhook that failed.

Safe to run as often as you like: a message already stored is skipped, and an
email that went is never sent twice. Nothing wires this to a clock yet
(CLAUDE.md, "Scheduler"); hourly is the intention.

Prints counts only. No names, numbers or message text reach the output.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# Before app.config is imported: it reads the environment once, at import.
load_dotenv()

from ..db import close_pool, init_pool  # noqa: E402
from ..services import whatsapp_line  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=int, default=6,
                        help="how far back to ask Twilio for missed messages (default 6)")
    args = parser.parse_args(argv)

    init_pool()
    try:
        tried, sent = whatsapp_line.retry_notifications()
        print(f"Escalation emails: {tried} waiting, {sent} sent now.")
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
        seen, stored = whatsapp_line.backfill(since)
        print(f"Twilio had {seen} messages from families in the last {args.hours} hours; "
              f"{stored} were missing and are now stored.")
    finally:
        close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
