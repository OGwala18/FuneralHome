"""Bring a production Postgres up to date and let the API log in to it.

    python db/provision_api_role.py

Reads two environment variables, and nothing else:

    DATABASE_OWNER_URL   the database owner's connection string
    API_DB_PASSWORD      the password the API will connect with as induduzo_api

This is what Railway's private `database-migrator` service runs. It is safe to
run again: migrations already applied are skipped, and the password is simply
set to the same value.

WHY THE API DOES NOT USE THE OWNER URL
The owner bypasses row-level security and can drop or alter the schema. 0005
creates `induduzo_api` as a role that can only read and write the rows the
endpoints need, and creates it NOLOGIN, because a credential must never live in
migration history. Locally 0006_local_api_password.sh opens it up; a managed
host cannot run shell scripts, so this does the same job from Python.

WHAT IT NEVER PRINTS
Either connection string or the password. The password does not even travel
to the server in clear text: libpq hashes it to a SCRAM verifier here, exactly
as psql's \\password does, so it cannot surface in a server log either.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
except ImportError:  # pragma: no cover
    sys.exit("psycopg is required.  pip install 'psycopg[binary]'")

API_ROLE = "induduzo_api"
MIGRATE = Path(__file__).parent / "migrate.py"

# The password ends up inside the API's DATABASE_URL, so it must survive a URL
# without escaping. 32 URL-safe characters is ~190 bits; nobody types it.
_PASSWORD_RE = re.compile(r"^[A-Za-z0-9_-]{32,}$")


def fail(message: str) -> int:
    print("ERROR: " + message, file=sys.stderr)
    return 1


def main() -> int:
    owner_url = os.getenv("DATABASE_OWNER_URL")
    password = os.getenv("API_DB_PASSWORD", "")

    if not owner_url:
        return fail("Set DATABASE_OWNER_URL to the database owner's connection string.")
    if not _PASSWORD_RE.fullmatch(password):
        return fail(
            "API_DB_PASSWORD must be at least 32 URL-safe characters (A-Z a-z 0-9 _ -). "
            "Generate one with:  python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    # 1. Schema. The runner prints filenames only. The URL goes through the
    #    environment rather than argv, where `ps` would show it.
    print("== Migrations", flush=True)
    env = {**os.environ, "DATABASE_URL": owner_url}
    result = subprocess.run([sys.executable, str(MIGRATE)], env=env, check=False)
    if result.returncode != 0:
        return fail("migrations did not apply; the API role was left unchanged.")

    # 2. Let the API role log in.
    print("== API role")
    try:
        with psycopg.connect(owner_url, autocommit=True) as conn:
            row = conn.execute(
                "select rolsuper, rolbypassrls from pg_roles where rolname = %s",
                (API_ROLE,),
            ).fetchone()
            if row is None:
                return fail(f"role {API_ROLE} does not exist; 0005_api_role.sql has not run.")
            if row[0] or row[1]:
                # Either attribute would make every RLS policy decorative.
                return fail(f"{API_ROLE} is a superuser or bypasses RLS. Fix that by hand first.")

            verifier = conn.pgconn.encrypt_password(password.encode(), API_ROLE.encode())
            conn.execute(
                sql.SQL("alter role {} with login password {}").format(
                    sql.Identifier(API_ROLE), sql.Literal(verifier.decode())
                )
            )
        print(f"{API_ROLE} can log in.")
    except psycopg.Error as exc:
        # psycopg's messages name the host and user, never the password.
        return fail(f"could not configure {API_ROLE}: {type(exc).__name__}: {exc}")

    # 3. Prove it, the way the API will connect.
    print("== Check")
    try:
        api_conninfo = make_conninfo(owner_url, user=API_ROLE, password=password)
        with psycopg.connect(api_conninfo) as conn:
            who = conn.execute("select current_user").fetchone()[0]
            conn.execute("select count(*) from plan_enquiries").fetchone()
        print(f"Connected as {who} and read plan_enquiries. Done.")
    except psycopg.Error as exc:
        return fail(f"{API_ROLE} could not connect or read: {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
