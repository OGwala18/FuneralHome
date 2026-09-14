"""Induduzo API.

One FastAPI service in front of the local Postgres. The public website talks
only to this; it never holds a database credential.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

from .config import get_settings  # noqa: E402  (must follow load_dotenv)
from .db import close_pool, connection, init_pool  # noqa: E402
from .observability import init_sentry  # noqa: E402
from .routers import admin, enquiries  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Before anything else, so errors raised during startup are captured too.
_sentry_enabled = init_sentry()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_pool()
    yield
    close_pool()


settings = get_settings()

_is_production = settings.environment.lower() == "production"

app = FastAPI(
    title="Induduzo Funeral Home API",
    version="0.1.0",
    description="Two-stage plan registration capture.",
    lifespan=lifespan,
    # In production the interactive docs are an inventory of every endpoint and
    # the full request schema. Useful locally, free reconnaissance in public.
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
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
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Send the same class of headers the website already gets from Netlify.

    The API returns JSON rather than HTML, so the set is narrower than a page
    needs — but nosniff and anti-framing still matter for any response a browser
    might be tricked into rendering, and HSTS matters once it is behind TLS.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    # An API serves no documents and needs no browser features.
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if _is_production:
        # Only in production: sending HSTS over plain HTTP in dev would pin
        # localhost to HTTPS in the browser and break the dev server.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(enquiries.router)
app.include_router(admin.router)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return field-level errors the form can attach to the right input.

    FastAPI's default shape is a list the browser cannot map back to fields;
    this flattens it to {field: message}.
    """
    field_errors: dict[str, str] = {}
    for error in exc.errors():
        location = [part for part in error["loc"] if part != "body"]
        if location:
            field_errors[str(location[0])] = error["msg"].replace("Value error, ", "")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Please check the highlighted fields.",
            "field_errors": field_errors,
        },
    )


@app.get("/health", tags=["ops"])
def health() -> dict:
    """Liveness plus a real database round-trip."""
    database_ok = True
    try:
        with connection() as conn:
            conn.execute("select 1")
    except Exception:  # noqa: BLE001
        logger.exception("Health check: database unreachable")
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "environment": settings.environment,
        "database": "up" if database_ok else "down",
        "whatsapp": "configured" if settings.whatsapp_enabled else "not_configured",
        "email": "configured" if settings.email_enabled else "not_configured",
        "staff_portal": "configured" if settings.staff_portal_enabled else "not_configured",
        "error_tracking": "enabled" if _sentry_enabled else "disabled",
        "release": settings.release,
    }
