"""Inviting staff to Supabase Auth, and setting a forgotten password.

This is the ONLY place the service-role key is used, and it must never leave the
server. That key can mint accounts and read every user, so:

  * it is read from the environment, never committed;
  * it is never returned in a response, logged, or sent to the portal;
  * the portal cannot call Supabase admin APIs at all — it asks our API, which
    holds the key and enforces that the caller is an owner first.

Inviting is optional. Without a key configured the authorisation record is still
created and an owner adds the Supabase account by hand, so the feature degrades
rather than breaking. A forgotten password (routers/password_reset.py) cannot be
set without the key, so that feature reports itself as not configured instead.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InviteResult:
    sent: bool
    detail: str | None = None


def _headers(key: str) -> dict[str, str]:
    """The headers that carry the service key.

    A new-style secret key (sb_secret_...) is not a JWT and goes on `apikey`
    ONLY: Supabase rejects one sent as a Bearer token ("Invalid JWT"), and its
    gateway puts the matching service-role JWT on Authorization itself. A
    legacy service_role key is a JWT and is sent on both, as before.
    """
    headers = {"Content-Type": "application/json", "apikey": key}
    if not key.startswith("sb_"):
        headers["Authorization"] = "Bearer %s" % key
    return headers


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
        headers=_headers(settings.supabase_service_role_key),
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


# --- A forgotten password (routers/password_reset.py) -------------------------------

@dataclass(frozen=True)
class PasswordResult:
    """What Supabase said to a new password.

    `saved`: it is now the person's password. `rejected`: Supabase refused the
    password itself (too weak, or against the project's rules) and `detail` is
    its own sentence, which names a rule and never a person. Anything else is
    an outage: the caller keeps the temporary password alive for another try.
    """
    saved: bool
    rejected: bool = False
    detail: str | None = None
    # Supabase has no account with that id (deleted and made again by hand).
    no_account: bool = False


def admin_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _admin_url(path: str) -> str:
    return get_settings().supabase_url.rstrip("/") + "/auth/v1/admin" + path


def _call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """One admin call. Returns (status, parsed body); raises only on no answer."""
    request = urllib.request.Request(
        _admin_url(path),
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers=_headers(get_settings().supabase_service_role_key),
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        status = exc.code
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {"items": parsed}


def find_user_id(email: str) -> str | None:
    """The Supabase account id for an address, for staff who have never signed
    in through the API (so staff_users.supabase_user_id is still empty).

    Staff are a handful of accounts, so one page of the user list is read and
    matched exactly; Supabase's own filter is a substring search. Never raises:
    None means "not found or not reachable", and the caller treats both alike.
    """
    if not admin_configured():
        return None
    wanted = email.strip().lower()
    try:
        for page in range(1, 6):
            status, body = _call("GET", "/users?page=%d&per_page=200" % page)
            if status != 200:
                logger.warning("Supabase user lookup answered HTTP %s", status)
                return None
            users = body.get("users") or []
            for user in users:
                if str(user.get("email") or "").strip().lower() == wanted:
                    return str(user.get("id"))
            if len(users) < 200:
                return None
    except Exception as exc:  # noqa: BLE001 - "not found" is the safe answer
        logger.warning("Supabase user lookup failed: %s", type(exc).__name__)
    return None


def set_password(user_id: str, password: str) -> PasswordResult:
    """Make `password` this Supabase account's password. Never raises.

    The password goes to Supabase over TLS and nowhere else: it is not logged,
    stored or returned. Supabase hashes it and applies the project's password
    rules, so a password it refuses comes back as `rejected` with its reason.
    """
    if not admin_configured():
        return PasswordResult(saved=False, detail="not_configured")
    try:
        status, body = _call("PUT", "/users/%s" % urllib.parse.quote(user_id, safe=""),
                             {"password": password})
    except Exception as exc:  # noqa: BLE001 - an outage, not the person's fault
        logger.warning("Supabase password update failed: %s", type(exc).__name__)
        return PasswordResult(saved=False)

    if 200 <= status < 300:
        logger.info("Supabase password updated")
        return PasswordResult(saved=True)
    if status == 404:
        logger.warning("Supabase has no account with the stored id")
        return PasswordResult(saved=False, no_account=True)

    # 422 (and 400 on some versions) is Supabase refusing the password itself:
    # too short, too weak, or against the project's character rules. Its
    # sentence names the rule, never the person, so it can go to the screen.
    code = str(body.get("error_code") or body.get("code") or "")
    message = body.get("msg") or body.get("message") or body.get("error_description")
    if status in (400, 422) and (code in ("weak_password", "validation_failed", "same_password")
                                 or "password" in str(message or "").lower()):
        logger.info("Supabase refused the new password (%s)", code or status)
        return PasswordResult(saved=False, rejected=True,
                              detail=str(message) if message else None)

    logger.warning("Supabase password update answered HTTP %s (%s)", status, code or "-")
    return PasswordResult(saved=False)
