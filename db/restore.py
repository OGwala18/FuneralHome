"""Restore one daily backup (db/backup.py) into an EMPTY database.

    RESTORE_DATABASE_URL=postgresql://... python db/restore.py induduzo-2026-11-16T0600Z.json.gz
    RESTORE_DATABASE_URL=postgresql://... python db/restore.py FILE --dry-run
    RESTORE_DATABASE_URL=postgresql://... python db/restore.py FILE --no-forward

The target comes from RESTORE_DATABASE_URL only, never a command-line argument,
so the connection string stays out of shell history and process lists.

WHAT IT DOES, IN ORDER
1. Reads the backup and checks its shape.
2. Refuses if the target already holds a member book, leads or staff: any row
   in people, policies, plan_enquiries or staff_users. It can never overwrite a
   live book. It also refuses a target equal to DATABASE_URL or
   DATABASE_OWNER_URL.
3. Builds the schema with db/migrate.py, up to the newest migration the backup
   itself records, and further one file at a time until every table and column
   in the backup exists. (A backup from before a data migration must be loaded
   BEFORE that migration runs, so the migration sees the rows.)
4. In ONE transaction: empties the backup's tables (the migrations seed some
   reference rows; the backup's own copy of them wins), switches off each
   table's user triggers, loads every table in foreign-key order, switches the
   triggers back on, then checks every table row by row against the file. Any
   difference rolls the whole load back.
5. Runs the remaining migrations over the restored rows (skip with
   --no-forward).

TRIGGERS
User triggers are off during the load, so nothing is recorded twice and nothing
is rewritten: the `set_updated_at` triggers would stamp every row with today's
date, and audit or history triggers (member_book_history, migration 0031) would
log the whole book as freshly edited. The backup already holds those history
rows as they were. Foreign keys stay on (they are not user triggers), so a load
that breaks integrity fails.

`schema_migrations` in the backup is read, never loaded: the target keeps its
own truthful record of what ran there.

WHAT IT NEVER DOES
Print a row, a name, a number or a connection string. Output is table names and
row counts. A database error is reported by its kind and the constraint or
column involved, never its message text, because Postgres quotes the offending
value in many of its messages.

The backup holds personal information (ID numbers). Restore it only into a
database you control, and never copy the file into the repository.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover
    sys.exit("psycopg is required.  pip install 'psycopg[binary]'")

HERE = Path(__file__).parent
MIGRATIONS_DIR = HERE / "migrations"

# Any row here means the target is in use. The restore stops before writing.
GUARDED_TABLES = ("people", "policies", "plan_enquiries", "staff_users")
# Read from the backup, never loaded into the target.
NOT_LOADED = {"schema_migrations"}
BATCH = 500


class Refused(Exception):
    """A reason not to go on, safe to print."""


# --------------------------------------------------------------------------- #
# The backup file
# --------------------------------------------------------------------------- #

def read_backup(path: Path) -> tuple[str, dict[str, list[dict]]]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Refused(f"{path.name} is not a readable backup ({type(exc).__name__}).")
    tables = doc.get("tables") if isinstance(doc, dict) else None
    if not isinstance(tables, dict) or not all(isinstance(v, list) for v in tables.values()):
        raise Refused(f"{path.name} does not look like a db/backup.py file.")
    for name, rows in tables.items():
        if rows:
            keys = set(rows[0])
            if any(set(r) != keys for r in rows):
                raise Refused(f"{name}: rows in the backup do not share one set of columns.")
    return str(doc.get("taken_at", "unknown")), tables


def backup_columns(rows: list[dict]) -> list[str] | None:
    """The columns a table had when backed up. None for an empty table: json_agg
    of no rows is [], so the file cannot say."""
    return list(rows[0]) if rows else None


# --------------------------------------------------------------------------- #
# The target
# --------------------------------------------------------------------------- #

def public_columns(conn) -> dict[str, dict[str, str]]:
    """{table: {column: attgenerated}} for every ordinary table in public."""
    out: dict[str, dict[str, str]] = {}
    for table, column, generated in conn.execute(
        """
        select c.relname, a.attname, a.attgenerated
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
          join pg_attribute a on a.attrelid = c.oid
         where n.nspname = 'public' and c.relkind in ('r', 'p')
           and a.attnum > 0 and not a.attisdropped
         order by c.relname, a.attnum
        """
    ):
        out.setdefault(table, {})[column] = generated
    return out


def guard(conn) -> None:
    present = public_columns(conn)
    busy = []
    for table in GUARDED_TABLES:
        if table in present:
            n = conn.execute(
                sql.SQL("select count(*) from (select 1 from public.{} limit 1) x").format(
                    sql.Identifier(table))
            ).fetchone()[0]
            if n:
                busy.append(table)
    if busy:
        raise Refused(
            "The target already has rows in " + ", ".join(busy) + ". A restore only ever "
            "goes into an empty database; nothing was written.")


def missing_from(conn, tables: dict[str, list[dict]]) -> list[str]:
    """What the target still lacks to hold the backup: tables, or table.column."""
    present = public_columns(conn)
    gaps = []
    for table, rows in tables.items():
        if table in NOT_LOADED:
            continue
        if table not in present:
            gaps.append(table)
            continue
        for col in backup_columns(rows) or []:
            if col not in present[table]:
                gaps.append(f"{table}.{col}")
    return gaps


def load_order(conn, names: list[str]) -> list[str]:
    """Parents before children, from the target's own foreign keys."""
    wanted = set(names)
    parents: dict[str, set[str]] = {t: set() for t in names}
    for child, parent in conn.execute(
        """
        select c.relname, p.relname
          from pg_constraint k
          join pg_class c on c.oid = k.conrelid
          join pg_class p on p.oid = k.confrelid
          join pg_namespace n on n.oid = c.relnamespace
         where k.contype = 'f' and n.nspname = 'public'
        """
    ):
        if child in wanted and parent in wanted:
            if child == parent:
                raise Refused(
                    f"{child} refers to itself. Teach db/restore.py to load it parents-first "
                    "before restoring this backup.")
            parents[child].add(parent)
    order: list[str] = []
    done: set[str] = set()
    while len(order) < len(names):
        ready = sorted(t for t in names if t not in done and parents[t] <= done)
        if not ready:
            stuck = sorted(t for t in names if t not in done)
            raise Refused("Foreign keys form a loop between: " + ", ".join(stuck))
        order.extend(ready)
        done.update(ready)
    return order


