"""Admin notification email.

Every enquiry is emailed to the office the moment stage 1 is submitted — before
the person has decided whether to finish the full application. That is the point
of the two-stage form: a half-finished enquiry is still a lead worth phoning.

Two rules shape this module:

1. **A mail failure must never cost a lead.** The row is already committed
   before this runs; every failure here is logged and swallowed.
2. **Enquiry content is untrusted.** Names and notes come from a public form, so
   every value is HTML-escaped before it reaches the HTML part. Without that,
   a note containing markup would render as markup in the office mailbox.
"""

from __future__ import annotations

import html
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailResult:
    sent: bool
    error: str | None = None


# Field label -> key in the enquiry dict. Ordered for how a human reads it.
_LEAD_FIELDS: list[tuple[str, str]] = [
    ("Name", "first_name"),
    ("Surname", "surname"),
    ("Mobile", "mobile_number"),
    ("Email", "email"),
    ("City", "city"),
    ("Suburb / area", "suburb_or_town"),
    ("Province", "province"),
    ("Preferred language", "language_preference"),
    ("Plan of interest", "plan_interest"),
    ("Best time to call", "best_contact_time"),
    ("How they heard of us", "how_heard"),
    ("Marketing opt-in", "marketing_consent"),
]

_APPLICATION_FIELDS: list[tuple[str, str]] = [
    ("ID number", "id_number"),
    ("Date of birth", "date_of_birth"),
    ("Marital status", "marital_status"),
    ("Address", "address_line1"),
    ("Address line 2", "address_line2"),
    ("Postal code", "postal_code"),
    ("Burial area", "cover_area"),
    ("Plan selected", "plan_selected"),
    ("Coffin choice", "coffin_choice"),
    ("Dependants", "number_of_dependants"),
    ("Payment preference", "payment_preference"),
    ("Next of kin", "next_of_kin_name"),
    ("Next of kin mobile", "next_of_kin_mobile"),
    ("Next of kin relationship", "next_of_kin_relationship"),
    ("Beneficiary", "beneficiary_name"),
    ("Beneficiary mobile", "beneficiary_mobile"),
    ("Beneficiary relationship", "beneficiary_relationship"),
    ("Notes", "notes"),
]


