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

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_whatsapp_from
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
