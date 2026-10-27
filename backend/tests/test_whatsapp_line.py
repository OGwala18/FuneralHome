"""The WhatsApp line end to end: Twilio's webhooks, storing, the menu,
escalations, the office email and the staff screen.
docs/feature-3-whatsapp-line.md §9.

Nothing leaves the process. Twilio's Client is a fake that records what it was
asked to send, and the office email is a fake that records what it was asked
to say. Requests are signed the way Twilio signs them, with a made-up token.

Each test uses its own made-up family number, so conversations never mix.
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import twilio.rest
from twilio.request_validator import RequestValidator

from app.config import Settings
from app.routers import whatsapp as whatsapp_router
from app.services import email, whatsapp, whatsapp_line
from app.services import whatsapp_content as content
from app.services.email import EmailResult
from app.services.whatsapp_content import SAST

ACCOUNT_SID = "AC" + "0" * 30 + "f1"
TOKEN = "made-up-auth-token"
LINE = "+27820000000"
PUBLIC = "https://api.test"

# A Tuesday morning and a Saturday afternoon.
OPEN = datetime(2026, 10, 27, 10, 0, tzinfo=SAST)
CLOSED = datetime(2026, 10, 31, 14, 0, tzinfo=SAST)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "twilio_account_sid": ACCOUNT_SID,
        "twilio_auth_token": TOKEN,
        "twilio_whatsapp_from": LINE,
        "twilio_content_sid": "HX" + "0" * 32,
        "whatsapp_outbound": "on",
        "whatsapp_test_recipients": frozenset(),
        "public_api_url": PUBLIC,
        "portal_url": "https://portal.test",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def use(monkeypatch):
    """Run the line with these settings instead of the environment's."""
    def apply(**overrides) -> Settings:
        settings = _settings(**overrides)
        for module in (whatsapp, whatsapp_line, whatsapp_router, email):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        return settings

    apply()
    return apply


class Clock:
    """The line's clock. Each reading moves it on a second, so messages keep
    their order in the transcript."""

    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def at(self, moment: datetime) -> None:
        self.now = moment

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)

    def read(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(whatsapp_line, "_now", c.read)
    return c


class FakeTwilio:
    """Stands in for twilio.rest.Client: records sends and deletes."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[str] = []
        # What messages.list() returns, and each message's media, for the backfill.
        self.history: list[SimpleNamespace] = []
        self.media: dict[str, list[SimpleNamespace]] = {}

    def client(self, account_sid: str, auth_token: str) -> SimpleNamespace:
        fake = self

        class Messages:
            def create(self, **params):
                fake.sent.append(params)
                return SimpleNamespace(sid="SM" + uuid.uuid4().hex)

            def list(self, **filters):
                return list(fake.history)

            def __call__(self, sid):
                return SimpleNamespace(
                    delete=lambda: fake.deleted.append(sid) or True,
                    media=SimpleNamespace(list=lambda limit=10: fake.media.get(sid, [])),
                )

        return SimpleNamespace(messages=Messages())

    def to(self, number: str) -> list[str]:
        return [m["body"] for m in self.sent if m["to"] == f"whatsapp:{number}"]


@pytest.fixture
def fake_twilio(monkeypatch) -> FakeTwilio:
    fake = FakeTwilio()
    monkeypatch.setattr(twilio.rest, "Client", fake.client)
    return fake


@pytest.fixture
def mailbox(monkeypatch) -> list[tuple[dict, str]]:
    sent: list[tuple[dict, str]] = []

    def fake_send(details: dict, name: str) -> EmailResult:
        sent.append((dict(details), name))
        return EmailResult(sent=True)

    monkeypatch.setattr(whatsapp_line, "send_whatsapp_escalation", fake_send)
    return sent


@pytest.fixture
def family() -> str:
    return "+2782%07d" % random.randint(1000000, 9999999)


@pytest.fixture
def line(use, clock, fake_twilio, mailbox):
    return SimpleNamespace(use=use, clock=clock, twilio=fake_twilio, mailbox=mailbox)


def _sign(path: str, form: dict) -> str:
    return RequestValidator(TOKEN).compute_signature(PUBLIC + path, form)


def send(client, number: str, body: str = "", *, sid: str | None = None,
         media: tuple[str, ...] = (), signature: str | None = None):
    """Post a family's message the way Twilio does."""
    sid = sid or "SM" + uuid.uuid4().hex
    form = {
        "MessageSid": sid,
        "AccountSid": ACCOUNT_SID,
        "From": f"whatsapp:{number}",
        "To": f"whatsapp:{LINE}",
        "Body": body,
        "NumMedia": str(len(media)),
        "ProfileName": "Thandi Test",
    }
    for i, content_type in enumerate(media):
        form[f"MediaUrl{i}"] = (f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}"
                                f"/Messages/{sid}/Media/ME{uuid.uuid4().hex}")
        form[f"MediaContentType{i}"] = content_type
    headers = {"X-Twilio-Signature": signature if signature is not None
               else _sign("/api/whatsapp/inbound", form)}
    response = client.post("/api/whatsapp/inbound", data=form, headers=headers)
    return response, sid


