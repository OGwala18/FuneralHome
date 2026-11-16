"""Database access.

The database is a separate service reached by a connection string; this module
is the only place that knows how to talk to it.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None

# Environments whose database connection never leaves the machine or a
# provider's private network, so there is nobody in between to read it.
_LOCAL_ENVIRONMENTS = {"development", "test"}


def tls_setting(database_url: str, environment: str) -> dict[str, str]:
    """`{"sslmode": "require"}` when the connection crosses the internet.

    psycopg's default, `prefer`, uses TLS only when the server offers it, so
    anyone in between can answer "no TLS here" and read every row in transit:
    ID numbers, phone numbers, addresses. The live API reaches Supabase over
    the public internet, and Supabase's pooler offers TLS (checked 13 Nov 2026),
    so a deployed API insists on it.

    Left alone: a DATABASE_URL that names its own sslmode (the operator's
    choice wins), a laptop or the test suite, and private hosts such as
    Railway's `*.railway.internal`, which never touch the internet.
    """
    if environment.lower() in _LOCAL_ENVIRONMENTS:
        return {}
    try:
        parts = conninfo_to_dict(database_url)
    except Exception:  # noqa: BLE001 - let the pool report a malformed URL itself
        return {}
    if parts.get("sslmode"):
        return {}
    host = str(parts.get("host") or "")
    private = (not host or host.startswith("/") or "." not in host
               or host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".internal"))
    return {} if private else {"sslmode": "require"}


def init_pool() -> None:
    global _pool
    if _pool is None:
        settings = get_settings()
        tls = tls_setting(settings.database_url, settings.environment)
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, **tls},
            open=True,
        )
        # Never the URL: it carries the password.
        logger.info("Database pool opened (TLS %s)",
                    "required" if tls else "as configured")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("Database pool closed")


@contextmanager
def connection() -> Iterator[Any]:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    with _pool.connection() as conn:
        yield conn


def log_event(conn: Any, enquiry_id: str, event_type: str, payload: dict | None = None,
              actor: str = "public_website") -> None:
    """Append to the audit trail.

    Runs inside the caller's transaction so an enquiry and its event either both
    land or neither does.
    """
    import json

    conn.execute(
        """
        insert into enquiry_events (enquiry_id, event_type, actor, payload)
        values (%s, %s, %s, %s::jsonb)
        """,
        (enquiry_id, event_type, actor, json.dumps(payload or {})),
    )
