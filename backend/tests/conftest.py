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
    "WHATSAPP_OUTBOUND",
    "WHATSAPP_TEST_RECIPIENTS",
    "PUBLIC_API_URL",
    "SENTRY_DSN",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "STAFF_EMAILS",
    "PLAUSIBLE_API_KEY",
):
    os.environ[_name] = ""
os.environ["ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import StaffUser, require_staff  # noqa: E402
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
def staff_as():
    """Sign requests in as a staff member with the given role.

    Replaces require_staff, the one dependency every admin route and every
    require_role() check is built on, so the role gate itself is still the real
    one. Removed again after the test, so the anonymous checks stay anonymous.
    """
    def sign_in(role: str = "admin") -> StaffUser:
        user = StaffUser(user_id="00000000-0000-0000-0000-0000000000aa",
                         email=f"{role}@staff.test", role=role,
                         staff_id="00000000-0000-0000-0000-0000000000bb")
        app.dependency_overrides[require_staff] = lambda: user
        return user

    yield sign_in
    app.dependency_overrides.pop(require_staff, None)


@pytest.fixture
def db():
    """A separate connection for checking what the API actually wrote."""
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        yield conn


# --- Two-step sign-in (plan §11B) -------------------------------------------------
#
# These sign in the REAL way: a genuine ES256 token checked by the real
# require_staff_identity and require_staff, with only the key lookup stubbed.
# staff_as above stays for the role tests, which don't care about the second step.

import dataclasses  # noqa: E402
import time as _time  # noqa: E402
import uuid as _uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import jwt as _jwt  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from app import auth as _auth  # noqa: E402
from app.config import get_settings as _real_get_settings  # noqa: E402
from app.routers import two_step as _two_step_router  # noqa: E402
from app.services import email as _email  # noqa: E402
from app.services import two_step as _two_step  # noqa: E402

TEST_SUPABASE_URL = "https://two-step-test.supabase.test"
_SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())


class _StubJwks:
    """Stands in for Supabase's JWKS: every token is checked against our test key."""

    class _Key:
        key = _SIGNING_KEY.public_key()

    def get_signing_key_from_jwt(self, _token):
        return self._Key()


def _two_step_settings(enforcement: str, configured: bool = True):
    extra = (
        {
            "two_step_encryption_keys": [Fernet.generate_key().decode()],
            "two_step_code_pepper": "test-pepper-" + "x" * 32,
            "webauthn_rp_id": "localhost",
            "webauthn_origins": ["http://localhost:8081"],
        }
        if configured
        else {"two_step_encryption_keys": [], "two_step_code_pepper": None}
    )
    return dataclasses.replace(
        _real_get_settings(),
        supabase_url=TEST_SUPABASE_URL,
        two_step_enforcement=enforcement,
        **extra,
    )


@pytest.fixture
def two_step(monkeypatch):
    """Switch the second step on or off for this test, as the server would be.

    two_step("on") / two_step("off") / two_step("on", configured=False).
    """
    def switch(enforcement: str = "on", configured: bool = True):
        settings = _two_step_settings(enforcement, configured)
        for module in (_auth, _two_step_router):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        monkeypatch.setattr(_auth, "_client", lambda: _StubJwks())
        return settings

    return switch


@pytest.fixture
def signed_in(two_step, db):
    """Mint a real token for a real staff row: signed_in(role, session_id=...).

    Returns (headers, staff_id, session_id). The staff row is created fresh, so
    tests never share a person. Enforcement defaults to ON unless the test
    already called two_step().
    """
    if _auth.get_settings is _real_get_settings:
        two_step("on")

    def sign_in(role: str = "admin", session_id: str | None = None, email: str | None = None):
        email = email or f"two-step-{_uuid.uuid4().hex[:10]}@staff.test"
        session_id = session_id or str(_uuid.uuid4())
        # Signing in again as an existing person (a second session) reuses the row.
        existing = db.execute(
            "select id, supabase_user_id from staff_users where email = %s", (email,)
        ).fetchone()
        if existing:
            staff_id, subject = existing[0], str(existing[1])
        else:
            subject = str(_uuid.uuid4())
            staff_id = db.execute(
                """
                insert into staff_users (email, role, is_active, supabase_user_id, invited_by)
                values (%s, %s, true, %s, 'test') returning id
                """,
                (email, role, subject),
            ).fetchone()[0]
        token = _jwt.encode(
            {
                "sub": subject,
                "email": email,
                "aud": "authenticated",
                "iss": TEST_SUPABASE_URL + "/auth/v1",
                "exp": int(_time.time()) + 3600,
                "iat": int(_time.time()),
                "session_id": session_id,
            },
            _SIGNING_KEY,
            algorithm="ES256",
        )
        return {"Authorization": f"Bearer {token}"}, str(staff_id), session_id

    return sign_in


@pytest.fixture
def clock(monkeypatch):
    """The two-step clock, frozen and movable: clock.advance(hours=12)."""

    class Clock:
        def __init__(self):
            self.at = datetime.now(timezone.utc).replace(microsecond=0)

        def __call__(self):
            return self.at

        def advance(self, **delta):
            from datetime import timedelta
            self.at += timedelta(**delta)

    c = Clock()
    monkeypatch.setattr(_two_step, "now", c)
    return c


@pytest.fixture
def smtp_sink(monkeypatch):
    """A real SMTP conversation, login included, with tests/smtp_sink.py.

    `mailbox` below proves what the API asked to send; this proves it gets
    through smtplib to a server. sink.mode makes the server fail on purpose;
    sink.settings is what the email module now reads, for tests that change it.
    """
    from smtp_sink import SmtpSink

    sink = SmtpSink().start()
    sink.settings = dataclasses.replace(
        _real_get_settings(),
        smtp_host=sink.host, smtp_port=sink.port,
        smtp_username=sink.username, smtp_password=sink.password,
        smtp_timeout=2, mail_from="website@induduzo.test", mail_to="office@induduzo.test",
    )
    monkeypatch.setattr(_email, "get_settings", lambda: sink.settings)
    # Plain text to 127.0.0.1 only; the opt-out config.py keeps for mail catchers.
    monkeypatch.setenv("SMTP_STARTTLS", "0")
    yield sink
    sink.stop()


@pytest.fixture
def mailbox(monkeypatch):
    """Every email the API sends lands in this list instead of an SMTP server."""
    sent: list = []

    def capture(message):
        sent.append(message)
        return _email.EmailResult(sent=True)

    monkeypatch.setattr(_email, "_send", capture)
    return sent
