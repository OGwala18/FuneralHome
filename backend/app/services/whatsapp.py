"""WhatsApp confirmation via Twilio.

Two things drive the shape of this module:

1. A registration confirmation is *business-initiated*. Outside the 24-hour
   customer-service window WhatsApp only permits pre-approved template
   messages, so production sends must go through an approved Content template
   (TWILIO_CONTENT_SID). The free-text body path only works inside the Twilio
   sandbox or an open 24h window.

2. A messaging failure must never cost a lead. Every failure here is logged and
   swallowed: the enquiry is already committed before this is called.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import get_settings

logger = logging.getLogger(__name__)


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


def send_registration_confirmation(
    *, to_mobile: str, first_name: str, reference: str
) -> WhatsAppResult:
    """Send the post-registration confirmation. Never raises."""
    settings = get_settings()

    if not settings.whatsapp_enabled:
        # Dev default: log what would have gone out so the flow is still
        # observable end to end without Twilio credentials.
        logger.info(
            "WhatsApp not configured; would send to %s: reference %s", to_mobile, reference
        )
        return WhatsAppResult(sent=False, error="whatsapp_not_configured")

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
        logger.warning("WhatsApp send failed for reference %s: %s", reference, exc)
        return WhatsAppResult(sent=False, error=str(exc)[:200])
