"""Configuration, read from the environment only.

AIA foundation 03 §4.2: API keys and third-party secrets live in environment
variables. Never in the database, never in the repo, never in the frontend.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # The database is a separate service joined by a connection string.
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://induduzo:induduzo_local_dev@localhost:5433/induduzo",
    )

    environment: str = os.getenv("ENVIRONMENT", "development")

    # Browsers allowed to call this API. The Vite dev server runs on 8080.
    cors_origins: list[str] = field(
        default_factory=lambda: _split(
            os.getenv("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
        )
    )

    # Twilio WhatsApp. Absent in dev -> confirmations are logged, not sent, and
    # the registration still succeeds. A messaging outage must never cost a lead.
    twilio_account_sid: str | None = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_whatsapp_from: str | None = os.getenv("TWILIO_WHATSAPP_FROM")
    twilio_content_sid: str | None = os.getenv("TWILIO_CONTENT_SID")

    # Admin notification email. Same rule as WhatsApp: absent in dev means the
    # message is logged rather than sent, and the enquiry still succeeds.
    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_timeout: int = int(os.getenv("SMTP_TIMEOUT", "15"))
    mail_from: str = os.getenv("MAIL_FROM", "no-reply@induduzo.co.za")
    mail_to: str = os.getenv("MAIL_TO", "admin@induduzo.co.za")

    # --- Error tracking -----------------------------------------------------
    # A DSN is a write-only ingest endpoint, not a secret in the way an API key
    # is, but it still belongs in the environment rather than the repo.
    sentry_dsn: str | None = os.getenv("SENTRY_DSN")

    # Performance tracing is sampled because it is billed per transaction.
    # 0.1 = 10% of requests, which is plenty at this volume.
    sentry_traces_sample_rate: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    # Tags every event with the deployed commit, so an error can be traced to
    # the exact code that produced it. Railway and Netlify both expose this.
    release: str = os.getenv("RELEASE") or os.getenv("RAILWAY_GIT_COMMIT_SHA") or "dev"

    # --- Staff portal authentication ----------------------------------------
    # Supabase Auth issues the tokens; we only verify them against its public
    # JWKS. There is no shared secret here by design.
    supabase_url: str | None = os.getenv("SUPABASE_URL")

    # HIGHLY SENSITIVE. Can create accounts and read every user. Used only in
    # services/supabase_admin.py, server-side, and never returned or logged.
    # Optional: without it, staff invitations are created by hand instead.
    supabase_service_role_key: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # Bootstrap only. These addresses become owners on first sign-in IF the
    # staff table is empty; after that the table is the sole authority.
    staff_emails: frozenset[str] = field(
        default_factory=lambda: frozenset(
            e.strip().lower() for e in os.getenv("STAFF_EMAILS", "").split(",") if e.strip()
        )
    )

    @property
    def supabase_jwks_url(self) -> str | None:
        if not self.supabase_url:
            return None
        return self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str | None:
        if not self.supabase_url:
            return None
        return self.supabase_url.rstrip("/") + "/auth/v1"

    @property
    def staff_portal_enabled(self) -> bool:
        return bool(self.supabase_url and self.staff_emails)

    @property
    def smtp_use_ssl(self) -> bool:
        """Implicit TLS. Port 465 is SMTPS; 587 uses STARTTLS instead."""
        return os.getenv("SMTP_USE_SSL", "").lower() in {"1", "true", "yes"} or self.smtp_port == 465

    @property
    def smtp_use_starttls(self) -> bool:
        """TLS is on unless explicitly disabled.

        The opt-out exists ONLY for local mail catchers (MailHog, Mailpit, the
        test catcher in scratchpad), which speak plaintext on port 1025.
        Disabling it against a real mail host would send the mailbox password
        and every applicant's personal details in clear text over the network.
        """
        if os.getenv("SMTP_STARTTLS", "").lower() in {"0", "false", "no"}:
            return False
        # Never both: STARTTLS upgrades a plaintext connection, which is
        # meaningless on a socket that is already wrapped in TLS.
        return not self.smtp_use_ssl

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_whatsapp_from
        )

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.mail_to)


@lru_cache
def get_settings() -> Settings:
    return Settings()
