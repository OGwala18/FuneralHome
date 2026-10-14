"""Roll every live policy's premium schedule forward to twelve months ahead.

    cd backend && python -m app.jobs.schedule_instalments          # locally
    python -m backend.app.jobs.schedule_instalments                # in the API image

Safe to run as often as you like: an instalment that already exists for a
policy and date is skipped, so a second run the same day adds nothing. Nothing
wires this to a clock yet (CLAUDE.md, "Scheduler"); once a month is plenty,
and the Railway cron that eventually runs it needs no other change.

Prints counts only. No names, numbers or amounts reach the output.
"""

from __future__ import annotations

from dotenv import load_dotenv

# Before app.config is imported: it reads the environment once, at import.
load_dotenv()

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from ..config import get_settings  # noqa: E402
from ..services import instalments  # noqa: E402


def main() -> int:
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
        checked, added = instalments.generate_all(conn)
    print(f"Checked {checked} live policies; scheduled {added} new instalments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
