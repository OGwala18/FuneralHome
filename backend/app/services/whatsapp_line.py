"""The WhatsApp line's records: conversations, messages, escalations, ratings.

docs/feature-3-whatsapp-line.md §4. A message from a family is stored first,
then the menu (services/whatsapp_menu.py) decides the reply, all in one
transaction under a lock on the conversation. Sending the replies and emailing
the office happen after the commit, in deliver() and notify(), and swallow
their own failures: a Twilio or mail outage must never lose a message.

Only an escalation, a family asking for a person, reaches staff. Every other
menu step is stored for the statistics and for context once a person is
involved, but is never emailed or listed in the portal on its own.

No message text and no phone number goes into a log line here. MessageSids,
row ids and menu node ids do.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import get_settings
from ..db import connection
from . import whatsapp, whatsapp_content as content, whatsapp_menu as menu
from .email import send_whatsapp_escalation
from .whatsapp_content import NODES

logger = logging.getLogger(__name__)

# Staff may write free text for this long after the family's last message.
# After that WhatsApp only accepts an approved template.
SERVICE_WINDOW = timedelta(hours=24)

# While a person is handling a conversation, a family writing again before
# anyone has replied hears back at most this often.
HOLDING_INTERVAL = timedelta(hours=1)

# Thirteen or more digits, allowing the spaces and dashes people type: a South
# African ID number is 13, a card number 16. Never stored, never forwarded.
_LONG_NUMBER = re.compile(r"(?<!\d)\d(?:[\s-]?\d){12,}(?!\d)")
REDACTED = "[number removed]"

_MEDIA_SID = re.compile(r"/Media/(ME[0-9a-fA-F]{32})")
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")

STAFF_AUTHORS_EXCLUDED = ("family", "menu", "system")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------- Inbound ---

@dataclass(frozen=True)
class Inbound:
    sid: str
    account_sid: str
    from_number: str
    to_number: str
    body: str
    profile_name: str | None
    media: list[dict]


def _bare(address: str | None) -> str:
    return (address or "").strip().removeprefix("whatsapp:")


def parse_inbound(form: dict[str, str]) -> Inbound | None:
    """Twilio's form fields, or None if this isn't a WhatsApp message we can use."""
    sid = (form.get("MessageSid") or form.get("SmsMessageSid") or "").strip()
    sender = _bare(form.get("From"))
    if not sid or not _E164.fullmatch(sender):
        return None
    media = []
    try:
        count = min(int(form.get("NumMedia") or 0), 10)
    except ValueError:
        count = 0
    for index in range(count):
        found = _MEDIA_SID.search(form.get(f"MediaUrl{index}") or "")
        if found:
            media.append({"sid": found.group(1),
                          "content_type": (form.get(f"MediaContentType{index}") or "")[:100]})
    return Inbound(
        sid=sid,
        account_sid=(form.get("AccountSid") or "").strip(),
        from_number=sender,
        to_number=_bare(form.get("To")),
        body=(form.get("Body") or "")[:4000],
        profile_name=((form.get("ProfileName") or "").strip()[:120] or None),
        media=media,
    )


def redact(body: str) -> tuple[str, bool]:
    cleaned = _LONG_NUMBER.sub(REDACTED, body)
    return cleaned, cleaned != body


@dataclass
class Delivery:
    """What to do once the transaction has committed."""
    conversation_id: str | None = None
    to_number: str | None = None
    enquiry_id: str | None = None
    replies: list[tuple[str, str | None]] = field(default_factory=list)  # (text, node)
    notify_escalation: str | None = None
    delete_twilio_copy: str | None = None


def _national_variants(number: str) -> list[str]:
    """The spellings an enquiry's mobile number may have been stored in."""
    if number.startswith("+27"):
        national = number[3:]
        return [number, "27" + national, "0" + national]
    return [number]


def _link(conn: Any, conv: dict) -> None:
    """Match the number to an enquiry and a member, once."""
    number = conv["other_number"]
    if conv["enquiry_id"] is None:
        row = conn.execute(
            """
            select id from plan_enquiries
             where archived_at is null and mobile_number = any(%s)
             order by created_at desc limit 1
            """,
            (_national_variants(number),),
        ).fetchone()
        if row:
            conv["enquiry_id"] = row["id"]
    if conv["person_id"] is None:
        row = conn.execute(
            """
            select person_id from person_phones
             where archived_at is null and number = %s
             order by is_primary desc, created_at desc limit 1
            """,
            (number,),
        ).fetchone()
        if row:
            conv["person_id"] = row["person_id"]