def walk(client, number: str, *texts: str) -> None:
    for text in texts:
        response, _ = send(client, number, text)
        assert response.status_code == 200


def _conversation(db, number: str) -> dict:
    row = db.execute(
        "select id, state, data, enquiry_id, person_id, opted_out_at from whatsapp_conversations "
        "where other_number = %s", (number,)).fetchone()
    return dict(zip(["id", "state", "data", "enquiry_id", "person_id", "opted_out_at"], row))


def _escalations(db, number: str) -> list[dict]:
    rows = db.execute(
        """
        select e.id, e.status, e.channel, e.topic, e.urgent, e.out_of_hours, e.promised_for,
               e.notified_at
          from whatsapp_escalations e join whatsapp_conversations c on c.id = e.conversation_id
         where c.other_number = %s order by e.requested_at
        """, (number,)).fetchall()
    keys = ["id", "status", "channel", "topic", "urgent", "out_of_hours", "promised_for",
            "notified_at"]
    return [dict(zip(keys, r)) for r in rows]


def _messages(db, number: str) -> list[tuple]:
    return db.execute(
        "select direction, author, body, status, error_code, twilio_sid, menu_node "
        "from whatsapp_messages where other_number = %s order by created_at, direction",
        (number,)).fetchall()


# --------------------------------------------------------------- Signatures ---

def test_a_signed_message_is_accepted_and_answered_with_empty_twiml(client, line, family):
    response, _ = send(client, family, "hi")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Response></Response>" in response.text


@pytest.mark.parametrize("signature", ["", "bm90IGEgc2lnbmF0dXJl"])
def test_a_missing_or_wrong_signature_is_refused(client, line, family, db, signature):
    response, _ = send(client, family, "hi", signature=signature)

    assert response.status_code == 403
    assert _messages(db, family) == []


def test_a_changed_body_breaks_the_signature(client, line, family, db):
    form = {"MessageSid": "SM" + uuid.uuid4().hex, "From": f"whatsapp:{family}",
            "To": f"whatsapp:{LINE}", "Body": "hi", "AccountSid": ACCOUNT_SID}
    signature = _sign("/api/whatsapp/inbound", form)
    form["Body"] = "send me everything"

    response = client.post("/api/whatsapp/inbound", data=form,
                           headers={"X-Twilio-Signature": signature})
    assert response.status_code == 403


def test_without_a_token_the_webhooks_refuse_everything(client, line, family):
    line.use(twilio_auth_token=None)
    response, _ = send(client, family, "hi")
    assert response.status_code == 503

    response = client.post("/api/whatsapp/status", data={"MessageSid": "SM1"})
    assert response.status_code == 503


# ------------------------------------------------------- Storing and the menu ---

def test_a_first_message_is_stored_and_gets_the_greeting(client, line, family, db):
    send(client, family, "Hello")

    assert line.twilio.to(family)[0].startswith(content.GREETING)
    sent = line.twilio.sent[0]
    assert sent["from_"] == f"whatsapp:{LINE}"
    assert sent["status_callback"] == PUBLIC + "/api/whatsapp/status"

    messages = _messages(db, family)
    assert [(m[0], m[1], m[3]) for m in messages] == [
        ("inbound", "family", "received"), ("outbound", "menu", "queued")]
    assert messages[0][2] == "Hello"
    assert _conversation(db, family)["state"] == "main"