def _present(value: object) -> str:
    """Render a value for a human, collapsing empties to an em dash."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _build_message(
    *, subject: str, heading: str, intro: str, rows: list[tuple[str, str]], reference: str,
    sender_name: str = "Induduzo website", footer: str = "sent automatically by the Induduzo website.",
    urgent: bool = False,
) -> EmailMessage:
    settings = get_settings()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name, settings.mail_from))
    message["To"] = settings.mail_to
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="induduzo.co.za")
    # Lets the office thread stage 1 and stage 2 of the same enquiry together.
    message["X-Induduzo-Reference"] = reference
    if urgent:
        # Most mail programs show these as a red exclamation mark.
        message["X-Priority"] = "1"
        message["Importance"] = "high"

    plain_lines = [heading, "", intro, ""]
    plain_lines += ["%-26s %s" % (label + ":", value) for label, value in rows]
    plain_lines += ["", "Reference: %s" % reference]
    message.set_content("\n".join(plain_lines))

    # Every interpolated value is escaped: this content came from a public form.
    escaped = "".join(
        "<tr>"
        '<td style="padding:6px 14px 6px 0;color:#526170;white-space:nowrap;'
        'vertical-align:top">%s</td>'
        '<td style="padding:6px 0;color:#171C21"><strong>%s</strong></td>'
        "</tr>" % (html.escape(label), html.escape(value))
        for label, value in rows
    )

    message.add_alternative(
        "<html><body style=\"font-family:Segoe UI,Arial,sans-serif;color:#171C21\">"
        '<h2 style="color:#B7352F;margin:0 0 4px">%s</h2>'
        '<p style="color:#526170;margin:0 0 18px">%s</p>'
        '<table style="border-collapse:collapse;font-size:14px">%s</table>'
        '<p style="color:#526170;font-size:12px;margin-top:22px">'
        "Reference %s &middot; %s"
        "</p></body></html>"
        % (html.escape(heading), html.escape(intro), escaped, html.escape(reference),
           html.escape(footer)),
        subtype="html",
    )
    return message


def _send(message: EmailMessage) -> EmailResult:
    settings = get_settings()

    if not settings.email_enabled:
        # The reference, never the subject: the subject carries the applicant's
        # name (ARCHITECTURE.md rule 9).
        logger.info(
            "Email not configured; would have sent notification for %s to %s",
            message["X-Induduzo-Reference"],
            settings.mail_to,
        )
        return EmailResult(sent=False, error="email_not_configured")

    try:
        if settings.smtp_use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
            )
        else:
            server = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
            )
        with server:
            if settings.smtp_use_starttls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

        logger.info("Admin email sent for %s", message["X-Induduzo-Reference"])
        return EmailResult(sent=True)

    except Exception as exc:  # noqa: BLE001 - a mail failure must not fail the request
        # Deliberately logging neither the body nor the subject: the body is full
        # of personal data and the subject carries the applicant's name.
        logger.warning(
            "Admin email failed for %s: %s", message["X-Induduzo-Reference"], exc
        )
        return EmailResult(sent=False, error=str(exc)[:200])


def send_new_lead(enquiry: dict) -> EmailResult:
    """Stage 1. Sent whether or not the person goes on to complete stage 2."""
    reference = str(enquiry.get("reference", "unknown"))
    name = "%s %s" % (enquiry.get("first_name", ""), enquiry.get("surname", ""))
    rows = [(label, _present(enquiry.get(key))) for label, key in _LEAD_FIELDS]

    return _send(
        _build_message(
            subject="New enquiry: %s (%s)" % (name.strip(), reference),
            heading="New plan enquiry",
            intro=(
                "Captured from the website. This person has NOT yet completed the "
                "full application — follow up by phone."
            ),
            rows=rows,
            reference=reference,
        )
    )


def send_completed_application(enquiry: dict) -> EmailResult:
    """Stage 2. The full application, ready for a family liaison to action."""
    reference = str(enquiry.get("reference", "unknown"))
    name = "%s %s" % (enquiry.get("first_name", ""), enquiry.get("surname", ""))
    rows = [(label, _present(enquiry.get(key))) for label, key in _LEAD_FIELDS]
    rows += [(label, _present(enquiry.get(key))) for label, key in _APPLICATION_FIELDS]

    return _send(
        _build_message(
            subject="Application completed: %s (%s)" % (name.strip(), reference),
            heading="Application completed",
            intro="This person finished the full application and accepted the plan terms.",
            rows=rows,
            reference=reference,
        )
    )


def send_whatsapp_escalation(escalation: dict, name: str) -> EmailResult:
    """A family on WhatsApp asked for a person. The only WhatsApp email the
    office gets: menu answers are never emailed (docs/feature-3-whatsapp-line.md).

    `escalation` is services/whatsapp_line.escalation_details(). The subject
    carries the family's name, so it is never logged; the reference is the
    escalation id's first eight characters.
    """
    from datetime import timedelta, timezone

    settings = get_settings()
    reference = "WA-" + str(escalation["id"])[:8].upper()
    sast = timezone(timedelta(hours=2))
    number = escalation["other_number"]
    how = ("Reply to them on WhatsApp from the staff portal"
           if escalation["channel"] == "whatsapp" else "Phone them")

    link = ""
    if settings.portal_url:
        link = "%s/growth/whatsapp/%s" % (settings.portal_url, escalation["id"])

    rows = [
        ("Name", name),
        ("WhatsApp number", number),
        ("They asked for", "A WhatsApp reply" if escalation["channel"] == "whatsapp"
         else "A phone call"),
        ("About", escalation["topic_label"]),
        ("Asked at", escalation["requested_at"].astimezone(sast).strftime("%a %d %b %Y, %H:%M")),
    ]
    if escalation.get("out_of_hours") and escalation.get("promised_for"):
        rows.append(("Promised for", escalation["promised_for"].astimezone(sast)
                     .strftime("%a %d %b, %H:%M") + " (asked out of hours)"))
    if escalation.get("enquiry_reference"):
        rows.append(("Enquiry", escalation["enquiry_reference"]))
    if escalation.get("member_name"):
        rows.append(("Member", escalation["member_name"]))
    if link:
        rows.append(("Open in the portal", link))

    urgent = bool(escalation.get("urgent"))
    subject = ("URGENT – someone has passed away. WhatsApp from %s" % name if urgent
               else "Please respond: WhatsApp from %s" % name)
    intro = (
        "Please respond to %s (%s) using the staff portal, or call them. %s." % (name, number, how)
    )
    if urgent:
        intro += " They told the WhatsApp menu that someone has passed away."

    return _send(
        _build_message(
            subject=subject,
            heading="Someone has passed away: please phone now" if urgent
            else "A family asked to speak to a person",
            intro=intro,
            rows=rows,
            reference=reference,
            sender_name="Induduzo WhatsApp",
            footer="sent by the Induduzo WhatsApp line. Menu answers are never emailed, "
                   "only requests for a person.",
            urgent=urgent,
        )
    )