def _conversation(conn: Any, number: str, profile_name: str | None) -> dict:
    """The family's conversation, created if new, locked for this transaction."""
    row = conn.execute(
        """
        insert into whatsapp_conversations (other_number, profile_name)
        values (%s, %s)
        on conflict (tenant_id, other_number) do update
           set profile_name = coalesce(excluded.profile_name,
                                       whatsapp_conversations.profile_name)
        returning id
        """,
        (number, profile_name),
    ).fetchone()
    return conn.execute(
        "select * from whatsapp_conversations where id = %s for update", (row["id"],)
    ).fetchone()


def _open_escalation(conn: Any, conversation_id: Any) -> dict | None:
    return conn.execute(
        """
        select * from whatsapp_escalations
         where conversation_id = %s and status = 'open'
        """,
        (conversation_id,),
    ).fetchone()


def _last_staff_message_at(conn: Any, conversation_id: Any) -> datetime | None:
    row = conn.execute(
        """
        select max(created_at) as at from whatsapp_messages
         where conversation_id = %s and direction = 'outbound'
           and author <> all(%s)
        """,
        (conversation_id, list(STAFF_AUTHORS_EXCLUDED)),
    ).fetchone()
    return row["at"] if row else None


def topic_label(topic: str) -> str:
    if topic in NODES:
        return NODES[topic].title
    return {"compliment": "Compliment", "staff": "Help from staff"}.get(
        topic, topic.replace("_", " ").capitalize())


