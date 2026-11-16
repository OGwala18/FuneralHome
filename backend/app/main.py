"""Induduzo API.

One FastAPI service in front of the local Postgres. The public website talks
only to this; it never holds a database credential.
"""

from __future__ import annotations

import itertools
import logging
from contextlib import asynccontextmanager

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

load_dotenv()

from .config import get_settings  # noqa: E402  (must follow load_dotenv)
from .db import close_pool, connection, init_pool  # noqa: E402
from .errors import code_for_status  # noqa: E402
from .observability import init_sentry  # noqa: E402
from .request_context import (  # noqa: E402
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    install_logging_filters,
    security_headers,
)
from .routers import admin, analytics, enquiries, members, payments, two_step, whatsapp  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    # [request_id] ties every line to the X-Request-ID a ticket quotes.
    format="%(asctime)s %(levelname)-8s %(name)s [%(request_id)s]: %(message)s",
)
install_logging_filters()
logger = logging.getLogger(__name__)

# Before anything else, so errors raised during startup are captured too.
_sentry_enabled = init_sentry()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_pool()
    yield
    close_pool()


settings = get_settings()

# Every deployed environment (internal, production) is locked down. Only a
# developer's own machine and the test suite get the interactive docs and go
# without HSTS. An internal copy on a public Railway address is still public.
_LOCAL_ENVIRONMENTS = {"development", "test"}
_is_deployed = settings.environment.lower() not in _LOCAL_ENVIRONMENTS

app = FastAPI(
    title="Induduzo Funeral Home API",
    version="0.1.0",
    description="Two-stage plan registration capture.",
    lifespan=lifespan,
    # Deployed, the interactive docs are an inventory of every endpoint and the
    # full request schema. Useful locally, free reconnaissance in public.
    docs_url=None if _is_deployed else "/docs",
    redoc_url=None if _is_deployed else "/redoc",
    openapi_url=None if _is_deployed else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # No cookies are used; the staff portal sends a bearer token instead, so
    # credentials stay off and the allowlist can remain strict.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    # Authorization is required, not optional: the staff portal sends a bearer
    # token, and a preflight that does not permit this header fails outright —
    # the browser blocks the request before the API ever sees it.
    # Idempotency-Key is sent by the public form; without it here the browser's
    # preflight fails and every registration is blocked before it leaves.
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-Induduzo-Device"],
    # X-Request-ID is readable by the site and portal, so an error toast can
    # show it and a ticket can quote it.
    expose_headers=["Idempotent-Replayed", "Retry-After", REQUEST_ID_HEADER],
)

# Added last, so it is the outermost: the request id exists before anything
# else runs, an oversized body is refused before it is read, and every response
# (CORS preflights and errors included) leaves with the security headers and
# Cache-Control: no-store. See app/request_context.py.
app.add_middleware(
    RequestContextMiddleware,
    max_body_bytes=settings.max_request_bytes,
    deployed=_is_deployed,
)

app.include_router(enquiries.router)
app.include_router(admin.router)
app.include_router(members.router)
app.include_router(payments.router)
app.include_router(whatsapp.router)
app.include_router(whatsapp.admin_router)
app.include_router(analytics.router)
app.include_router(two_step.router)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "-"


def _error(request: Request, status_code: int, code: str, detail, *,
           headers: dict[str, str] | None = None, **extra) -> JSONResponse:
    """Every error body has the same three keys: detail, code, request_id."""
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code, "request_id": _request_id(request), **extra},
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """A sentence for the screen plus a machine code (app/errors.py).

    ApiError and StaffGateError name their own code (second_step_required,
    duplicate_id_number, ...); any other HTTPException gets the generic code
    for its status, so no error leaves without one. Headers such as
    WWW-Authenticate and Retry-After are kept.
    """
    code = getattr(exc, "code", None) or code_for_status(exc.status_code)
    return _error(request, exc.status_code, code, exc.detail, headers=exc.headers)


