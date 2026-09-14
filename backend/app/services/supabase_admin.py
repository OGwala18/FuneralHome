"""Inviting staff to Supabase Auth.

This is the ONLY place the service-role key is used, and it must never leave the
server. That key can mint accounts and read every user, so:

  * it is read from the environment, never committed;
  * it is never returned in a response, logged, or sent to the portal;
  * the portal cannot call Supabase admin APIs at all — it asks our API, which
    holds the key and enforces that the caller is an owner first.

Inviting is optional. Without a key configured the authorisation record is still
created and an owner adds the Supabase account by hand, so the feature degrades
rather than breaking.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InviteResult:
    sent: bool
    detail: str | None = None


def invite_supabase_user(email: str) -> InviteResult:
    """Send a Supabase invitation email. Never raises."""
    settings = get_settings()

    if not (settings.supabase_url and settings.supabase_service_role_key):
        logger.info(
            "Supabase service key not configured; staff row created but no invite sent."
        )
        return InviteResult(
            sent=False,
            detail="No invite sent. Create the account in the Supabase dashboard.",
        )

    url = settings.supabase_url.rstrip("/") + "/auth/v1/invite"
    body = json.dumps({"email": email}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": settings.supabase_service_role_key,
            "Authorization": "Bearer %s" % settings.supabase_service_role_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if 200 <= response.status < 300:
                logger.info("Supabase invitation sent")
                return InviteResult(sent=True)
            return InviteResult(sent=False, detail="Supabase returned %s" % response.status)
    except urllib.error.HTTPError as exc:
        # Body may name the address; keep it out of the log.
        logger.warning("Supabase invite rejected with HTTP %s", exc.code)
        return InviteResult(sent=False, detail="Supabase rejected the invitation.")
    except Exception:  # noqa: BLE001 - an invite failure must not undo the grant
        logger.warning("Supabase invite failed to send")
        return InviteResult(sent=False, detail="Could not reach Supabase.")
