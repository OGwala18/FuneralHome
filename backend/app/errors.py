"""Error codes: one stable name for every way a request or a notification fails.

WHY THIS FILE EXISTS
A ticket that says "the form didn't work" takes an hour to trace. One that says
`database_unavailable`, request `4f1c...`, 08:14 takes a minute, and the same
steps fix it every time. So every error response this API sends carries:

- `detail`      a sentence for the screen (what the site and portal show)
- `code`        a stable name from CATALOG below
- `request_id`  the same id as the response's X-Request-ID header and as the
                `[request_id]` in that request's log lines

Notifications that fail after a request has already succeeded (an email, a
WhatsApp) never reach the caller. They are recorded instead, as `*_failed`
events whose payload `error` is one of the codes below.

CATALOG is written for whoever triages a ticket, person or AI: what the code
means, where it comes from, the usual cause, the fix, and who acts on it.
Codes are append-only. Renaming one leaves every old ticket pointing nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException

# Who acts on it. "family": the person on the public site. "staff": an office
# user. "owner": settings only the owner holds (Railway, Supabase, mailbox).
# "developer": a code or schema change.
Actor = Literal["family", "staff", "owner", "developer"]


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    status: int | None      # HTTP status, or None for a recorded notification failure
    area: str               # where it comes from
    meaning: str
    likely_cause: str
    fix: str
    who: Actor
    retryable: bool = False


def _entries(*items: ErrorInfo) -> dict[str, ErrorInfo]:
    return {item.code: item for item in items}


CATALOG: dict[str, ErrorInfo] = _entries(
    # --- Any request -------------------------------------------------------------
    ErrorInfo("validation_failed", 422, "request validation (app/schemas.py)",
              "A field was missing or not in the allowed form.",
              "A typo by the person, or a site/portal build out of step with the API.",
              "The `field_errors` say which field. If many people hit the same field, "
              "compare the form with the schema.", "family"),
    ErrorInfo("bad_request", 400, "request parsing",
              "The request could not be read at all.",
              "Malformed JSON, or a client that is not our site or portal.",
              "Nothing, if it is one caller. Many: check a recent site release.", "developer"),
    ErrorInfo("request_too_large", 413, "request size limit (app/request_context.py)",
              "The request body is over MAX_REQUEST_BYTES.",
              "A script probing the API. No form of ours comes close.",
              "Nothing. Raise MAX_REQUEST_BYTES only for a real, new upload feature.",
              "developer"),
    ErrorInfo("not_signed_in", 401, "staff sign-in (app/auth.py)",
              "No staff token, or one that is expired or not ours.",
              "The session ended, or the request came from outside the portal.",
              "Sign in again. Every staff hitting it at once: check SUPABASE_URL on the API.",
              "staff"),
    ErrorInfo("forbidden", 403, "role check (app/auth.py require_role)",
              "Signed in, but the role does not allow this.",
              "A viewer tried a write, or an admin an owner-only action.",
              "The owner changes the role in Settings if the person should have it.",
              "owner"),
    ErrorInfo("not_found", 404, "routing / lookups",
              "No such address, or no such record.",
              "An old link, a deleted record, or a mistyped URL.",
              "Check the record still exists. Repeated from one place: fix the link.", "staff"),
    ErrorInfo("method_not_allowed", 405, "routing",
              "The address exists but not for this method.",
              "A client out of step with the API.", "Compare the caller with ARCHITECTURE.md §4.",
              "developer"),
    ErrorInfo("conflict", 409, "database constraints",
              "The change clashes with a record that already exists.",
              "A duplicate policy number, person or similar.",
              "Find the existing record; correct it rather than adding a second.", "staff"),
    ErrorInfo("rate_limited", 429, "rate limit (app/ratelimit.py)",
              "Too many requests from one connection in the window.",
              "A script, or many people on one shared network.",
              "Wait for Retry-After. Real families blocked: they phone or WhatsApp us.",
              "family", retryable=True),
    ErrorInfo("internal_error", 500, "unhandled exception",
              "A bug: the API did not expect what happened.",
              "Code. The traceback is in the API log under the same request_id.",
              "Find the request_id in the Railway log, fix the cause, add a test.",
              "developer"),
    ErrorInfo("database_unavailable", 503, "database connection (app/db.py)",
              "The API could not reach Postgres.",
              "Supabase paused or down, a wrong DATABASE_URL, or every pooled connection busy.",
              "Check /health, then the Supabase dashboard (is the project paused?) and "
              "the API's DATABASE_URL. Nothing was saved; the person must try again.",
              "owner", retryable=True),
    ErrorInfo("service_unavailable", 503, "a dependency is not configured",
              "Something this request needs is switched off on this server.",
              "A missing setting on Railway (see /health for which).",
              "Set the missing variable on the API service and redeploy.", "owner",
              retryable=True),
    ErrorInfo("upstream_failed", 502, "an outside service",
              "A service the API calls (mail, Twilio, Plausible) refused or failed.",
              "That service is down, or our credentials for it are wrong.",
              "Check the service's status page and the matching Railway variables.",
              "owner", retryable=True),

    ErrorInfo("network_unreachable", None, "the browser (site or portal), never the API",
              "The browser could not reach the API at all; no request id exists.",
              "The family's connection, the API down, DNS, or a CSP/CORS block after a "
              "new API address.",
              "Check /health and the uptime check first. Up: check the site's CSP and "
              "CORS_ORIGINS for the address the browser called.", "owner", retryable=True),

    # --- The public registration funnel ------------------------------------------
    ErrorInfo("enquiry_not_found", 404, "stage 2 (app/routers/enquiries.py)",
              "Stage 2 named an enquiry that does not exist or was archived.",
              "A stale browser tab, or the stage-1 row was archived.",
              "The person starts again from /register. Nothing to repair.", "family"),
    ErrorInfo("duplicate_id_number", 409, "stage 2, unique ID number index",
              "An application with this ID number already exists.",
              "The same person applying twice, or a mistyped ID matching someone else.",
              "Staff search the ID in the portal and phone the person back.", "staff"),
    ErrorInfo("idempotency_key_invalid", 400, "stage 1 Idempotency-Key header",
              "The Idempotency-Key header is not a UUID.",
              "A client that is not our site.", "Nothing.", "developer"),
    ErrorInfo("idempotency_mismatch", 422, "stage 1 Idempotency-Key header",
              "The same form attempt was re-sent with different details.",
              "A browser bug, or someone replaying a key.",
              "The person reloads the page and starts again.", "family"),

    # --- Staff two-step sign-in (existing codes, plan §8) ------------------------
    ErrorInfo("second_step_required", 403, "two-step gate (app/auth.py)",
              "Password accepted; the second step is still due.",
              "A new sign-in, or 12 hours passed.", "The portal shows the second step.", "staff"),
    ErrorInfo("two_step_not_configured", 503, "two-step gate (app/auth.py)",
              "Two-step is ON but its keys are missing, so nobody can get in.",
              "TWO_STEP_ENCRYPTION_KEYS or TWO_STEP_CODE_PEPPER unset on the API.",
              "Set both on Railway and redeploy; the log names which is missing.", "owner"),
    ErrorInfo("session_missing", 401, "two-step (app/routers/two_step.py)",
              "The token has no session to record the second step against.",
              "An old or hand-made token.", "Sign out and in again.", "staff"),
    ErrorInfo("too_many_attempts", 429, "two-step (app/routers/two_step.py)",
              "Too many wrong codes; locked for 15 minutes.",
              "Mistyped codes, or someone guessing.", "Wait, or the owner checks the staff log.",
              "staff", retryable=True),
    ErrorInfo("resend_too_soon", 429, "two-step (app/routers/two_step.py)",
              "A new code was asked for too soon after the last.",
              "Pressing resend repeatedly.", "Wait for Retry-After.", "staff", retryable=True),
    ErrorInfo("email_send_failed", 502, "two-step emailed code",
              "The sign-in code email did not go out.",
              "See the matching email_* event for the reason.",
              "Fix the mailbox settings; meanwhile use another second-step method.", "owner",
              retryable=True),

    # --- Email (recorded on *_email_failed events; app/services/email.py) -------
    ErrorInfo("email_not_configured", None, "email",
              "No SMTP_HOST on this server, so nothing was sent.",
              "Expected on a laptop. On Railway: SMTP_* variables missing.",
              "Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, MAIL_FROM.", "owner"),
    ErrorInfo("email_auth_required", None, "email",
              "The mail server refused to send without a login.",
              "SMTP_USERNAME / SMTP_PASSWORD missing on the API (the 12 Nov 2026 "
              "'550 SMTP AUTH is required').",
              "Set both on the API service and redeploy.", "owner", retryable=True),
    ErrorInfo("email_auth_failed", None, "email",
              "The mail server rejected the username or password.",
              "The mailbox password was changed or rotated.",
              "Update SMTP_PASSWORD on the API service and redeploy.", "owner",
              retryable=True),
    ErrorInfo("email_recipient_refused", None, "email",
              "The mail server would not deliver to this address.",
              "A mistyped applicant address, or MAIL_TO wrong.",
              "Applicant: phone them for the right address. Office: check MAIL_TO.", "staff"),
    ErrorInfo("email_sender_refused", None, "email",
              "The mail server would not send as MAIL_FROM.",
              "MAIL_FROM is not a mailbox this login may send as.",
              "Set MAIL_FROM to the login's own address.", "owner"),
    ErrorInfo("email_connect_failed", None, "email",
              "Could not connect to the mail server.",
              "Wrong SMTP_HOST/SMTP_PORT, or the mail host is down.",
              "Check the host and port (465 = SSL, 587 = STARTTLS).", "owner", retryable=True),
    ErrorInfo("email_timeout", None, "email",
              "The mail server did not answer in SMTP_TIMEOUT seconds.",
              "Mail host overloaded or blocking Railway's address.",
              "Retry later; persistent: ask the mail host.", "owner", retryable=True),
    ErrorInfo("email_tls_failed", None, "email",
              "The encrypted connection to the mail server failed.",
              "Port and mode mismatched, or the host's certificate is wrong.",
              "Use 465 for SSL or 587 for STARTTLS; check the certificate.", "owner",
              retryable=True),
    ErrorInfo("email_rejected", None, "email",
              "The mail server refused the message itself.",
              "Spam filtering, size, or a policy at the mail host.",
              "Read smtp_status on the event; ask the mail host.", "owner"),
    ErrorInfo("email_failed", None, "email",
              "Sending failed for a reason not classified above.",
              "Unknown; the API log has the exception type.",
              "Find the reference in the log; add a classification.", "developer"),

    # --- WhatsApp (recorded on whatsapp_failed events; app/services/whatsapp.py) -
    ErrorInfo("whatsapp_not_configured", None, "WhatsApp",
              "Twilio credentials missing, so nothing was sent.",
              "Expected on a laptop. On Railway: TWILIO_* variables missing.",
              "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM.", "owner"),
    ErrorInfo("whatsapp_outbound_off", None, "WhatsApp",
              "WHATSAPP_OUTBOUND is off, so no family is messaged.",
              "The safe default until the line is approved.",
              "Set WHATSAPP_OUTBOUND=on (production) when ready.", "owner"),
    ErrorInfo("whatsapp_not_allowlisted", None, "WhatsApp",
              "Allowlist mode, and this number is not on it.",
              "Expected on internal.", "Add the number to WHATSAPP_TEST_RECIPIENTS.", "owner"),
    ErrorInfo("whatsapp_unknown_number", None, "WhatsApp",
              "'known' mode, and nobody gave us this number.",
              "Working as designed.", "Nothing.", "owner"),
    ErrorInfo("whatsapp_failed", None, "WhatsApp",
              "The send failed for a reason not classified (not one of Twilio's codes).",
              "A bug in the sender, or a network fault reaching Twilio.",
              "Find the reference in the API log; the exception type is there.", "developer"),
    ErrorInfo("twilio_sdk_missing", None, "WhatsApp",
              "The twilio package is not installed.", "A broken image build.",
              "Rebuild from requirements.txt.", "developer"),
)

# Twilio's own numbered errors arrive as twilio_<number>. The common ones are
# named; https://www.twilio.com/docs/api/errors has the rest.
TWILIO_CODES: dict[str, str] = {
    "twilio_20003": "Twilio rejected our credentials: TWILIO_AUTH_TOKEN wrong or rotated.",
    "twilio_21211": "The number is not a valid phone number.",
    "twilio_21608": "Trial account: the number is not verified with Twilio.",
    "twilio_63003": "That number has no WhatsApp account.",
    "twilio_63016": "Outside the 24-hour window and no approved template (TWILIO_CONTENT_SID).",
    "twilio_63018": "Twilio rate limit for this sender.",
}

_BY_STATUS: dict[int, str] = {
    400: "bad_request", 401: "not_signed_in", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 413: "request_too_large",
    422: "validation_failed", 429: "rate_limited", 500: "internal_error",
    502: "upstream_failed", 503: "service_unavailable",
}


def code_for_status(status: int) -> str:
    """The generic code for an HTTP status, for errors raised without one."""
    if status in _BY_STATUS:
        return _BY_STATUS[status]
    return "internal_error" if status >= 500 else "bad_request"


def describe(code: str) -> ErrorInfo | None:
    """The catalog entry for a code; Twilio's numbered codes get a generic one."""
    if code in CATALOG:
        return CATALOG[code]
    if code.startswith("twilio_"):
        return ErrorInfo(code, None, "WhatsApp (Twilio)",
                         TWILIO_CODES.get(code, "Twilio refused the message."),
                         "See Twilio's error list for this number.",
                         "Look the number up at https://www.twilio.com/docs/api/errors.",
                         "owner")
    return None


class ApiError(HTTPException):
    """An HTTPException that names its catalog code.

    `detail` stays a sentence for the screen; `code` is what a client branches
    on and what a ticket is filed under. main.py renders both.
    """

    def __init__(self, status_code: int, code: str, detail: str,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
