"""The WhatsApp line: Twilio's webhooks, and the staff screen's endpoints.

docs/feature-3-whatsapp-line.md. Two routers:

- `router`, /api/whatsapp: called by Twilio, not by people. Every request must
  carry a valid X-Twilio-Signature, made with the account's auth token, or it
  is refused. Without a token configured the endpoints answer 503 rather than
  accept anything unsigned.
- `admin_router`, /api/admin/whatsapp: the portal's WhatsApp screen under
  Growth. It lists only escalations, the conversations where a family asked
  for a person; everything else the menu handles stays out of sight.

Only an owner may send from the line: replying, and resolving (which can ask
the family for a rating). Decided by the owner on 27 Oct 2026, for now. Admins
and viewers read.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from ..auth import StaffUser, require_role, require_staff
from ..config import get_settings
from ..db import connection
from ..services import whatsapp, whatsapp_line as line
from ..services.staff import log_staff_event
from ..services.whatsapp_content import NODES
from ..services.whatsapp_menu import ESCALATED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])
admin_router = APIRouter(prefix="/api/admin/whatsapp", tags=["admin"],
                         dependencies=[Depends(require_staff)])

# An empty TwiML document: "received, nothing to say in this response". The
# menu's replies go out through the API afterwards, so each one is recorded and
# reports its own delivery.
_EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


# ---------------------------------------------------------------- Webhooks ---

async def _signed_form(request: Request) -> dict[str, str]:
    """The request's form fields, if Twilio signed them. 403 otherwise."""
    from twilio.request_validator import RequestValidator

    settings = get_settings()
    if not settings.twilio_auth_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "WhatsApp is not configured on this server.")

    form = dict(parse_qsl((await request.body()).decode("utf-8", "replace"),
                          keep_blank_values=True))

    # Behind Railway's proxy the URL the API sees isn't the one Twilio signed,
    # so it is rebuilt from the public address.
    if settings.public_api_url:
        url = settings.public_api_url + request.url.path
        if request.url.query:
            url += "?" + request.url.query
    else:
        url = str(request.url)

    signature = request.headers.get("x-twilio-signature", "")
    if not signature or not RequestValidator(settings.twilio_auth_token).validate(
            url, form, signature):
        logger.warning("WhatsApp webhook refused: bad or missing signature")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature.")
    return form


def _handle_inbound(message: line.Inbound) -> line.Delivery:
    with connection() as conn:
        return line.handle_inbound(conn, message)


@router.post("/inbound", include_in_schema=False)
async def inbound(request: Request, background: BackgroundTasks) -> Response:
    """A family's message. Stored, answered by the menu, and, if they ask for a
    person, handed to staff. Answers within a second or two: Twilio doesn't
    retry a webhook that fails or times out."""
    form = await _signed_form(request)
    message = line.parse_inbound(form)
    settings = get_settings()

    if message is None or message.from_number == settings.twilio_whatsapp_from:
        return Response(_EMPTY_TWIML, media_type="application/xml")

    delivery = await run_in_threadpool(_handle_inbound, message)
    # After commit, never before: the reply and the email must only go out for
    # a message that is safely stored.
    background.add_task(line.deliver, delivery)
    return Response(_EMPTY_TWIML, media_type="application/xml")


def _apply_status(sid: str, message_status: str, error_code: str | None) -> None:
    with connection() as conn:
        line.apply_status(conn, sid, message_status, error_code)


