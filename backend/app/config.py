"""Configuration, read from the environment only.

AIA foundation 03 §4.2: API keys and third-party secrets live in environment
variables. Never in the database, never in the repo, never in the frontend.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

# The pepper keys the HMAC that emailed and recovery codes are stored as. Any
# shorter and it adds too little to stop a stolen copy of the database being
# used to guess codes offline.
MIN_PEPPER_BYTES = 32

# Who an outbound WhatsApp may go to: nobody, the test numbers, or anyone.
WHATSAPP_OUTBOUND_MODES = ("off", "allowlist", "on")

_E164_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _phone_numbers(value: str) -> frozenset[str]:
    """Comma-separated numbers, with the spaces and dashes people type taken
    out, so "+27 82 000 0001" matches the +27820000001 the API stores."""
    return frozenset(re.sub(r"[\s()-]", "", item) for item in _split(value))


def _is_fernet_key(key: str) -> bool:
    """Whether Fernet would accept `key`: 32 bytes, url-safe base64.

    Checked here, so a mistyped key reads as "not configured" rather than as an
    error inside the first request that needs it.
    """
    try:
        return len(base64.urlsafe_b64decode(key)) == 32
    except ValueError:  # binascii.Error is a ValueError
        return False


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

    # Who a WhatsApp from the line may go to: "off" (nobody), "allowlist" (only
    # WHATSAPP_TEST_RECIPIENTS) or "on" (anyone). docs/feature-3-whatsapp-line.md
    # §7. Unset means "off": credentials alone never start messaging families,
    # so an environment sends only once someone has chosen to. Internal uses
    # "allowlist", so a test never reaches a real family; production uses "on".
    whatsapp_outbound: str = (os.getenv("WHATSAPP_OUTBOUND") or "off").strip().lower()

    # Comma-separated E.164 numbers: staff phones, internal only. Personal
    # data, so kept out of repr() and never logged.
    whatsapp_test_recipients: frozenset[str] = field(
        default_factory=lambda: _phone_numbers(os.getenv("WHATSAPP_TEST_RECIPIENTS", "")),
        repr=False,
    )

    # The API's public address, e.g. https://<service>.up.railway.app.
    # Behind Railway's proxy the request URL is not the one Twilio signed, so
    # the webhook signature check rebuilds it from this.
    public_api_url: str | None = (os.getenv("PUBLIC_API_URL") or "").strip().rstrip("/") or None

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

    # --- Staff two-step sign-in ---------------------------------------------
    # docs/feature-2-staff-two-factor.md §7. Internal and production each
    # have their own keys and pepper, and never share them.

    # "on" or "off". Production refuses to start with it off (__post_init__),
    # so a forgotten variable fails loudly instead of leaving the door open.
    two_step_enforcement: str = (os.getenv("TWO_STEP_ENFORCEMENT") or "off").strip().lower()

    # SEALED. Fernet keys, comma-separated. The first one encrypts
    # authenticator-app secrets and every one decrypts, so a key is rotated by
    # putting a new one first. Kept out of repr(), like the pepper.
    two_step_encryption_keys: list[str] = field(
        default_factory=lambda: _split(os.getenv("TWO_STEP_ENCRYPTION_KEYS", "")),
        repr=False,
    )

    # SEALED. Keys the HMAC that emailed and recovery codes are stored as. It
    # lives here and never in the database, so a stolen copy of the database
    # can't be used to guess codes offline.
    two_step_code_pepper: str | None = field(
        default=os.getenv("TWO_STEP_CODE_PEPPER") or None, repr=False
    )

    # Passkeys. The RP ID is the portal's bare domain: localhost,
    # portal-internal.up.railway.app or portal.induduzo.co.za. A passkey only
    # ever works on the domain it was made for, so production's is set once,
    # at launch, and never changed.
    webauthn_rp_id: str | None = os.getenv("WEBAUTHN_RP_ID") or None
    # Shown in the passkey prompt.
    webauthn_rp_name: str = os.getenv("WEBAUTHN_RP_NAME") or "Induduzo Staff Portal"
    # The exact portal origins a passkey may be used from.
    webauthn_origins: list[str] = field(
        default_factory=lambda: _split(os.getenv("WEBAUTHN_ORIGINS", ""))
    )

    def __post_init__(self) -> None:
        # Refuse to start rather than run in a state nobody chose. Every
        # entrypoint builds these settings before it serves or changes anything.
        if self.two_step_enforcement not in ("on", "off"):
            raise ValueError("TWO_STEP_ENFORCEMENT must be 'on' or 'off'.")
        if self.two_step_enforcement == "off" and self.environment.strip().lower() == "production":
            raise RuntimeError(
                "TWO_STEP_ENFORCEMENT is off and ENVIRONMENT is production. Staff "
                "sign-in in production must ask for a second step, so the API "
                "will not start. Set TWO_STEP_ENFORCEMENT=on."
            )
        if self.whatsapp_outbound not in WHATSAPP_OUTBOUND_MODES:
            raise ValueError("WHATSAPP_OUTBOUND must be 'off', 'allowlist' or 'on'.")
        # A number in any other form could never match, so the allowlist would
        # quietly send to nobody. The message names the setting, not the
        # numbers, which are personal.
        if not all(_E164_RE.fullmatch(number) for number in self.whatsapp_test_recipients):
            raise ValueError(
                "WHATSAPP_TEST_RECIPIENTS must be E.164 numbers, comma-separated: "
                "a + and the country code (+27), with no leading 0."
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

    @property
    def two_step_enforced(self) -> bool:
        return self.two_step_enforcement == "on"

    @property
    def two_step_missing(self) -> list[str]:
        """The two-step settings that are absent or unusable, by name.

        Empty means two-step sign-in is fully configured. Names only, never
        values, so the list is safe to log.

        This is how enforcement fails closed (§7): with enforcement on and
        anything listed here, staff routes must answer 503 "Two-step sign-in is
        not configured", never let someone in on a password alone.
        """
        missing = []
        keys = self.two_step_encryption_keys
        if not keys or not all(_is_fernet_key(key) for key in keys):
            missing.append("TWO_STEP_ENCRYPTION_KEYS")
        if len((self.two_step_code_pepper or "").encode("utf-8")) < MIN_PEPPER_BYTES:
            missing.append("TWO_STEP_CODE_PEPPER")
        if not self.webauthn_rp_id:
            missing.append("WEBAUTHN_RP_ID")
        if not self.webauthn_rp_name.strip():
            missing.append("WEBAUTHN_RP_NAME")
        if not self.webauthn_origins:
            missing.append("WEBAUTHN_ORIGINS")
        return missing

    @property
    def two_step_configured(self) -> bool:
        return not self.two_step_missing


@lru_cache
def get_settings() -> Settings:
    return Settings()