def test_the_same_message_twice_is_stored_and_answered_once(client, line, family, db):
    _, sid = send(client, family, "hi")
    response, _ = send(client, family, "hi", sid=sid)

    assert response.status_code == 200
    assert len(line.twilio.to(family)) == 1
    assert len(_messages(db, family)) == 2


def test_the_menu_answers_from_the_stored_step(client, line, family, db):
    walk(client, family, "hi", "5", "1")   # Plans -> Plan A

    assert "Plan A (Urban)" in line.twilio.to(family)[-1]
    assert _conversation(db, family)["state"] == "plans.a"
    assert _messages(db, family)[-1][6] == "plans.a"


def test_a_message_from_the_line_itself_is_ignored(client, line, db):
    response, _ = send(client, LINE, "hi")
    assert response.status_code == 200
    assert line.twilio.sent == []


def test_a_number_that_matches_an_enquiry_and_a_member_is_linked(client, line, family, db):
    national = "0" + family[3:]
    response = client.post("/api/enquiries", json={
        "first_name": "Thandiwe", "surname": "Test", "mobile_number": national,
        "plan_interest": "plan_a", "contact_consent": True})
    assert response.status_code == 201

    walk(client, family, "hi")
    assert str(_conversation(db, family)["enquiry_id"]) == response.json()["id"]


def test_an_unknown_number_is_still_stored_and_answered(client, line, family, db):
    walk(client, family, "hi")
    conversation = _conversation(db, family)
    assert conversation["enquiry_id"] is None
    assert line.twilio.to(family)


# -------------------------------------------------------------- Escalations ---

def test_asking_for_a_person_opens_an_escalation_and_emails_once(client, line, family, db):
    line.clock.at(OPEN)
    walk(client, family, "hi", "2", "5", "2")   # Claims -> None of these -> WhatsApp me

    [escalation] = _escalations(db, family)
    assert escalation["status"] == "open"
    assert escalation["channel"] == "whatsapp"
    assert escalation["topic"] == "claims"
    assert not escalation["urgent"] and not escalation["out_of_hours"]
    assert escalation["notified_at"] is not None

    [(details, name)] = line.mailbox
    assert details["other_number"] == family
    assert details["topic_label"] == "Claims and payouts"
    assert name == "Thandi Test"
    assert "as soon as possible" in line.twilio.to(family)[-1]
    assert _conversation(db, family)["state"] == "escalated"


def test_menu_answers_alone_are_never_emailed(client, line, family, db):
    walk(client, family, "hi", "2", "1", "1", "5", "Thanks")
    assert line.mailbox == []
    assert _escalations(db, family) == []


def test_out_of_hours_the_escalation_promises_the_next_opening(client, line, family, db):
    line.clock.at(CLOSED)
    walk(client, family, "hi", "3", "5", "3")

    [escalation] = _escalations(db, family)
    assert escalation["out_of_hours"]
    assert escalation["promised_for"] == datetime(2026, 11, 2, 8, 0, tzinfo=SAST)
    assert "at 08:00 on Monday" in line.twilio.to(family)[-1]


def test_a_bereavement_is_urgent(client, line, family, db):
    line.clock.at(CLOSED)
    walk(client, family, "hi", "1", "1")

    [escalation] = _escalations(db, family)
    assert escalation["urgent"] and escalation["channel"] == "call"
    assert line.mailbox[0][0]["urgent"]
    assert content.PHONES_24H in line.twilio.to(family)[-1]


def test_while_a_person_has_it_the_menu_is_quiet_but_not_silent(client, line, family, db):
    line.clock.at(OPEN)
    walk(client, family, "hi", "2", "5", "2")
    replies = len(line.twilio.to(family))

    line.clock.advance(minutes=5)
    walk(client, family, "My mother's claim from June")
    assert len(line.twilio.to(family)) == replies + 1
    assert "we have your message" in line.twilio.to(family)[-1]

    line.clock.advance(minutes=5)
    walk(client, family, "Hello?")
    assert len(line.twilio.to(family)) == replies + 1   # at most once an hour

    line.clock.advance(minutes=61)
    walk(client, family, "Anyone there?")
    assert len(line.twilio.to(family)) == replies + 2


