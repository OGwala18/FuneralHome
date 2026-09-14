"""Error tracking via Sentry, with personal data stripped before it leaves.

WHY THIS FILE IS MOSTLY SCRUBBING
Sentry's value is seeing what actually broke in production. Its danger, here, is
that the things it captures by default — request bodies, headers, and the local
variables in a stack frame — are exactly where this system's personal data
lives. An unhandled error inside the registration endpoint would otherwise ship
a South African ID number, mobile number and home address to a third party.

So three layers, deliberately overlapping:

1. `send_default_pii=False` and no local variables, so the obvious channels are
   closed at the source.
2. A key denylist, because a field named `id_number` is sensitive whatever it
   contains.
3. A regex backstop for SA ID numbers, mobile numbers and emails, because
   personal data has a habit of turning up inside free-text messages that no
   denylist anticipated.

If Sentry is not configured the whole module is inert and the app runs normally.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)

REDACTED = "[redacted]"

# Any key containing one of these (case-insensitive) has its value replaced.
_SENSITIVE_KEYS = (
    # Credentials. "key" is deliberately broad rather than "api_key": a test
    # caught `service_role_key` slipping through a narrower list, and
    # over-redacting a harmless field costs nothing.
    "password", "passwd", "secret", "token", "key", "authorization",
    "cookie", "session", "credential", "private", "salt", "signature",
    # Connection strings carry the database password inside them.
    "dsn", "database_url", "conn_str", "connection_string",
    # Domain specific: everything the forms collect about a person.
    "id_number", "mobile", "phone", "tel", "email", "address", "postal",
    "first_name", "surname", "full_name", "next_of_kin", "beneficiary",
    "date_of_birth", "dob", "notes", "account", "branch_code", "iban",
)

# Backstops for data appearing inside free text, where no key name helps.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Credentials embedded in a URL, e.g. postgresql://user:password@host/db.
    # First, because the rules below would otherwise mangle it into something
    # unrecognisable and leave the password in place.
    (re.compile(r"\b(\w+)://[^:/\s]+:[^@/\s]+@"), r"\1://[credentials]@"),
    # SA ID: 13 consecutive digits.
    (re.compile(r"\b\d{13}\b"), "[id-number]"),
    # SA mobile in any common form.
    (re.compile(r"\b(?:\+?27|0)[6-8]\d{8}\b"), "[mobile]"),
    (re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]{2,}\b"), "[email]"),
]

_MAX_DEPTH = 12


def _scrub_text(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _scrub(node: Any, depth: int = 0) -> Any:
    """Walk an event and redact anything that looks personal."""
    if depth > _MAX_DEPTH:
        return REDACTED

    if isinstance(node, dict):
        cleaned = {}
        for key, value in node.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SENSITIVE_KEYS):
                cleaned[key] = REDACTED
            else:
                cleaned[key] = _scrub(value, depth + 1)
        return cleaned

    if isinstance(node, (list, tuple)):
        scrubbed = [_scrub(item, depth + 1) for item in node]
        return type(node)(scrubbed) if isinstance(node, tuple) else scrubbed

    if isinstance(node, str):
        return _scrub_text(node)

    return node


def _before_send(event: dict, hint: dict) -> dict | None:
    """Last gate before an event leaves the process."""
    try:
        # Bodies can be large and are always the richest source of personal
        # data; drop rather than scrub, since the URL and status say enough.
        request = event.get("request")
        if isinstance(request, dict):
            request.pop("data", None)
            request.pop("cookies", None)
            headers = request.get("headers")
            if isinstance(headers, dict):
                for header in list(headers):
                    if header.lower() in {"authorization", "cookie", "x-api-key"}:
                        headers[header] = REDACTED
            if isinstance(request.get("query_string"), str):
                request["query_string"] = _scrub_text(request["query_string"])

        return _scrub(event)
    except Exception:  # noqa: BLE001
        # A scrubber that throws must never let an unscrubbed event through.
        logger.exception("Sentry scrubbing failed; dropping the event")
        return None


def init_sentry() -> bool:
    """Start Sentry if configured. Returns whether it was enabled."""
    settings = get_settings()
    if not settings.sentry_dsn:
        logger.info("Sentry not configured; error tracking is off.")
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry-sdk is not installed; error tracking is off.")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.release,
        # Never send request bodies, user identifiers or IP addresses.
        send_default_pii=False,
        # Stack-frame locals hold the parsed request model, i.e. the applicant's
        # details. This is the single most important line in the file.
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=_before_send,
        before_send_transaction=_before_send,
    )
    logger.info(
        "Sentry enabled (environment=%s, traces=%.2f)",
        settings.environment,
        settings.sentry_traces_sample_rate,
    )
    return True