def _escalate(conn: Any, conv: dict, request: menu.Escalate, now: datetime,
              open_escalation: dict | None) -> str | None:
    """Open an escalation, or update the one already open. Returns its id if
    the office should be emailed now."""
    out_of_hours = not content.office_open(now)
    promised_for = content.next_opening(now) if out_of_hours else None

    if open_escalation:
        newly_urgent = request.urgent and not open_escalation["urgent"]
        conn.execute(
            """
            update whatsapp_escalations
               set channel = %s, topic = %s, topic_label = %s,
                   urgent = urgent or %s,
                   notified_at = case when %s then null else notified_at end
             where id = %s
            """,
            (request.channel, request.topic, topic_label(request.topic),
             request.urgent, newly_urgent, open_escalation["id"]),
        )
        return str(open_escalation["id"]) if newly_urgent else None

    row = conn.execute(
        """
        insert into whatsapp_escalations
          (conversation_id, channel, topic, topic_label, urgent,
           out_of_hours, promised_for, requested_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (conv["id"], request.channel, request.topic, topic_label(request.topic),
         request.urgent, out_of_hours, promised_for, now),
    ).fetchone()
    logger.info("WhatsApp escalation %s opened (%s, %s)", row["id"], request.topic,
                request.channel)
    return str(row["id"])


def _record_feedback(conn: Any, conv: dict, feedback: menu.Feedback,
                     escalation_id: str | None) -> None:
    if feedback.comment is not None and feedback.rating is None:
        # A comment after a rating belongs on that rating's row.
        updated = conn.execute(
            """
            update whatsapp_feedback set comment = %s
             where id = (select id from whatsapp_feedback
                          where conversation_id = %s and comment is null
                            and created_at > now() - interval '2 hours'
                          order by created_at desc limit 1)
            returning id
            """,
            (feedback.comment, conv["id"]),
        ).fetchone()
        if updated:
            return
    conn.execute(
        """
        insert into whatsapp_feedback (conversation_id, escalation_id, topic, rating, comment)
        values (%s, %s, %s, %s, %s)
        """,
        (conv["id"], escalation_id, feedback.topic, feedback.rating, feedback.comment),
    )


def handle_inbound(conn: Any, message: Inbound, now: datetime | None = None) -> Delivery:
    """Store a family's message and decide the reply. Inside one transaction."""
    now = now or _now()
    body, redacted = redact(message.body)

    conv = _conversation(conn, message.from_number, message.profile_name)
    stored = conn.execute(
        """
        insert into whatsapp_messages
          (conversation_id, direction, twilio_sid, author, business_number,
           other_number, body, media, menu_node, status, enquiry_id, created_at)
        values (%s, 'inbound', %s, 'family', %s, %s, %s, %s::jsonb, %s, 'received', %s, %s)
        on conflict (twilio_sid) do nothing
        returning id
        """,
        (conv["id"], message.sid, message.to_number, message.from_number, body,
         json.dumps(message.media), conv["state"], conv["enquiry_id"], now),
    ).fetchone()
    if stored is None:
        # Twilio delivered the same message twice. It has its answer already.
        logger.info("WhatsApp %s already stored", message.sid)
        return Delivery()

    _link(conn, conv)
    delivery = Delivery(conversation_id=str(conv["id"]), to_number=message.from_number,
                        enquiry_id=str(conv["enquiry_id"]) if conv["enquiry_id"] else None,
                        delete_twilio_copy=message.sid if redacted else None)

    words = menu.normalise(body)
    state, data, misses = conv["state"], dict(conv["data"] or {}), conv["misses"]
    opted_out_at = conv["opted_out_at"]
    open_escalation = _open_escalation(conn, conv["id"])
    turn: menu.Turn | None = None

    if opted_out_at is not None:
        if words == "start":
            opted_out_at = None
            turn = menu.respond(state=menu.IDLE, data={}, misses=0, text=body,
                                has_media=False, now=now, idle_since=None)
    elif words == "stop":
        opted_out_at = now
        turn = menu.Turn(replies=[content.STOPPED], state=menu.IDLE, node="stop")
    elif redacted:
        turn = menu.Turn(replies=[content.ID_NUMBER_REMOVED], state=state, data=data,
                         misses=misses, node="id_number_removed")
    elif open_escalation and state == menu.ESCALATED and words not in ("menu", "main menu"):
        # A person has this conversation. The menu stays out of the way, but
        # the family hears back if nobody has written for a while.
        last_staff = _last_staff_message_at(conn, conv["id"])
        held_at = datetime.fromisoformat(data["held_at"]) if data.get("held_at") else None
        quiet = last_staff is not None and now - last_staff < HOLDING_INTERVAL
        if not quiet and (held_at is None or now - held_at >= HOLDING_INTERVAL):
            data["held_at"] = now.isoformat()
            turn = menu.Turn(replies=[content.holding_text(now)], state=state, data=data,
                             node="holding")
        else:
            turn = menu.Turn(replies=[], state=state, data=data)
    else:
        turn = menu.respond(state=state, data=data, misses=misses, text=body,
                            has_media=bool(message.media), now=now,
                            idle_since=conv["last_message_at"] if conv["last_inbound_at"] else None)

    if turn is not None:
        state, data, misses = turn.state, turn.data, turn.misses
        if turn.escalate:
            delivery.notify_escalation = _escalate(conn, conv, turn.escalate, now,
                                                   open_escalation)
        if turn.feedback:
            _record_feedback(conn, conv, turn.feedback, data.get("escalation_id"))
        delivery.replies = [(text, turn.node) for text in turn.replies]

    conn.execute(
        """
        update whatsapp_conversations
           set state = %s, data = %s::jsonb, misses = %s, opted_out_at = %s,
               last_inbound_at = %s, last_message_at = %s,
               enquiry_id = %s, person_id = %s
         where id = %s
        """,
        (state, json.dumps(data), misses, opted_out_at, now, now,
         conv["enquiry_id"], conv["person_id"], conv["id"]),
    )
    logger.info("WhatsApp %s stored at %s -> %s", message.sid, conv["state"], state)
    return delivery


# ---------------------------------------------------------------- Outbound ---

def record_outbound(conn: Any, *, conversation_id: str | None, to_number: str,
                    body: str, author: str, result: whatsapp.WhatsAppResult,
                    node: str | None = None, enquiry_id: str | None = None) -> dict:
    settings = get_settings()
    now = _now()
    row = conn.execute(
        """
        insert into whatsapp_messages
          (conversation_id, direction, twilio_sid, author, business_number,
           other_number, body, menu_node, status, error_code, enquiry_id, created_at)
        values (%s, 'outbound', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (conversation_id, result.message_sid if result.sent else None, author,
         settings.twilio_whatsapp_from or "", to_number, body, node,
         "queued" if result.sent else "not_sent", None if result.sent else result.error,
         enquiry_id, now),
    ).fetchone()
    if conversation_id:
        conn.execute(
            "update whatsapp_conversations set last_message_at = %s where id = %s",
            (now, conversation_id),
        )
    return row


def deliver(delivery: Delivery) -> None:
    """After commit: send the menu's replies in order, record each, email the
    office about a new escalation, and delete Twilio's copy of a message that
    carried an ID number. Never raises."""
    try:
        for text, node in delivery.replies:
            result = whatsapp.send_text(to_mobile=delivery.to_number, body=text,
                                        purpose="menu")
            with connection() as conn:
                record_outbound(conn, conversation_id=delivery.conversation_id,
                                to_number=delivery.to_number, body=text, author="menu",
                                result=result, node=node, enquiry_id=delivery.enquiry_id)
        if delivery.delete_twilio_copy:
            whatsapp.delete_message(delivery.delete_twilio_copy)
    except Exception:  # noqa: BLE001
        logger.exception("Could not deliver WhatsApp replies for conversation %s",
                         delivery.conversation_id)
    if delivery.notify_escalation:
        notify(delivery.notify_escalation)


def record_confirmation(conn: Any, *, enquiry_id: str, to_number: str, body: str,
                        result: whatsapp.WhatsAppResult) -> None:
    """The registration confirmation, in the same table as everything else."""
    if not _E164.fullmatch(to_number):
        return
    conv = conn.execute(
        """
        insert into whatsapp_conversations (other_number, enquiry_id)
        values (%s, %s)
        on conflict (tenant_id, other_number) do update
           set enquiry_id = coalesce(whatsapp_conversations.enquiry_id, excluded.enquiry_id)
        returning id
        """,
        (to_number, enquiry_id),
    ).fetchone()
    record_outbound(conn, conversation_id=str(conv["id"]), to_number=to_number, body=body,
                    author="system", result=result, node="confirmation",
                    enquiry_id=enquiry_id)


# Delivery progress only moves forward; a late "sent" never overwrites "read".
_PROGRESS = ["not_sent", "queued", "sent", "delivered", "read"]
_FINAL_FAILURES = {"failed", "undelivered"}
_KNOWN = set(_PROGRESS) | _FINAL_FAILURES


def apply_status(conn: Any, sid: str, status: str, error_code: str | None) -> bool:
    """A Twilio status callback. True if it changed a row."""
    status = (status or "").strip().lower()
    if status == "accepted":
        status = "queued"
    if status not in _KNOWN:
        return False
    row = conn.execute(
        """
        select id, status from whatsapp_messages
         where twilio_sid = %s and direction = 'outbound' for update
        """,
        (sid,),
    ).fetchone()
    if row is None:
        return False
    current = row["status"]
    if status in _FINAL_FAILURES:
        if current == "read":
            return False
    elif current in _FINAL_FAILURES or (
            _PROGRESS.index(status) <= _PROGRESS.index(current)
            if current in _PROGRESS else False):
        return False
    conn.execute(
        "update whatsapp_messages set status = %s, error_code = coalesce(%s, error_code) where id = %s",
        (status, (error_code or None) and f"twilio_{error_code}"[:40], row["id"]),
    )
    return True


# ------------------------------------------------------------- Escalations ---

def escalation_details(conn: Any, escalation_id: str) -> dict | None:
    """An escalation with who it is, as staff see it."""
    return conn.execute(
        """
        select e.*, c.other_number, c.profile_name, c.last_inbound_at, c.state,
               c.enquiry_id, c.person_id,
               pe.reference as enquiry_reference,
               nullif(trim(coalesce(pe.first_name, '') || ' ' || coalesce(pe.surname, '')), '')
                 as enquiry_name,
               nullif(trim(coalesce(p.first_names, '') || ' ' || coalesce(p.surname, '')), '')
                 as member_name
          from whatsapp_escalations e
          join whatsapp_conversations c on c.id = e.conversation_id
          left join plan_enquiries pe on pe.id = c.enquiry_id
          left join people p on p.id = c.person_id
         where e.id = %s
        """,
        (escalation_id,),
    ).fetchone()


def display_name(row: dict) -> str:
    return (row.get("member_name") or row.get("enquiry_name")
            or row.get("profile_name") or row["other_number"])


def notify(escalation_id: str) -> None:
    """Email the office about an escalation. Never raises; the backfill job
    retries any that didn't go."""
    try:
        with connection() as conn:
            details = escalation_details(conn, escalation_id)
        if details is None:
            return
        result = send_whatsapp_escalation(details, display_name(details))
        with connection() as conn:
            conn.execute(
                """
                update whatsapp_escalations
                   set notified_at = case when %s then now() else notified_at end,
                       notify_error = %s
                 where id = %s
                """,
                (result.sent, None if result.sent else (result.error or "")[:200],
                 escalation_id),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not email WhatsApp escalation %s", escalation_id)


def window_open(last_inbound_at: datetime | None, now: datetime | None = None) -> bool:
    if last_inbound_at is None:
        return False
    return (now or _now()) - last_inbound_at < SERVICE_WINDOW


def resolve(conn: Any, escalation: dict, *, staff_email: str, note: str | None,
            ask_rating: bool, now: datetime | None = None) -> Delivery:
    """Close an escalation. The menu takes over the conversation again, and
    may ask the family to rate the help they had."""
    now = now or _now()
    conn.execute(
        """
        update whatsapp_escalations
           set status = 'resolved', resolved_at = %s, resolved_by = %s,
               resolution_note = %s
         where id = %s
        """,
        (now, staff_email, note, escalation["id"]),
    )
    delivery = Delivery(conversation_id=str(escalation["conversation_id"]),
                        to_number=escalation["other_number"],
                        enquiry_id=str(escalation["enquiry_id"]) if escalation["enquiry_id"] else None)
    asking = ask_rating and window_open(escalation["last_inbound_at"], now)
    if asking:
        delivery.replies = [(content.ASK_RATING_AFTER_STAFF, "staff")]
    conn.execute(
        "update whatsapp_conversations set state = %s, data = %s::jsonb, misses = 0 where id = %s",
        (menu.RATING if asking else menu.IDLE,
         json.dumps({"topic": "staff", "escalation_id": str(escalation["id"])} if asking else {}),
         escalation["conversation_id"]),
    )
    return delivery


# ------------------------------------------------------------- Safety net ---
# app/jobs/whatsapp_backfill.py runs these. Twilio doesn't retry a webhook
# that failed, and a mail server can be down when an escalation opens.

def retry_notifications(older_than: timedelta = timedelta(minutes=2)) -> tuple[int, int]:
    """Email the office about open escalations whose email didn't go.
    Returns (tried, sent)."""
    with connection() as conn:
        rows = conn.execute(
            """
            select id from whatsapp_escalations
             where status = 'open' and notified_at is null and requested_at < %s
             order by requested_at
            """,
            (_now() - older_than,),
        ).fetchall()
    for row in rows:
        notify(str(row["id"]))
    with connection() as conn:
        still = conn.execute(
            "select count(*) as n from whatsapp_escalations where id = any(%s) and notified_at is null",
            ([r["id"] for r in rows],),
        ).fetchone()["n"]
    return len(rows), len(rows) - still


def backfill(since: datetime) -> tuple[int, int]:
    """Store messages families sent since `since` that the webhook never saw,
    for example while the API was restarting. They get no menu reply: it
    would arrive late and out of order. Returns (seen, stored)."""
    settings = get_settings()
    if not settings.whatsapp_enabled:
        return 0, 0
    from twilio.rest import Client

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    seen = stored = 0
    for item in client.messages.list(to=f"whatsapp:{settings.twilio_whatsapp_from}",
                                     date_sent_after=since, limit=500):
        if not str(getattr(item, "direction", "")).startswith("inbound"):
            continue
        seen += 1
        sender = _bare(item.from_)
        if not _E164.fullmatch(sender):
            continue
        media = []
        if int(getattr(item, "num_media", 0) or 0):
            media = [{"sid": m.sid, "content_type": (m.content_type or "")[:100]}
                     for m in client.messages(item.sid).media.list(limit=10)]
        body, redacted = redact(item.body or "")
        with connection() as conn:
            conv = _conversation(conn, sender, None)
            row = conn.execute(
                """
                insert into whatsapp_messages
                  (conversation_id, direction, twilio_sid, author, business_number,
                   other_number, body, media, menu_node, status, created_at)
                values (%s, 'inbound', %s, 'family', %s, %s, %s, %s::jsonb, 'backfilled',
                        'received', coalesce(%s, now()))
                on conflict (twilio_sid) do nothing
                returning id
                """,
                (conv["id"], item.sid, settings.twilio_whatsapp_from, sender, body,
                 json.dumps(media), item.date_sent),
            ).fetchone()
        if row:
            stored += 1
            logger.info("WhatsApp %s backfilled", item.sid)
            if redacted:
                whatsapp.delete_message(item.sid)
    return seen, stored