def test_menu_during_an_escalation_goes_back_without_closing_it(client, line, family, db):
    line.clock.at(OPEN)
    walk(client, family, "hi", "2", "5", "2", "menu")
    assert content.GREETING in line.twilio.to(family)[-1]

    # Asking again updates the open escalation; the office isn't emailed twice.
    walk(client, family, "3", "5", "3")
    [escalation] = _escalations(db, family)
    assert escalation["channel"] == "call" and escalation["topic"] == "pay"
    assert len(line.mailbox) == 1


def test_a_bereavement_on_an_open_escalation_makes_it_urgent_and_emails_again(
        client, line, family, db):
    line.clock.at(OPEN)
    walk(client, family, "hi", "2", "5", "2", "menu", "1", "1")
    [escalation] = _escalations(db, family)
    assert escalation["urgent"]
    assert len(line.mailbox) == 2


def test_a_failed_email_is_left_for_the_backfill_to_retry(client, line, family, db, monkeypatch):
    monkeypatch.setattr(whatsapp_line, "send_whatsapp_escalation",
                        lambda details, name: EmailResult(sent=False, error="smtp down"))
    walk(client, family, "hi", "2", "5", "2")
    [escalation] = _escalations(db, family)
    assert escalation["notified_at"] is None


# ------------------------------------------------------ STOP and ID numbers ---

def test_stop_switches_replies_off_and_start_back_on(client, line, family, db):
    walk(client, family, "hi", "STOP")
    assert line.twilio.to(family)[-1] == content.STOPPED
    assert _conversation(db, family)["opted_out_at"] is not None

    count = len(line.twilio.sent)
    walk(client, family, "2", "hello")
    assert len(line.twilio.sent) == count
    assert len([m for m in _messages(db, family) if m[0] == "inbound"]) == 4

    walk(client, family, "start")
    assert line.twilio.to(family)[-1].startswith(content.GREETING)
    assert _conversation(db, family)["opted_out_at"] is None


@pytest.mark.parametrize("typed", ["1234567890123", "123456 7890 123", "4111-1111-1111-1111"])
def test_an_id_or_card_number_is_never_stored(client, line, family, db, typed):
    walk(client, family, "hi")
    _, sid = send(client, family, f"my number is {typed} thanks")

    bodies = [m[2] for m in _messages(db, family) if m[0] == "inbound"]
    assert bodies[-1] == "my number is [number removed] thanks"
    assert line.twilio.to(family)[-1] == content.ID_NUMBER_REMOVED
    assert sid in line.twilio.deleted
    assert _conversation(db, family)["state"] == "main"


# --------------------------------------------------------------- Allowlist ---

def test_on_allowlist_a_number_off_the_list_gets_no_reply(client, line, family, db):
    line.use(whatsapp_outbound="allowlist", whatsapp_test_recipients=frozenset({"+27820000001"}))
    walk(client, family, "hi", "2", "5", "2")

    assert line.twilio.to(family) == []
    outbound = [m for m in _messages(db, family) if m[0] == "outbound"]
    assert outbound and all(m[3] == "not_sent" and m[4] == "whatsapp_not_allowlisted"
                            for m in outbound)
    # It is still stored and still reaches the office.
    assert len(_escalations(db, family)) == 1


def test_on_allowlist_a_listed_number_is_answered(client, line, family):
    line.use(whatsapp_outbound="allowlist", whatsapp_test_recipients=frozenset({family}))
    walk(client, family, "hi")
    assert line.twilio.to(family)


# --------------------------------------------------------- Status callbacks ---

def _status(client, sid: str, status: str, error_code: str | None = None):
    form = {"MessageSid": sid, "MessageStatus": status, "AccountSid": ACCOUNT_SID}
    if error_code:
        form["ErrorCode"] = error_code
    return client.post("/api/whatsapp/status", data=form,
                       headers={"X-Twilio-Signature": _sign("/api/whatsapp/status", form)})


def _outbound_status(db, sid: str) -> tuple:
    return db.execute("select status, error_code from whatsapp_messages where twilio_sid = %s",
                      (sid,)).fetchone()