# --------------------------------------------------------------------------- #
# Migrations
# --------------------------------------------------------------------------- #

def migration_files() -> list[str]:
    return sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))


def run_migrate(url: str, upto: str | None) -> None:
    """Run db/migrate.py against the target. Its own output names files only,
    but a failing migration prints the database's message, which can quote a
    row once data is loaded; so only file lines are passed on."""
    cmd = [sys.executable, str(HERE / "migrate.py")]
    if upto:
        cmd += ["--upto", upto]
    env = dict(os.environ, DATABASE_URL=url)
    done = subprocess.run(cmd, env=env, capture_output=True, text=True)
    for line in done.stdout.splitlines():
        if line.startswith(("applying ", "Applied ", "Database is up to date")):
            print("  " + line)
    if done.returncode != 0:
        raise Refused(
            "db/migrate.py failed (output above names the file). Run it yourself against "
            "the scratch database to read the error; it may quote a row.")


def build_schema(url: str, tables: dict[str, list[dict]]) -> list[str]:
    """Migrate to the backup's own level, then on until the backup fits.
    Returns the migrations still to run after the load."""
    files = migration_files()
    recorded = {r.get("filename") for r in tables.get("schema_migrations", [])}
    known = sorted(f for f in recorded if f in files)
    unknown = sorted(f for f in recorded if f and f not in files)
    if unknown:
        print("Note: the backup records migrations this checkout does not have "
              "(renamed or newer): " + ", ".join(unknown))

    level = known[-1] if known else None
    if level:
        print(f"Building the schema up to {level} (the backup's newest known migration)")
        run_migrate(url, level)
    else:
        print("The backup records no known migration; building from the first file")

    with psycopg.connect(url) as conn:
        gaps = missing_from(conn, tables)
    position = files.index(level) + 1 if level else 0
    while gaps:
        if position >= len(files):
            raise Refused(
                "Even with every migration in this checkout, the target lacks: "
                + ", ".join(gaps) + ". The backup is from a newer schema; check out the "
                "branch it was taken on.")
        print(f"  the backup needs {gaps[0]}" + (f" and {len(gaps) - 1} more" if len(gaps) > 1 else "")
              + f"; applying {files[position]}")
        run_migrate(url, files[position])
        position += 1
        with psycopg.connect(url) as conn:
            gaps = missing_from(conn, tables)

    with psycopg.connect(url) as conn:
        applied = {r[0] for r in conn.execute("select filename from schema_migrations")}
    return [f for f in files if f not in applied]


