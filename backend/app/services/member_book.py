"""Read the imported member book using a verified staff member's Supabase JWT.

The publishable key identifies this application. The JWT selects the
``authenticated`` Postgres role, so the existing RLS policies apply. No member
data or credentials are cached, logged, or stored in local Postgres.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import HTTPException, status

from ..config import get_settings


def member_book_get(table: str, params: dict[str, str], jwt_token: str,
                    *, count: bool = False) -> tuple[list[dict[str, Any]], int | None]:
    """Query one approved table. Return rows and an optional exact count."""
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_publishable_key):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Member book is not configured on this server.",
        )

    if table not in {"people", "person_phones", "policy_members", "policy_overview"}:
        raise ValueError("Unapproved member book table")

    url = (
        settings.supabase_url.rstrip("/")
        + "/rest/v1/" + table
        + "?" + urllib.parse.urlencode(params)
    )
    headers = {
        "apikey": settings.supabase_publishable_key,
        "Authorization": "Bearer " + jwt_token,
        "Accept": "application/json",
    }
    if count:
        headers["Prefer"] = "count=exact"
    request = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            rows = json.load(response)
            content_range = response.headers.get("Content-Range", "")
    except urllib.error.HTTPError as exc:
        # Supabase's error body may contain a field value. Never log or return it.
        if exc.code == 401:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "Your session has expired. Please sign in again.") from None
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Could not load the member book from Supabase.") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Could not load the member book from Supabase.") from None

    if not isinstance(rows, list):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Could not load the member book from Supabase.")
    total = None
    if count:
        match = re.search(r"/(\d+)$", content_range)
        if match:
            total = int(match.group(1))
    return rows, total
