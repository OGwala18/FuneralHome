"""Making the public form safe to submit twice.

A family on a weak signal taps "Submit" again, or the browser retries a request
the server already handled. Neither may create a second enquiry or send the
office a second email. See db/migrations/0019_enquiry_idempotency.sql.

Stage 1 uses the Idempotency-Key header: the browser invents one UUID per form
attempt and sends it with every try. Stage 2 needs no header; it compares a
fingerprint of the application with the one already saved.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from fastapi import HTTPException, Request, Response, status

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"


def idempotency_key(request: Request) -> str | None:
    """The caller's key, or None when the header is absent.

    The header is optional so a browser still running an older copy of the site
    keeps working. A key that is present but not a UUID is refused: accepting
    free text would let a caller pick a key someone else is likely to use.
    """
    raw = request.headers.get(HEADER)
    if raw is None or not raw.strip():
        return None
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must be a UUID.",
        ) from exc


def fingerprint(payload: dict) -> str:
    """A one-way hash of a request body, stable across key order."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mark_replayed(response: Response) -> None:
    response.headers[REPLAYED_HEADER] = "true"


def refuse_mismatch() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "This form was already sent with different details. "
            "Please reload the page and start again."
        ),
    )