@app.exception_handler(psycopg.OperationalError)
@app.exception_handler(PoolTimeout)
async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Postgres unreachable, or every pooled connection busy.

    A 503 the form already knows how to explain ("phone or WhatsApp us"),
    instead of a bare 500. The exception's text can carry the host name, so
    only its type is logged.
    """
    logger.error("Database unavailable: %s on %s %s",
                 type(exc).__name__, request.method, request.url.path)
    return _error(
        request, status.HTTP_503_SERVICE_UNAVAILABLE, "database_unavailable",
        "Our system is busy right now. Please try again in a minute, or phone or "
        "WhatsApp us and we will help you straight away.",
        headers={"Retry-After": "30"},
    )


@app.exception_handler(psycopg.DataError)
async def unstorable_value_handler(request: Request, exc: psycopg.DataError) -> JSONResponse:
    """A value Postgres cannot hold: a NUL byte, a number out of range, a date
    that does not exist. Caused by the request, so a 422, never a 500.

    The public form's schemas refuse these first (app/schemas.py); this is the
    net under every other route. The message can quote the value, so it is not
    logged or returned.
    """
    logger.warning("Unstorable value (%s) on %s %s",
                   type(exc).__name__, request.method, request.url.path)
    return _error(request, 422, "validation_failed",
                  "One of the fields contains something we cannot store. "
                  "Please check it and try again.", field_errors={})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """The last resort: a bug. JSON with the request id, never a stack trace.

    Starlette runs this outside the middleware stack, so the headers every other
    response gets are added here by hand. The exception still propagates after
    this returns, so Uvicorn logs the traceback and Sentry still sees it.
    """
    request_id = _request_id(request)
    logger.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    headers = {name.decode(): value.decode() for name, value in security_headers(_is_deployed)}
    headers.update({"Cache-Control": "no-store", REQUEST_ID_HEADER: request_id})
    return _error(
        request, status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error",
        "Something went wrong on our side. Please try again, or phone us.",
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return field-level errors the form can attach to the right input.

    FastAPI's default shape is a list the browser cannot map back to fields;
    this flattens it to {field: message}.
    """
    field_errors: dict[str, str] = {}
    for error in exc.errors():
        location = [part for part in error["loc"] if part != "body"]
        # A nested form section reads "beneficiary.date_of_birth". Pydantic's
        # union tags such as "literal['a']" are not field names, so they stop it.
        names = list(itertools.takewhile(
            lambda part: isinstance(part, str) and part.isidentifier(), location))
        if location:
            key = ".".join(names) if names else str(location[0])
            field_errors[key] = error["msg"].replace("Value error, ", "")

    return _error(request, 422, "validation_failed",
                  "Please check the highlighted fields.", field_errors=field_errors)


@app.get("/health", tags=["ops"])
def health(response: Response) -> dict:
    """Liveness plus a real database round-trip.

    503 when the database is unreachable. Railway's deploy check and any uptime
    monitor treat every 2xx as healthy, so a 200 here would route traffic to an
    instance that cannot save a single registration.
    """
    database_ok = True
    try:
        with connection() as conn:
            conn.execute("select 1")
    except Exception:  # noqa: BLE001
        logger.exception("Health check: database unreachable")
        database_ok = False

    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_ok else "degraded",
        "environment": settings.environment,
        "database": "up" if database_ok else "down",
        "whatsapp": "configured" if settings.whatsapp_enabled else "not_configured",
        # Who it may send to: off, allowlist or on. Never the numbers.
        "whatsapp_outbound": settings.whatsapp_outbound,
        # Twilio's webhooks are checked against the public address. Without it
        # they only verify when the API is called on its own address.
        "whatsapp_webhooks": "configured" if settings.public_api_url else "not_configured",
        "email": "configured" if settings.email_enabled else "not_configured",
        "staff_portal": "configured" if settings.staff_portal_enabled else "not_configured",
        "analytics": "configured" if settings.analytics_enabled else "not_configured",
        "error_tracking": "enabled" if _sentry_enabled else "disabled",
        "release": settings.release,
    }
