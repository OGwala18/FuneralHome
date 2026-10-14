"""Touch the database so a free-tier Supabase project is never paused.

    python db/keepalive.py                  # uses DATABASE_URL
    python db/keepalive.py --database-url postgresql://...
    python db/keepalive.py --quiet          # only speaks when something is wrong

WHY THIS EXISTS

Supabase pauses a free project after a stretch of inactivity. For most projects
that is a mild inconvenience. For this one it is an outage: Supabase Auth is how
the office signs in to the staff portal, so a quiet week means nobody can get in
until a human opens the Supabase dashboard and un-pauses it by hand.

The project is deliberately on the free tier — 50,000 monthly active users is
far beyond the handful of staff who will ever sign in, so the user limit was
never the constraint. Pausing is. This script removes that one risk and keeps
the R450/month that Pro would have cost.

HOW IT IS MEANT TO BE RUN

Nothing in this repository runs on a clock yet, and the API is not deployed
anywhere, so wiring a scheduler now would mean choosing infrastructure that does
not exist. This is therefore a plain command: idempotent, safe to run as often
as you like, and safe to run twice at the same moment.

When the backend is deployed, point something at it on a weekly-or-better
schedule — a Railway cron, a GitHub Actions `schedule:` trigger, or an uptime
monitor hitting an endpoint that calls the same query. Until then **somebody has
to run it, or open the Supabase dashboard, at least once a week.**

DESIGN NOTES

It reads DATABASE_URL directly and never imports `backend.app.config`. That is
deliberate. The Settings dataclass in that module resolves its `os.getenv(...)`
defaults once, at import time, so any entrypoint that imports it before calling
`load_dotenv()` silently receives None for everything. `db/migrate.py` sidesteps
the same trap the same way.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

try:
    import psycopg
except ImportError:  # pragma: no cover
    sys.exit("psycopg is required.  pip install 'psycopg[binary]'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Keep a free-tier Supabase project from pausing."
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print nothing on success; useful from a scheduler that mails output",
    )
    args = parser.parse_args()

    if not args.database_url:
        sys.exit("Set DATABASE_URL or pass --database-url.")

    started = datetime.now(timezone.utc)

    try:
        # A read is enough to count as activity, and a read cannot damage
        # anything if this is ever pointed at the wrong database by mistake.
        with psycopg.connect(args.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("select now()")
                (server_time,) = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - the reason matters more than the type
        # Loud on failure: a silent failure here is indistinguishable from
        # success right up until the morning nobody can sign in.
        print("KEEPALIVE FAILED: %s" % exc, file=sys.stderr)
        return 1

    if not args.quiet:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        print("Database reachable at %s (%.2fs)." % (server_time.isoformat(), elapsed))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
