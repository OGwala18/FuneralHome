"""Apply database migrations to any Postgres.

Local Docker applies db/migrations automatically, but only once, on a fresh
volume. Managed Postgres (Supabase, Railway, RDS) never does. This runner is how
the schema reaches production.

    python db/migrate.py                    # apply anything outstanding
    python db/migrate.py --status           # show what is applied
    python db/migrate.py --dry-run          # show what WOULD run

Reads DATABASE_URL, or --database-url.

Design notes:

* Each file runs inside ONE transaction, and the record of it is written in the
  same transaction. A migration cannot half-apply and then be marked done.
* Applied files are checksummed. Editing a migration that has already run is an
  error, not a silent no-op, because production and local would silently diverge.
* `.sh` files are skipped. They exist for local Docker convenience only and
  managed hosts cannot execute them.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    sys.exit("psycopg is required.  pip install 'psycopg[binary]'")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

TRACKING_TABLE = """
create table if not exists schema_migrations (
    filename    text primary key,
    checksum    text        not null,
    applied_at  timestamptz not null default now(),
    applied_by  text        not null default current_user
)
"""


def checksum(text: str) -> str:
    # Newlines normalised so a checkout with different line endings does not
    # look like a modified migration.
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]


def discover() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        sys.exit("No migrations directory at %s" % MIGRATIONS_DIR)
    # Sorted by filename: the numeric prefix is the ordering contract.
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Induduzo database migrations.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--status", action="store_true", help="show state and exit")
    parser.add_argument("--dry-run", action="store_true", help="show what would run")
    parser.add_argument(
        "--baseline",
        metavar="FILENAME",
        help=(
            "Adopt an existing database: record every migration UP TO AND INCLUDING "
            "this file as applied, without running it. Use only when the schema "
            "already matches, e.g. a database created by Docker's initdb before "
            "this runner existed."
        ),
    )
    args = parser.parse_args()

    if not args.database_url:
        sys.exit("Set DATABASE_URL or pass --database-url.")

    files = discover()
    skipped = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sh"))

    with psycopg.connect(args.database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(TRACKING_TABLE)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("select filename, checksum from schema_migrations")
            applied = dict(cur.fetchall())

        # A migration that changed after being applied means local and
        # production no longer describe the same schema. Fail loudly.
        drifted = [
            f.name
            for f in files
            if f.name in applied and applied[f.name] != checksum(f.read_text(encoding="utf-8"))
        ]
        if drifted:
            print("ERROR: these migrations changed after they were applied:")
            for name in drifted:
                print("  %s" % name)
            print("\nMigrations are immutable once run. Add a new file instead.")
            return 1

        pending = [f for f in files if f.name not in applied]

        if args.baseline:
            names = [f.name for f in files]
            if args.baseline not in names:
                print("ERROR: %s is not a migration. Known files:" % args.baseline)
                for n in names:
                    print("  %s" % n)
                return 1

            upto = names.index(args.baseline)
            marking = [f for f in files[: upto + 1] if f.name not in applied]
            if not marking:
                print("Nothing to baseline; those migrations are already recorded.")
                return 0

            print("Recording as applied WITHOUT running (schema assumed to exist):")
            for f in marking:
                print("  %s" % f.name)
            with conn.cursor() as cur:
                for f in marking:
                    cur.execute(
                        "insert into schema_migrations (filename, checksum, applied_by) "
                        "values (%s, %s, 'baseline')",
                        (f.name, checksum(f.read_text(encoding="utf-8"))),
                    )
            conn.commit()
            print("\nBaselined %d migration(s). Run again to apply the rest." % len(marking))
            return 0

        if args.status or args.dry_run:
            print("Applied:")
            for f in files:
                if f.name in applied:
                    print("  [x] %s" % f.name)
            print("Pending:")
            for f in pending:
                print("  [ ] %s" % f.name)
            if not pending:
                print("  (none)")
            if skipped:
                print("Skipped (shell, local Docker only): %s" % ", ".join(skipped))
            return 0

        if not pending:
            print("Database is up to date (%d migrations applied)." % len(applied))
            if skipped:
                print("Skipped (shell, local Docker only): %s" % ", ".join(skipped))
            return 0

        for f in pending:
            sql = f.read_text(encoding="utf-8")
            print("applying %s ..." % f.name, end=" ", flush=True)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    # Same transaction as the migration itself.
                    cur.execute(
                        "insert into schema_migrations (filename, checksum) values (%s, %s)",
                        (f.name, checksum(sql)),
                    )
                conn.commit()
                print("ok")
            except Exception as exc:
                conn.rollback()
                print("FAILED")
                print("\n%s was rolled back. Nothing was applied.\n\n%s" % (f.name, exc))
                return 1

        print("\nApplied %d migration(s)." % len(pending))
        if skipped:
            print("Skipped (shell, local Docker only): %s" % ", ".join(skipped))
            print("On a managed host, set the API role password out of band:")
            print("  alter role induduzo_api login password '<from your secret store>';")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