def test_status_callbacks_move_a_message_forward_only(client, line, family, db):
    walk(client, family, "hi")
    sid = [m[5] for m in _messages(db, family) if m[0] == "outbound"][0]

    assert _status(client, sid, "sent").status_code == 204
    assert _status(client, sid, "delivered").status_code == 204
    assert _outbound_status(db, sid) == ("delivered", None)

    _status(client, sid, "sent")                 # late, out of order
    assert _outbound_status(db, sid)[0] == "delivered"

    _status(client, sid, "read")
    _status(client, sid, "failed", "63016")      # can't fail after being read
    assert _outbound_status(db, sid)[0] == "read"


def test_a_failure_is_recorded_with_its_code(client, line, family, db):
    walk(client, family, "hi")
    sid = [m[5] for m in _messages(db, family) if m[0] == "outbound"][0]
    _status(client, sid, "undelivered", "63024")
    assert _outbound_status(db, sid) == ("undelivered", "twilio_63024")


def test_an_unsigned_status_callback_is_refused(client, line):
    response = client.post("/api/whatsapp/status", data={"MessageSid": "SMx", "MessageStatus": "read"})
    assert response.status_code == 403


# ------------------------------------------------------------ Staff screen ---

def _escalate(client, line, number: str) -> str:
    line.clock.at(datetime.now(timezone.utc))
    walk(client, number, "hi", "2", "5", "2")
    escalations = client.get("/api/admin/whatsapp/escalations").json()
    return next(e["id"] for e in escalations if e["other_number"] == number)


def test_staff_see_only_escalated_conversations(client, line, family, staff_as):
    staff_as("viewer")
    quiet = "+2782%07d" % random.randint(1000000, 9999999)
    walk(client, quiet, "hi", "5", "1")          # menu only
    escalation_id = _escalate(client, line, family)

    rows = client.get("/api/admin/whatsapp/escalations").json()
    numbers = {r["other_number"] for r in rows}
    assert family in numbers and quiet not in numbers

    row = next(r for r in rows if r["id"] == escalation_id)
    assert row["window_open"] is True
    assert row["topic_label"] == "Claims and payouts"

    summary = client.get("/api/admin/whatsapp/escalations/summary").json()
    assert summary["open"] >= 1


def test_the_conversation_shows_the_menu_steps_for_context(client, line, family, staff_as):
    staff_as("viewer")
    escalation_id = _escalate(client, line, family)

    detail = client.get(f"/api/admin/whatsapp/escalations/{escalation_id}").json()
    authors = [m["author"] for m in detail["messages"]]
    assert authors[:2] == ["family", "menu"]
    assert detail["messages"][0]["body"] == "hi"


@pytest.mark.parametrize("role", ["viewer", "admin"])
def test_only_an_owner_can_reply_or_resolve(client, line, family, staff_as, role):
    staff_as("owner")
    escalation_id = _escalate(client, line, family)
    staff_as(role)

    assert client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/reply",
                       json={"body": "Hello"}).status_code == 403
    assert client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/resolve",
                       json={}).status_code == 403


def test_staff_reply_from_the_line_and_are_recorded(client, line, family, staff_as, db):
    owner = staff_as("owner")
    escalation_id = _escalate(client, line, family)

    response = client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/reply",
                           json={"body": "Sawubona, this is the Induduzo office."})
    assert response.status_code == 200
    assert response.json()["author"] == owner.email

    assert line.twilio.to(family)[-1] == "Sawubona, this is the Induduzo office."
    first_reply = db.execute("select first_reply_at from whatsapp_escalations where id = %s",
                             (escalation_id,)).fetchone()[0]
    assert first_reply is not None

    # After a staff reply the family's next message gets no holding reply.
    count = len(line.twilio.to(family))
    walk(client, family, "Thank you, I will wait for your call")
    assert len(line.twilio.to(family)) == count


def test_a_reply_after_24_hours_is_refused(client, line, family, staff_as):
    staff_as("owner")
    escalation_id = _escalate(client, line, family)
    line.clock.advance(hours=25)

    response = client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/reply",
                           json={"body": "Hello"})
    assert response.status_code == 409
    assert "24 hours" in response.json()["detail"]