# --------------------------------------------------------------------------- #
# The load
# --------------------------------------------------------------------------- #

def describe(exc: Exception) -> str:
    """A database error without its message text (which can quote a value)."""
    diag = getattr(exc, "diag", None)
    bits = [type(exc).__name__]
    for label, attr in (("table", "table_name"), ("column", "column_name"),
                        ("constraint", "constraint_name")):
        value = getattr(diag, attr, None) if diag else None
        if value:
            bits.append(f"{label} {value}")
    return ", ".join(bits)


def load(url: str, tables: dict[str, list[dict]]) -> dict[str, int]:
    names = [t for t in tables if t not in NOT_LOADED]
    cascaded: list[str] = []

    with psycopg.connect(url) as conn:
        conn.add_notice_handler(
            lambda d: cascaded.append(d.message_primary or "")
            if (d.message_primary or "").startswith("truncate cascades to table") else None)
        with conn.transaction():
            guard(conn)  # again, inside the transaction that writes
            present = public_columns(conn)
            order = load_order(conn, names)
            ident = {t: sql.Identifier("public", t) for t in names}

            conn.execute(sql.SQL("truncate {} cascade").format(
                sql.SQL(", ").join(ident[t] for t in order)))
            for line in cascaded:
                print(f"  note: {line} (not in the backup; emptied with its parent)")

            for t in order:
                conn.execute(sql.SQL("alter table {} disable trigger user").format(ident[t]))

            counts: dict[str, int] = {}
            for t in order:
                rows = tables[t]
                counts[t] = len(rows)
                if not rows:
                    continue
                cols = [c for c in backup_columns(rows) if not present[t].get(c)]  # skip generated
                col_list = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
                stmt = sql.SQL(
                    "insert into {t} ({cols}) overriding system value "
                    "select {cols} from json_populate_recordset(null::{t}, %s::json)"
                ).format(t=ident[t], cols=col_list)
                try:
                    for i in range(0, len(rows), BATCH):
                        conn.execute(stmt, (json.dumps(rows[i:i + BATCH]),))
                except psycopg.Error as exc:
                    raise Refused(f"Loading {t} failed: {describe(exc)}. Nothing was kept.")

            for t in order:
                conn.execute(sql.SQL("alter table {} enable trigger user").format(ident[t]))

            # Sequences (none today; every key is a uuid) must not hand out a
            # number the restored rows already use.
            for t in order:
                for (seq_col,) in conn.execute(
                    "select a.attname from pg_attribute a where a.attrelid = %s::regclass "
                    "and a.attnum > 0 and not a.attisdropped "
                    "and pg_get_serial_sequence(%s, a.attname) is not null",
                    (f'public."{t}"', f'public."{t}"'),
                ).fetchall():
                    conn.execute(sql.SQL(
                        "select setval(pg_get_serial_sequence(%s, %s), "
                        "coalesce((select max({c}) from {t}), 0) + 1, false)"
                    ).format(c=sql.Identifier(seq_col), t=ident[t]), (f'public."{t}"', seq_col))

            bad = verify(conn, tables, order, ident)
            if bad:
                raise Refused("The restored rows differ from the file in: " + ", ".join(bad)
                              + ". The load was rolled back.")
    return counts


