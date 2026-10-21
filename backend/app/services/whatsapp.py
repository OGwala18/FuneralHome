"""WhatsApp confirmation via Twilio.

Two things drive the shape of this module:

1. A registration confirmation is *business-initiated*. Outside the 24-hour
   customer-service window WhatsApp only permits pre-approved template
   messages, so production sends must go through an approved Content template
   (TWILIO_CONTENT_SID). The free-text body path only works inside the Twilio
   sandbox or an open 24h window.

2. A messaging failure must never cost a lead. Every failure here is logged and
   swallowed: the enquiry is already committed before this is called.

Nothing goes out unless WHATSAPP_OUTBOUND allows it (outbound_refusal). Logs
carry the reference, never the number or Twilio's message text, which can
quote the number.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

# The Twilio library logs every API request it makes at INFO, and the request
# URL carries the account SID. Its warnings and errors still come through.
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)


@dataclass(frozen=True)
class WhatsAppResult:
    sent: bool
    message_sid: str | None = None
    error: str | None = None


def _plain_body(first_name: str, reference: str) -> str:
    return (
        f"Sawubona {first_name}, thank you for registering with Induduzo Funeral Home.\n\n"
        f"Your reference is {reference}.\n\n"
        "A family liaison will call you within one working day. "
        "We will never ask for your bank card details by message.\n\n"
        "Siyazazi Izingxaki Zakho."
    )


def outbound_refusal(settings: Settings, to_mobile: str) -> str | None:
    """Why WHATSAPP_OUTBOUND forbids a message to `to_mobile`, or None if it
    allows one. Every message the line sends asks this first."""
    if settings.whatsapp_outbound == "on":
        return None
    if settings.whatsapp_outbound == "allowlist":
        if to_mobile in settings.whatsapp_test_recipients:
            return None
        return "whatsapp_not_allowlisted"
    return "whatsapp_outbound_off"


def _failure_code(exc: Exception) -> str:
    """What went wrong, safe to log and store: Twilio's error code, never its
    message. A message like 21211's quotes the number it was sending to.

    The codes are listed at https://www.twilio.com/docs/api/errors.
    """
    code = getattr(exc, "code", None)  # set on TwilioRestException
    if isinstance(code, int):
        return f"twilio_{code}"
    return type(exc).__name__


def send_registration_confirmation(
    *, to_mobile: str, first_name: str, reference: str
) -> WhatsAppResult:
    """Send the post-registration confirmation. Never raises."""
    settings = get_settings()

    if not settings.whatsapp_enabled:
        # Dev default: log what would have gone out so the flow is still
        # observable end to end without Twilio credentials. The reference is
        # enough to find the row; the mobile number is personal information and
        # must not reach a log file (ARCHITECTURE.md rule 9).
        logger.info("WhatsApp not configured; would send confirmation for %s", reference)
        return WhatsAppResult(sent=False, error="whatsapp_not_configured")

    refusal = outbound_refusal(settings, to_mobile)
    if refusal:
        logger.info(
            "WhatsApp confirmation for %s not sent: %s (WHATSAPP_OUTBOUND=%s)",
            reference, refusal, settings.whatsapp_outbound,
        )
        return WhatsAppResult(sent=False, error=refusal)

    try:
        from twilio.rest import Client
    except ImportError:
        logger.warning("twilio package not installed; skipping WhatsApp send")
        return WhatsAppResult(sent=False, error="twilio_sdk_missing")

    try:
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

        params: dict = {
            "from_": f"whatsapp:{settings.twilio_whatsapp_from}",
            "to": f"whatsapp:{to_mobile}",
        }

        if settings.twilio_content_sid:
            # Production path: approved template. Variables are positional and
            # must match the template's placeholders.
            import json

            params["content_sid"] = settings.twilio_content_sid
            params["content_variables"] = json.dumps({"1": first_name, "2": reference})
        else:
            # Sandbox / within-24h path only.
            params["body"] = _plain_body(first_name, reference)

        message = client.messages.create(**params)
        logger.info("WhatsApp confirmation sent, sid=%s", message.sid)
        return WhatsAppResult(sent=True, message_sid=message.sid)

    except Exception as exc:  # noqa: BLE001 - a send failure must not fail the request
        code = _failure_code(exc)
        logger.warning("WhatsApp send failed for reference %s: %s", reference, code)
        return WhatsAppResult(sent=False, error=code)