def test_a_reply_the_allowlist_refuses_says_why(client, line, family, staff_as, db):
    staff_as("owner")
    escalation_id = _escalate(client, line, family)
    line.use(whatsapp_outbound="allowlist", whatsapp_test_recipients=frozenset())

    response = client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/reply",
                           json={"body": "Hello"})
    assert response.status_code == 502
    assert "test numbers" in response.json()["detail"]


def test_resolving_asks_for_a_rating_and_stores_it(client, line, family, staff_as, db):
    staff_as("owner")
    escalation_id = _escalate(client, line, family)

    response = client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/resolve",
                           json={"note": "Phoned her, claim documents explained"})
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert line.twilio.to(family)[-1] == content.ASK_RATING_AFTER_STAFF

    walk(client, family, "5")
    rating, linked = db.execute(
        "select rating, escalation_id from whatsapp_feedback f "
        "join whatsapp_conversations c on c.id = f.conversation_id where c.other_number = %s",
        (family,)).fetchone()
    assert rating == 5 and str(linked) == escalation_id

    open_ids = {r["id"] for r in client.get("/api/admin/whatsapp/escalations").json()}
    assert escalation_id not in open_ids
    assert client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/reply",
                       json={"body": "Hello"}).status_code == 409


def test_after_resolving_the_menu_takes_over_again(client, line, family, staff_as):
    staff_as("owner")
    escalation_id = _escalate(client, line, family)
    client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/resolve",
                json={"ask_rating": False})

    walk(client, family, "hi")
    assert line.twilio.to(family)[-1].startswith(content.GREETING)


def test_attachments_are_shown_only_once_escalated(client, line, family, staff_as, db, monkeypatch):
    staff_as("viewer")
    monkeypatch.setattr(whatsapp, "fetch_media", lambda sid, media_sid: (b"\xff\xd8jpeg", "image/jpeg"))
    walk(client, family, "hi")
    send(client, family, "", media=("image/jpeg",))
    message_id = db.execute(
        "select id from whatsapp_messages where other_number = %s and media <> '[]'::jsonb",
        (family,)).fetchone()[0]

    assert client.get(f"/api/admin/whatsapp/messages/{message_id}/media/0").status_code == 404

    _escalate(client, line, family)
    response = client.get(f"/api/admin/whatsapp/messages/{message_id}/media/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/admin/whatsapp/messages/{message_id}/media/1").status_code == 404


def test_the_statistics_count_without_naming_anyone(client, line, family, staff_as):
    staff_as("viewer")
    walk(client, family, "hi", "5", "1", "1", "4", "Clear and quick")

    stats = client.get("/api/admin/whatsapp/stats").json()
    assert stats["conversations"] >= 1
    assert any(t["topic"] == "plans.a" for t in stats["top_answers"])
    assert any(f["comment"] == "Clear and quick" and f["rating"] == 4
               for f in stats["recent_feedback"])
    assert family not in str(stats)


# ------------------------------------------------------- The office email ---

def test_the_escalation_email_says_who_how_and_links_to_the_portal(use, monkeypatch, family):
    captured = []
    monkeypatch.setattr(email, "_send", lambda message: captured.append(message) or EmailResult(sent=True))
    escalation_id = uuid.uuid4()
    details = {
        "id": escalation_id, "other_number": family, "channel": "call", "urgent": True,
        "topic_label": "Someone has passed away", "requested_at": OPEN,
        "out_of_hours": False, "promised_for": None, "enquiry_reference": "IND-2026-001234",
        "member_name": None,
    }
    email.send_whatsapp_escalation(details, "Thandi Test")

    [message] = captured
    assert message["Subject"].startswith("URGENT")
    assert message["X-Priority"] == "1"
    assert message["X-Induduzo-Reference"] == "WA-" + str(escalation_id)[:8].upper()
    text = message.get_body(("plain",)).get_content()
    assert "Please respond to Thandi Test" in text
    assert family in text and "IND-2026-001234" in text
    assert f"https://portal.test/growth/whatsapp/{escalation_id}" in text


# -------------------------------------------------------------------- Logs ---