def verify(conn, tables, order, ident) -> list[str]:
    """Row-by-row: the table and the file, each read back through the table's
    own column types, must hold exactly the same rows, duplicates included."""
    bad = []
    for t in order:
        rows = tables[t]
        actual = conn.execute(sql.SQL("select count(*) from {}").format(ident[t])).fetchone()[0]
        if actual != len(rows):
            bad.append(f"{t} (count {actual} vs {len(rows)} in the file)")
            continue
        if not rows:
            continue
        as_text = sql.SQL(", ").join(
            sql.SQL("{}::text").format(sql.Identifier(c)) for c in backup_columns(rows))
        differ = conn.execute(sql.SQL(
            "select (select count(*) from (select {cols} from json_populate_recordset(null::{t}, %s::json)"
            "        except all select {cols} from {t}) a)"
            "     + (select count(*) from (select {cols} from {t}"
            "        except all select {cols} from json_populate_recordset(null::{t}, %s::json)) b)"
        ).format(cols=as_text, t=ident[t]), (json.dumps(rows), json.dumps(rows))).fetchone()[0]
        if differ:
            bad.append(f"{t} ({differ} rows differ)")
    return bad


# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a db/backup.py file into an empty database.")
    parser.add_argument("backup", type=Path, help="an induduzo-*.json.gz file")
    parser.add_argument("--dry-run", action="store_true",
                        help="read the file and check the target; write nothing")
    parser.add_argument("--no-forward", action="store_true",
                        help="stop at the schema the backup needed; do not run newer migrations")
    args = parser.parse_args()

    url = os.environ.get("RESTORE_DATABASE_URL")
    if not url:
        print("RESTORE_DATABASE_URL is not set.", file=sys.stderr)
        return 2
    for other in ("DATABASE_URL", "DATABASE_OWNER_URL"):
        if os.environ.get(other) and os.environ[other].strip() == url.strip():
            print(f"RESTORE_DATABASE_URL is the same as {other}. Restore into a separate, "
                  "empty database.", file=sys.stderr)
            return 2

    try:
        taken_at, tables = read_backup(args.backup)
        loadable = {t: r for t, r in tables.items() if t not in NOT_LOADED}
        print(f"Backup {args.backup.name} (taken {taken_at}): {len(loadable)} tables, "
              f"{sum(len(r) for r in loadable.values())} rows; "
              f"people={len(tables.get('people', []))}, policies={len(tables.get('policies', []))}")

        with psycopg.connect(url) as conn:
            guard(conn)
        print("Target is empty: no people, policies, enquiries or staff.")

        if args.dry_run:
            print("Dry run: nothing written.")
            return 0

        later = build_schema(url, tables)
        print("Loading in one transaction, user triggers off ...")
        counts = load(url, tables)
        for t in sorted(counts):
            print(f"  {t}: {counts[t]}")
        print(f"Loaded and checked row by row: {len(counts)} tables, "
              f"{sum(counts.values())} rows, every table identical to the file.")

        if later and not args.no_forward:
            print(f"Bringing the schema forward ({len(later)} newer migrations) ...")
            run_migrate(url, None)
        elif later:
            print(f"Stopped before {len(later)} newer migrations (--no-forward).")
    except Refused as why:
        print(f"Refused: {why}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"Database error: {describe(exc)}", file=sys.stderr)
        return 1
    print("Restore complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
