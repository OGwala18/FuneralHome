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
from .routers import enquiries  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_pool()
    yield
    close_pool()


settings = get_settings()

app = FastAPI(
    title="Induduzo Funeral Home API",
    version="0.1.0",
    description="Two-stage plan registration capture.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(enquiries.router)


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
    }
