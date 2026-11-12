"""Daily backup of the live member book, because Supabase's free tier keeps none.

    python db/backup.py

Reads DATABASE_OWNER_URL (the database owner's connection string) and
BACKUP_DIR (default /backups, a Railway volume). Writes every table in the
`public` schema as one gzip-compressed JSON file, named by UTC date, and keeps
the newest BACKUP_KEEP files (default 30).

WHY JSON AND NOT pg_dump
The API image has no PostgreSQL client tools, and a backup that needs a second
image is a backup nobody keeps running. Rows as JSON restore with a short
script, and the schema itself is in db/migrations.

WHAT IT NEVER DOES
Print a row, a name, a number or the connection string. Output is table names
and row counts.

The files hold personal information (ID numbers). They live only on the
private volume; never copy them into the repository.
"""

from __future__ import annotations

import datetime
import gzip
import json
import os
import sys
from pathlib import Path

import psycopg


def main() -> int:
    url = os.environ.get("DATABASE_OWNER_URL")
    if not url:
        print("DATABASE_OWNER_URL is not set.", file=sys.stderr)
        return 2
    folder = Path(os.environ.get("BACKUP_DIR", "/backups"))
    keep = int(os.environ.get("BACKUP_KEEP", "30"))
    folder.mkdir(parents=True, exist_ok=True)

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    target = folder / f"induduzo-{stamp}.json.gz"
    counts: dict[str, int] = {}

    with psycopg.connect(url) as conn, gzip.open(target, "wt", encoding="utf-8") as out:
        # Read everything as of one moment.
        conn.execute("set transaction isolation level repeatable read, read only")
        tables = [r[0] for r in conn.execute(
            "select tablename from pg_tables where schemaname = 'public' order by tablename")]
        out.write('{"taken_at": "%s", "tables": {' % stamp)
        for i, table in enumerate(tables):
            rows = conn.execute(
                f'select coalesce(json_agg(t), \'[]\'::json) from public."{table}" t'
            ).fetchone()[0]
            counts[table] = len(rows)
            out.write(("," if i else "") + json.dumps(table) + ":" + json.dumps(rows, default=str))
        out.write("}}")

    for old in sorted(folder.glob("induduzo-*.json.gz"))[:-keep]:
        old.unlink()

    print(f"Backup {target.name}: {len(counts)} tables, "
          f"{sum(counts.values())} rows; people={counts.get('people', 0)}, "
          f"policies={counts.get('policies', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