def _phone_numbers_in(text: str) -> list[str]:
    # Not inside a longer run of letters and digits, so a MessageSid or a row
    # id that happens to hold ten digits doesn't count.
    return re.findall(r"(?<![0-9A-Za-z])(?:\+?27\d{9}|0\d{9})(?![0-9A-Za-z])", text)


def test_the_logs_carry_no_numbers_and_no_message_text(client, line, family, staff_as, caplog):
    staff_as("owner")
    with caplog.at_level(logging.INFO):
        walk(client, family, "hi", "2", "5", "2", "My secret question about Gogo")
        escalation_id = next(r["id"] for r in client.get("/api/admin/whatsapp/escalations").json()
                             if r["other_number"] == family)
        client.post(f"/api/admin/whatsapp/escalations/{escalation_id}/reply",
                    json={"body": "Private staff words"})

    assert caplog.text  # something was logged
    assert family not in caplog.text
    assert _phone_numbers_in(caplog.text) == []
    for words in ("Gogo", "Private staff words", "Thandi"):
        assert words not in caplog.text


# ------------------------------------------------------------ Confirmation ---

def test_the_registration_confirmation_is_part_of_the_conversation(client, line, family, db,
                                                                   monkeypatch):
    from app.routers import enquiries

    monkeypatch.setattr(whatsapp, "get_settings", lambda: _settings())
    enquiry = client.post("/api/enquiries", json={
        "first_name": "Thandiwe", "surname": "Test", "mobile_number": family,
        "plan_interest": "plan_a", "contact_consent": True}).json()
    enquiries._send_confirmation(enquiry["id"], family, "Thandiwe", enquiry["reference"])

    [message] = _messages(db, family)
    assert message[:2] == ("outbound", "system")
    assert enquiry["reference"] in message[2]
    assert str(_conversation(db, family)["enquiry_id"]) == enquiry["id"]


# -------------------------------------------------------------- Safety net ---

def test_the_backfill_stores_what_the_webhook_missed_without_replying(client, line, family, db):
    walk(client, family, "hi")
    known = [m[5] for m in _messages(db, family) if m[0] == "inbound"][0]
    missed = "SM" + uuid.uuid4().hex
    line.twilio.history = [
        SimpleNamespace(sid=known, direction="inbound", from_=f"whatsapp:{family}",
                        body="hi", num_media="0", date_sent=None),
        SimpleNamespace(sid=missed, direction="inbound", from_=f"whatsapp:{family}",
                        body="Are you open on Saturday?", num_media="1",
                        date_sent=datetime.now(timezone.utc)),
        SimpleNamespace(sid="SM" + uuid.uuid4().hex, direction="outbound-api",
                        from_=f"whatsapp:{LINE}", body="menu", num_media="0", date_sent=None),
    ]
    line.twilio.media[missed] = [SimpleNamespace(sid="ME" + uuid.uuid4().hex,
                                                 content_type="image/jpeg")]
    sent_before = len(line.twilio.sent)

    assert whatsapp_line.backfill(datetime.now(timezone.utc) - timedelta(hours=6)) == (2, 1)
    assert whatsapp_line.backfill(datetime.now(timezone.utc) - timedelta(hours=6)) == (2, 0)

    row = db.execute("select body, menu_node, jsonb_array_length(media) from whatsapp_messages "
                     "where twilio_sid = %s", (missed,)).fetchone()
    assert row == ("Are you open on Saturday?", "backfilled", 1)
    assert len(line.twilio.sent) == sent_before


def test_an_escalation_email_that_failed_is_sent_by_the_retry(client, line, family, db, monkeypatch):
    monkeypatch.setattr(whatsapp_line, "send_whatsapp_escalation",
                        lambda details, name: EmailResult(sent=False, error="smtp down"))
    walk(client, family, "hi", "2", "5", "3")
    [escalation] = _escalations(db, family)
    assert escalation["notified_at"] is None

    sent = []
    monkeypatch.setattr(whatsapp_line, "send_whatsapp_escalation",
                        lambda details, name: sent.append(details["id"]) or EmailResult(sent=True))
    line.clock.advance(minutes=5)
    tried, delivered = whatsapp_line.retry_notifications()

    assert escalation["id"] in sent
    assert delivered >= 1 and tried >= delivered
    assert _escalations(db, family)[0]["notified_at"] is not None
