"""Per-request context: an id to trace by, a size ceiling, and the headers.

ONE MIDDLEWARE, THREE JOBS
1. A request id. Taken from the caller's X-Request-ID when it is a plain token,
   otherwise made up here. It goes back on the response, into every log line
   written while handling the request (background tasks included), and into
   every error body. A ticket that quotes it leads straight to the log lines.
2. A body-size ceiling. Without one, a single POST of hundreds of megabytes is
   read into memory before validation can refuse it. Refused with 413 before
   the body is read when Content-Length says so, and while reading otherwise.
3. The response headers every answer gets: the browser-hardening set that
   used to live in main.py, plus `Cache-Control: no-store`, so a shared office
   computer's browser never keeps a copy of a member's details.

Pure ASGI rather than @app.middleware("http"): the 413 is sent before the app
runs, and the headers land on every response this middleware sees.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextvars import ContextVar
from urllib.parse import parse_qsl, urlencode

from .errors import ApiError

REQUEST_ID_HEADER = "X-Request-ID"

# What a caller may supply as its own id: no spaces, quotes or control
# characters, so it is safe to echo into a header and a log line.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return request_id_var.get()


def security_headers(deployed: bool) -> list[tuple[bytes, bytes]]:
    """The same class of headers the website gets from Netlify, narrowed for JSON."""
    headers = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        # An API serves no documents and needs no browser features.
        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]
    if deployed:
        # Only when deployed: HSTS over plain HTTP in dev would pin localhost to
        # HTTPS in the browser and break the dev server.
        headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
    return headers


class RequestTooLarge(ApiError):
    def __init__(self) -> None:
        super().__init__(413, "request_too_large", "That request is too large.")


class RequestContextMiddleware:
    def __init__(self, app, *, max_body_bytes: int, deployed: bool) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.extra_headers = security_headers(deployed)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and _SAFE_ID.fullmatch(incoming) else uuid.uuid4().hex
        request_id_var.set(request_id)
        # Readable as request.state.request_id, for the handlers in main.py that
        # run outside this middleware (the 500 handler).
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                for name, value in self.extra_headers:
                    if name not in present:
                        headers.append((name, value))
                if b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        declared = _header(scope, b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > self.max_body_bytes):
            await _send_json(send_with_headers, 413, {
                "detail": "That request is too large.",
                "code": "request_too_large",
                "request_id": request_id,
            })
            return

        received = 0

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    # Raised inside the app, where the exception handlers turn
                    # it into the same 413 the fast path above sends.
                    raise RequestTooLarge()
            return message

        await self.app(scope, counting_receive, send_with_headers)


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1").strip()
    return None


async def _send_json(send, status: int, body: dict) -> None:
    payload = json.dumps(body).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode())],
    })
    await send({"type": "http.response.body", "body": payload})


# --- Logging ----------------------------------------------------------------------

def redact_query(path: str) -> str:
    """`/api/admin/members?search=Dlamini&limit=25` -> `...?search=*&limit=*`.

    Staff search the book by name, phone and ID number, and the search rides in
    the query string, so the access log would otherwise hold exactly the
    personal data rule 9 keeps out of logs. The names stay; the values go.
    """
    if "?" not in path:
        return path
    base, query = path.split("?", 1)
    names = [name for name, _ in parse_qsl(query, keep_blank_values=True)]
    if not names:
        return base + "?*"
    return base + "?" + urlencode([(name, "*") for name in names], safe="*")


class AccessLogRedactor(logging.Filter):
    """Removes query-string values from Uvicorn's access log lines.

    Uvicorn's access record carries (client, method, path, http_version, status).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], redact_query(args[2]), *args[3:])
        return True


def install_logging_filters() -> None:
    """Stamp every log record with its request id ('-' outside a request) and
    attach the redactor to Uvicorn's access log. Safe to call more than once.

    The stamp is made where records are created, not by a handler filter, so
    every handler (Railway's stdout, Sentry's breadcrumbs, a test's capture)
    sees the same `request_id` attribute.
    """
    previous = logging.getLogRecordFactory()
    if not getattr(previous, "stamps_request_id", False):
        def factory(*args, **kwargs):
            record = previous(*args, **kwargs)
            record.request_id = request_id_var.get()
            return record

        factory.stamps_request_id = True
        logging.setLogRecordFactory(factory)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogRedactor) for f in access.filters):
        access.addFilter(AccessLogRedactor())
