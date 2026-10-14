"""Shared setup for the API behaviour checks.

    cd backend
    DATABASE_URL=postgresql://induduzo_api:...@localhost:5433/induduzo python -m pytest

Point DATABASE_URL at a THROWAWAY database as the restricted API role, the way
production connects; never at Supabase or Railway. CI builds one from the
migrations with db/provision_api_role.py.

The environment is fixed here, before the app is imported, because config.py
reads every variable once at import time.
"""

from __future__ import annotations

import os

import psycopg
import pytest

if not os.getenv("DATABASE_URL"):
    pytest.exit(
        "Set DATABASE_URL to a throwaway database, connecting as induduzo_api.",
        returncode=2,
    )

# Empty, not absent. main.py's load_dotenv() never overrides a variable that is
# already set, so a developer's backend/.env cannot make a test run send a real
# email to the office or a real WhatsApp to a made-up number.
for _name in (
    "SMTP_HOST",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_FROM",
    "TWILIO_CONTENT_SID",
    "SENTRY_DSN",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "STAFF_EMAILS",
):
    os.environ[_name] = ""
os.environ["ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.ratelimit import application_limiter, lead_limiter  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # The context manager runs the lifespan, so the connection pool is opened
    # exactly as it is under Uvicorn.
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    # Every TestClient request comes from the same address, so without this the
    # seventh lead in a run is refused and the failure looks like a real bug.
    lead_limiter._hits.clear()
    application_limiter._hits.clear()


@pytest.fixture
def db():
    """A separate connection for checking what the API actually wrote."""
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        yield conn