@router.post("/status", include_in_schema=False)
async def delivery_status(request: Request) -> Response:
    """Twilio reporting queued, sent, delivered, read or failed."""
    form = await _signed_form(request)
    sid = (form.get("MessageSid") or "").strip()
    if sid:
        await run_in_threadpool(_apply_status, sid, form.get("MessageStatus") or "",
                                form.get("ErrorCode") or None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------ Staff screen ---

class EscalationRow(BaseModel):
    id: UUID
    status: str
    channel: str
    topic: str
    topic_label: str
    urgent: bool
    out_of_hours: bool
    promised_for: datetime | None = None
    requested_at: datetime
    notified_at: datetime | None = None
    first_reply_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None
    name: str
    other_number: str
    profile_name: str | None = None
    enquiry_id: UUID | None = None
    enquiry_reference: str | None = None
    person_id: UUID | None = None
    member_name: str | None = None
    last_inbound_at: datetime | None = None
    # Free text is allowed until 24 hours after the family's last message.
    window_open: bool
    # Messages from the family since staff last wrote.
    unanswered: int = 0


class MessageRow(BaseModel):
    id: UUID
    direction: str
    # 'family', 'menu', 'system', or the staff member's email.
    author: str
    body: str | None = None
    media: list[dict] = []
    status: str
    error_code: str | None = None
    menu_node: str | None = None
    created_at: datetime


class EscalationDetail(EscalationRow):
    messages: list[MessageRow]


class Summary(BaseModel):
    open: int
    urgent: int
    oldest_requested_at: datetime | None = None


class ReplyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # WhatsApp through Twilio allows 1,600 characters.
    body: str = Field(min_length=1, max_length=1600)


class ResolveIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    note: str | None = Field(default=None, max_length=1000)
    # Ask the family to rate the help, if they wrote in the last 24 hours.
    ask_rating: bool = True


class TopicCount(BaseModel):
    topic: str
    label: str
    count: int


class FeedbackRow(BaseModel):
    rating: int | None = None
    comment: str | None = None
    topic_label: str
    created_at: datetime


class Stats(BaseModel):
    days: int
    conversations: int
    messages_in: int
    escalations: int
    open_escalations: int
    ratings: int
    average_rating: float | None = None
    top_answers: list[TopicCount]
    escalated_topics: list[TopicCount]
    recent_feedback: list[FeedbackRow]


_ESCALATION_SELECT = """
    select e.*, c.other_number, c.profile_name, c.last_inbound_at,
           c.enquiry_id, c.person_id,
           pe.reference as enquiry_reference,
           nullif(trim(coalesce(pe.first_name, '') || ' ' || coalesce(pe.surname, '')), '')
             as enquiry_name,
           nullif(trim(coalesce(p.first_names, '') || ' ' || coalesce(p.surname, '')), '')
             as member_name,
           (select count(*) from whatsapp_messages m
             where m.conversation_id = e.conversation_id
               and m.direction = 'inbound'
               and m.created_at > e.requested_at
               and m.created_at > coalesce(
                     (select max(s.created_at) from whatsapp_messages s
                       where s.conversation_id = e.conversation_id
                         and s.direction = 'outbound'
                         and s.author not in ('menu', 'system')),
                     '-infinity'::timestamptz)
           ) as unanswered
      from whatsapp_escalations e
      join whatsapp_conversations c on c.id = e.conversation_id
      left join plan_enquiries pe on pe.id = c.enquiry_id
      left join people p on p.id = c.person_id
"""


def _row(r: dict) -> dict:
    return {**r, "name": line.display_name(r),
            "window_open": line.window_open(r["last_inbound_at"])}


def _load(conn, escalation_id: UUID) -> dict:
    row = conn.execute(_ESCALATION_SELECT + " where e.id = %s", (escalation_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such conversation.")
    return row


@admin_router.get("/escalations/summary", response_model=Summary)
def summary() -> Summary:
    """For the badge on Growth. Polled, so not written to the audit trail: it
    holds counts only."""
    with connection() as conn:
        row = conn.execute(
            """
            select count(*) as open, count(*) filter (where urgent) as urgent,
                   min(requested_at) as oldest_requested_at
              from whatsapp_escalations where status = 'open'
            """
        ).fetchone()
    return Summary(**row)


@admin_router.get("/escalations", response_model=list[EscalationRow])
def list_escalations(staff: StaffUser = Depends(require_staff),
                     view: Literal["open", "resolved"] = "open",
                     limit: int = Query(default=50, ge=1, le=200)) -> list[EscalationRow]:
    order = ("e.urgent desc, e.requested_at asc" if view == "open"
             else "e.resolved_at desc")
    with connection() as conn:
        rows = conn.execute(
            _ESCALATION_SELECT + f" where e.status = %s order by {order} limit %s",
            (view, limit),
        ).fetchall()
        log_staff_event(conn, staff.email, "whatsapp_escalations_viewed", None,
                        {"view": view, "rows": len(rows)})
    return [EscalationRow(**_row(r)) for r in rows]


@admin_router.get("/escalations/{escalation_id}", response_model=EscalationDetail)
def get_escalation(escalation_id: UUID,
                   staff: StaffUser = Depends(require_staff)) -> EscalationDetail:
    """One escalated conversation, with its recent messages for context."""
    with connection() as conn:
        row = _load(conn, escalation_id)
        messages = conn.execute(
            """
            select * from (
              select id, direction, author, body, media, status, error_code,
                     menu_node, created_at
                from whatsapp_messages
               where conversation_id = %s
                 and created_at <= coalesce(%s, 'infinity'::timestamptz)
               order by created_at desc
               limit 100
            ) recent order by created_at asc
            """,
            (row["conversation_id"], row["resolved_at"]),
        ).fetchall()
        log_staff_event(conn, staff.email, "whatsapp_conversation_viewed",
                        str(escalation_id), {"messages": len(messages)})
    return EscalationDetail(**_row(row), messages=[MessageRow(**m) for m in messages])


_REFUSALS = {
    "whatsapp_not_allowlisted": (
        "This environment only sends WhatsApp messages to the test numbers "
        "(WHATSAPP_OUTBOUND=allowlist), and this number isn't one of them."),
    "whatsapp_outbound_off": "WhatsApp sending is switched off on this environment.",
    "whatsapp_not_configured": "WhatsApp is not configured on this server.",
}


@admin_router.post("/escalations/{escalation_id}/reply", response_model=MessageRow)
def reply(escalation_id: UUID, payload: ReplyIn,
          staff: StaffUser = Depends(require_role("owner"))) -> MessageRow:
    """Write to the family from the line's own number. Only on an open
    escalation, and only within 24 hours of their last message."""
    with connection() as conn:
        row = _load(conn, escalation_id)
    if row["status"] != "open":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This conversation is resolved. The family can message again to reopen it.")
    if not line.window_open(row["last_inbound_at"]):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "It's been more than 24 hours since they last wrote, so WhatsApp only "
            "allows approved templates. Please phone them instead.")

    result = whatsapp.send_text(to_mobile=row["other_number"], body=payload.body,
                                purpose="staff")
    with connection() as conn:
        message = line.record_outbound(
            conn, conversation_id=str(row["conversation_id"]), to_number=row["other_number"],
            body=payload.body, author=staff.email, result=result, node="staff",
            enquiry_id=str(row["enquiry_id"]) if row["enquiry_id"] else None)
        if result.sent:
            conn.execute(
                """
                update whatsapp_escalations
                   set first_reply_at = coalesce(first_reply_at, %s)
                 where id = %s
                """,
                (message["created_at"], escalation_id),
            )
            # Back to the person, not the menu, if the family had wandered off.
            conn.execute(
                "update whatsapp_conversations set state = %s where id = %s",
                (ESCALATED, row["conversation_id"]),
            )
        log_staff_event(conn, staff.email, "whatsapp_reply_sent", str(escalation_id),
                        {"sent": result.sent, "error": result.error})

    if not result.sent:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            _REFUSALS.get(result.error or "",
                          "WhatsApp didn't accept the message (%s). Try again, or phone them."
                          % (result.error or "unknown error")))
    return MessageRow(**message)


@admin_router.post("/escalations/{escalation_id}/resolve", response_model=EscalationRow)
def resolve(escalation_id: UUID, payload: ResolveIn, background: BackgroundTasks,
            staff: StaffUser = Depends(require_role("owner"))) -> EscalationRow:
    with connection() as conn:
        row = _load(conn, escalation_id)
        if row["status"] != "open":
            raise HTTPException(status.HTTP_409_CONFLICT, "This conversation is already resolved.")
        delivery = line.resolve(conn, row, staff_email=staff.email, note=payload.note,
                                ask_rating=payload.ask_rating)
        log_staff_event(conn, staff.email, "whatsapp_escalation_resolved", str(escalation_id),
                        {"asked_rating": bool(delivery.replies)})
        updated = _load(conn, escalation_id)
    background.add_task(line.deliver, delivery)
    return EscalationRow(**_row(updated))


@admin_router.get("/messages/{message_id}/media/{index}")
def media(message_id: UUID, index: int,
          staff: StaffUser = Depends(require_staff)) -> Response:
    """A photo or document a family sent, fetched from Twilio for the portal.
    Only in a conversation that was escalated: the rest isn't shown."""
    with connection() as conn:
        row = conn.execute(
            """
            select m.twilio_sid, m.media, m.conversation_id
              from whatsapp_messages m
             where m.id = %s and m.direction = 'inbound'
               and exists (select 1 from whatsapp_escalations e
                            where e.conversation_id = m.conversation_id)
            """,
            (message_id,),
        ).fetchone()
        if row is None or not (0 <= index < len(row["media"])):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attachment.")
        log_staff_event(conn, staff.email, "whatsapp_media_viewed", str(message_id),
                        {"index": index})

    fetched = whatsapp.fetch_media(row["twilio_sid"], row["media"][index]["sid"])
    if fetched is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Twilio no longer has this file, or it couldn't be fetched.")
    data, content_type = fetched
    return Response(data, media_type=content_type,
                    headers={"Cache-Control": "private, no-store"})


@admin_router.get("/stats", response_model=Stats)
def stats(days: int = Query(default=30, ge=1, le=365)) -> Stats:
    """Counts for the Growth page: how much the line is used, what families ask
    about, how they rate it. No numbers, and no message text except the
    comments families chose to leave with a rating."""
    with connection() as conn:
        totals = conn.execute(
            """
            select
              (select count(distinct conversation_id) from whatsapp_messages
                where direction = 'inbound' and created_at > now() - make_interval(days => %(d)s))
                as conversations,
              (select count(*) from whatsapp_messages
                where direction = 'inbound' and created_at > now() - make_interval(days => %(d)s))
                as messages_in,
              (select count(*) from whatsapp_escalations
                where requested_at > now() - make_interval(days => %(d)s)) as escalations,
              (select count(*) from whatsapp_escalations where status = 'open') as open_escalations,
              (select count(rating) from whatsapp_feedback
                where created_at > now() - make_interval(days => %(d)s)) as ratings,
              (select round(avg(rating)::numeric, 1) from whatsapp_feedback
                where created_at > now() - make_interval(days => %(d)s)) as average_rating
            """,
            {"d": days},
        ).fetchone()
        answers = conn.execute(
            """
            select menu_node as topic, count(*) as count from whatsapp_messages
             where direction = 'outbound' and author = 'menu'
               and created_at > now() - make_interval(days => %s)
               and menu_node = any(%s)
             group by menu_node order by count desc limit 8
            """,
            (days, [n.id for n in NODES.values() if n.kind == "answer"]),
        ).fetchall()
        escalated = conn.execute(
            """
            select topic, min(topic_label) as label, count(*) as count
              from whatsapp_escalations
             where requested_at > now() - make_interval(days => %s)
             group by topic order by count desc limit 8
            """,
            (days,),
        ).fetchall()
        feedback = conn.execute(
            """
            select rating, comment, topic, created_at from whatsapp_feedback
             where created_at > now() - make_interval(days => %s)
             order by created_at desc limit 10
            """,
            (days,),
        ).fetchall()

    return Stats(
        days=days,
        **{k: totals[k] for k in ("conversations", "messages_in", "escalations",
                                  "open_escalations", "ratings")},
        average_rating=float(totals["average_rating"]) if totals["average_rating"] is not None else None,
        top_answers=[TopicCount(topic=r["topic"], label=line.topic_label(r["topic"]), count=r["count"])
                     for r in answers],
        escalated_topics=[TopicCount(topic=r["topic"], label=r["label"], count=r["count"])
                          for r in escalated],
        recent_feedback=[FeedbackRow(rating=r["rating"], comment=r["comment"],
                                     topic_label=line.topic_label(r["topic"]), created_at=r["created_at"])
                         for r in feedback],
    )
