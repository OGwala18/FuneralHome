"""Database access.

The database is a separate service reached by a connection string; this module
is the only place that knows how to talk to it.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def init_pool() -> None:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        logger.info("Database pool opened")


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
