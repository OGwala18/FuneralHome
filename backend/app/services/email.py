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
from datetime import datetime, timedelta, timezone
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


# --- A new member's welcome --------------------------------------------------------

def send_member_welcome(*, to_email: str, first_name: str, policy_number: str,
                        review_url: str | None) -> EmailResult:
    """Welcome a newly enrolled member by email. A notification: never raises.

    Goes to the member, not the office. The policy number is the reference
    _send logs; the address and name never reach a log.
    """
    settings = get_settings()
    name = (first_name or "").split(" ")[0] or "there"
    message = EmailMessage()
    message["Subject"] = "Welcome to the Induduzo family"
    message["From"] = formataddr(("Induduzo Funeral Home", settings.mail_from))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="induduzo.co.za")
    message["X-Induduzo-Reference"] = policy_number

    review_plain = (f"\nIf you have a moment, we'd be grateful for a Google review:\n"
                    f"{review_url}\n") if review_url else ""
    message.set_content(
        f"Hello {name},\n\n"
        "You've been successfully added to the Induduzo family, and it's great to have you.\n\n"
        f"Your policy number is {policy_number}. Please use it as the reference whenever "
        "you pay, and keep it somewhere safe.\n\n"
        "Your cover starts once your first premium is received, and a 3-month waiting "
        "period applies to natural causes.\n"
        f"{review_plain}\n"
        "Induduzo Funeral Home - Siyazazi Izingxaki Zakho\n"
        "WhatsApp 073 731 0521 | 082 954 9241 | info@induduzo.co.za\n"
    )
    review_html = (f'<p><a href="{html.escape(review_url)}">Leave us a Google review</a>'
                   "</p>") if review_url else ""
    message.add_alternative(
        '<html><body style="font-family:Segoe UI,Arial,sans-serif;color:#171C21">'
        f"<p>Hello {html.escape(name)},</p>"
        "<p><strong>You've been successfully added to the Induduzo family</strong>, and "
        "it's great to have you.</p>"
        f"<p>Your policy number is <strong>{html.escape(policy_number)}</strong>. Please use "
        "it as the reference whenever you pay, and keep it somewhere safe.</p>"
        "<p style=\"color:#526170\">Your cover starts once your first premium is received, "
        "and a 3-month waiting period applies to natural causes.</p>"
        f"{review_html}"
        '<p style="color:#526170;font-size:12px">Induduzo Funeral Home &middot; '
        "Siyazazi Izingxaki Zakho &middot; WhatsApp 073 731 0521</p></body></html>",
        subtype="html",
    )
    return _send(message)


# --- Staff sign-in code (2FA Bit 5; plan §9 "Emailed code") ------------------------

# South Africa has no daylight saving, so a fixed offset is exact all year.
_SAST = timezone(timedelta(hours=2), "SAST")


def send_sign_in_code(to_email: str, code: str, expires_at: datetime) -> EmailResult:
    """Email a staff member their sign-in code, inside the request.

    Not a background task: the person is waiting and must be told if it failed.
    Sent only to the address on the staff record. The subject never contains the
    code (lock-screen previews), there are no links, and nothing here is logged
    except the fixed reference "sign-in-code".
    """
    settings = get_settings()
    until = expires_at.astimezone(_SAST).strftime("%H:%M")

    message = EmailMessage()
    message["Subject"] = "Your Induduzo sign-in code"
    message["From"] = formataddr(("Induduzo Staff Portal", settings.mail_from))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="induduzo.co.za")
    # What _send logs. Never the address or the code.
    message["X-Induduzo-Reference"] = "sign-in-code"

    message.set_content(
        "Your Induduzo sign-in code is:\n\n"
        f"    {code}\n\n"
        f"It is valid until {until} (5 minutes) and works once.\n\n"
        "If this wasn't you, someone may know your password. Tell the owner.\n"
    )
    message.add_alternative(
        '<html><body style="font-family:Segoe UI,Arial,sans-serif;color:#171C21">'
        '<p style="margin:0 0 12px">Your Induduzo sign-in code is:</p>'
        '<p style="font-size:30px;letter-spacing:6px;font-weight:700;margin:0 0 12px">'
        f"{html.escape(code)}</p>"
        f'<p style="color:#526170;margin:0 0 18px">Valid until {html.escape(until)} '
        "(5 minutes). It works once.</p>"
        '<p style="color:#B7352F;margin:0">If this wasn\'t you, someone may know your '
        "password. Tell the owner.</p></body></html>",
        subtype="html",
    )
    return _send(message)
