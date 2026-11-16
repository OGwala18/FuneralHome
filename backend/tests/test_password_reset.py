"""A forgotten staff password: the emailed, one-use temporary password.

Real database, a frozen clock, a mailbox instead of SMTP, and a stand-in for
Supabase's admin API, so every rule is checked exactly: the same answer for
strangers and staff, one use, 30 minutes, five tries, replaced by a newer one,
the old password untouched until the new one is set, and nothing secret in a
log or an event.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import uuid

import pytest

from app.config import get_settings as _real_get_settings
from app.routers import password_reset as router_module
from app.services import email as email_service
from app.services import password_reset as resets
from app.services import supabase_admin
from app.services.supabase_admin import PasswordResult

FORGOT = "/api/auth/password/forgot"
RESET = "/api/auth/password/reset"
NEW = "a long new password 42"


class FakeSupabase:
    """Records what the API asked Supabase to do, and answers as told."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.answer = PasswordResult(saved=True)
        # One-off answers, used in order before `answer`.
        self.queue: list[PasswordResult] = []
        self.users: dict[str, str] = {}

    def set_password(self, user_id, password):
        self.calls.append((user_id, password))
        return self.queue.pop(0) if self.queue else self.answer

    def find_user_id(self, email):
        return self.users.get(email.lower())


@pytest.fixture
def configured(monkeypatch):
    settings = dataclasses.replace(
        _real_get_settings(),
        supabase_url="https://reset-test.supabase.test",
        supabase_service_role_key="sb_secret_test",
        two_step_code_pepper="test-pepper-" + "x" * 32,
        smtp_host="mail.test",
        mail_to="office@induduzo.test",
        portal_url="https://portal.test",
    )
    for module in (router_module, email_service):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def supabase(monkeypatch, configured):
    fake = FakeSupabase()
    monkeypatch.setattr(supabase_admin, "set_password", fake.set_password)
    monkeypatch.setattr(supabase_admin, "find_user_id", fake.find_user_id)
    return fake


@pytest.fixture
def staff(db):
    """A fresh active staff row: (staff_id, email, supabase_user_id)."""
    def make(active: bool = True, signed_in: bool = True):
        email = f"reset-{uuid.uuid4().hex[:10]}@staff.test"
        user_id = str(uuid.uuid4()) if signed_in else None
        staff_id = db.execute(
            """
            insert into staff_users (email, role, is_active, supabase_user_id, invited_by)
            values (%s, 'admin', %s, %s, 'test') returning id
            """,
            (email, active, user_id),
        ).fetchone()[0]
        return str(staff_id), email, user_id

    return make


def _temporary_in(message) -> str:
    body = message.get_body(("plain",)).get_content()
    return re.search(r"\b([A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4})\b", body).group(1)


def _forgot(client, email):
    return client.post(FORGOT, json={"email": email})


def _reset(client, email, temporary, new=NEW):
    return client.post(RESET, json={"email": email, "temporary_password": temporary,
                                    "new_password": new})


# --- Asking -----------------------------------------------------------------------

def test_staff_get_a_temporary_password_by_email(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()

    answer = _forgot(client, email)
    assert answer.status_code == 202, answer.text
    assert len(mailbox) == 1
    message = mailbox[0]
    assert message["To"] == email
    assert message["Subject"] == "Your temporary Induduzo password"
    temporary = _temporary_in(message)
    assert temporary not in message["Subject"]
    assert "https://portal.test/reset-password" in message.get_body(("plain",)).get_content()
    # Asking changes nothing in Supabase: the old password still works.
    assert supabase.calls == []


def test_strangers_get_the_same_answer_and_no_email(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    real = _forgot(client, email)
    stranger = _forgot(client, "nobody-here@staff.test")
    assert stranger.status_code == real.status_code == 202
    assert stranger.json() == real.json()
    assert len(mailbox) == 1


def test_deactivated_staff_get_nothing(client, clock, mailbox, supabase, staff):
    _, email, _ = staff(active=False)
    assert _forgot(client, email).status_code == 202
    assert mailbox == []


def test_the_address_is_matched_whatever_its_case(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    assert _forgot(client, "  " + email.upper() + " ").status_code == 202
    assert len(mailbox) == 1
    assert mailbox[0]["To"] == email


def test_one_email_a_minute_and_five_an_hour(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    _forgot(client, email)
    assert len(mailbox) == 1, "a second ask inside a minute sends nothing"

    for _ in range(4):
        clock.advance(seconds=61)
        _forgot(client, email)
    assert len(mailbox) == 5
    clock.advance(seconds=61)
    assert _forgot(client, email).status_code == 202
    assert len(mailbox) == 5, "the sixth in an hour sends nothing"


def test_without_the_service_key_it_says_so_and_sends_nothing(
        client, clock, mailbox, configured, monkeypatch, staff):
    off = dataclasses.replace(configured, supabase_service_role_key=None)
    monkeypatch.setattr(router_module, "get_settings", lambda: off)
    _, email, _ = staff()
    for answer in (_forgot(client, email), _reset(client, email, "ABCD-EFGH-JKMN")):
        assert answer.status_code == 503
        assert answer.json()["code"] == "password_reset_not_configured"
    assert mailbox == []


# --- Using it ---------------------------------------------------------------------

def test_the_temporary_password_sets_a_new_one_once(client, clock, mailbox, supabase, staff, db):
    staff_id, email, user_id = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])

    done = _reset(client, email, temporary)
    assert done.status_code == 200, done.text
    assert done.json() == {"reset": True}
    assert supabase.calls == [(user_id, NEW)]

    again = _reset(client, email, temporary, "another long password 43")
    assert again.status_code == 400
    assert again.json()["code"] == "temporary_password_invalid"
    assert len(supabase.calls) == 1

    events = [row[0] for row in db.execute(
        "select event_type from staff_events where subject = %s order by created_at", (email,))]
    assert "password_reset_sent" in events and "password_reset_done" in events


def test_how_it_is_typed_does_not_matter(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])
    typed = " " + temporary.lower().replace("-", " ") + " "
    assert _reset(client, email, typed).status_code == 200


def test_it_expires_after_thirty_minutes(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])
    clock.advance(minutes=30)
    late = _reset(client, email, temporary)
    assert late.status_code == 400
    assert late.json()["code"] == "temporary_password_invalid"
    assert supabase.calls == []


def test_five_wrong_tries_kill_it(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])
    for _ in range(5):
        assert _reset(client, email, "AAAA-AAAA-AAAA").status_code == 400
    dead = _reset(client, email, temporary)
    assert dead.status_code == 400
    assert supabase.calls == []


def test_a_newer_one_replaces_the_older(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    clock.advance(seconds=61)
    _forgot(client, email)
    old, new = _temporary_in(mailbox[0]), _temporary_in(mailbox[1])
    assert old != new
    assert _reset(client, email, old).status_code == 400
    assert _reset(client, email, new).status_code == 200


def test_it_only_works_for_the_address_it_was_sent_to(client, clock, mailbox, supabase, staff):
    _, first, _ = staff()
    _, second, _ = staff()
    _forgot(client, first)
    temporary = _temporary_in(mailbox[0])
    assert _reset(client, second, temporary).status_code == 400
    assert _reset(client, "nobody-here@staff.test", temporary).status_code == 400
    assert supabase.calls == []


@pytest.mark.parametrize("new, why", [
    ("short", "at least 12"),
    ("x" * 73, "at most 72"),
])
def test_a_new_password_outside_the_rules_is_refused_and_the_temporary_survives(
        client, clock, mailbox, supabase, staff, new, why):
    _, email, _ = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])
    refused = _reset(client, email, temporary, new)
    assert refused.status_code == 422
    assert refused.json()["code"] == "password_rejected"
    assert why in refused.json()["detail"]
    assert _reset(client, email, temporary).status_code == 200


def test_the_temporary_password_cannot_be_the_new_one(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])
    # Exactly the temporary one, however it is typed, is refused (14 characters
    # with the dashes, so it would pass the length rule on its own).
    refused = _reset(client, email, temporary, temporary.lower())
    assert refused.status_code == 422
    assert refused.json()["code"] == "password_rejected"
    assert supabase.calls == []
    assert _reset(client, email, temporary).status_code == 200


def test_supabase_refusing_the_password_keeps_the_temporary_alive(
        client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])

    supabase.answer = PasswordResult(saved=False, rejected=True,
                                     detail="Password should contain at least one digit.")
    refused = _reset(client, email, temporary)
    assert refused.status_code == 422
    assert refused.json()["code"] == "password_rejected"
    assert refused.json()["detail"] == "Password should contain at least one digit."

    supabase.answer = PasswordResult(saved=True)
    assert _reset(client, email, temporary).status_code == 200


def test_supabase_down_keeps_the_temporary_alive(client, clock, mailbox, supabase, staff):
    _, email, _ = staff()
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])
    supabase.answer = PasswordResult(saved=False)
    down = _reset(client, email, temporary)
    assert down.status_code == 502
    assert down.json()["code"] == "upstream_failed"
    supabase.answer = PasswordResult(saved=True)
    assert _reset(client, email, temporary).status_code == 200


def test_staff_who_never_signed_in_are_found_by_address(client, clock, mailbox, supabase, staff):
    _, email, _ = staff(signed_in=False)
    supabase.users[email] = "11111111-2222-3333-4444-555555555555"
    _forgot(client, email)
    assert _reset(client, email, _temporary_in(mailbox[0])).status_code == 200
    assert supabase.calls[0][0] == "11111111-2222-3333-4444-555555555555"


def test_no_supabase_sign_in_at_all_says_so(client, clock, mailbox, supabase, staff):
    _, email, _ = staff(signed_in=False)
    _forgot(client, email)
    missing = _reset(client, email, _temporary_in(mailbox[0]))
    assert missing.status_code == 409
    assert missing.json()["code"] == "sign_in_missing"


def test_a_stale_stored_id_is_looked_up_again(client, clock, mailbox, supabase, staff):
    _, email, stale = staff()
    fresh = str(uuid.uuid4())
    supabase.users[email] = fresh
    supabase.queue = [PasswordResult(saved=False, no_account=True)]
    _forgot(client, email)
    assert _reset(client, email, _temporary_in(mailbox[0])).status_code == 200
    assert [call[0] for call in supabase.calls] == [stale, fresh]


# --- Nothing secret is kept --------------------------------------------------------

def test_nothing_readable_is_stored_logged_or_put_in_an_event(
        client, clock, mailbox, supabase, staff, db, caplog):
    staff_id, email, _ = staff()
    caplog.set_level(logging.DEBUG)
    _forgot(client, email)
    temporary = _temporary_in(mailbox[0])
    _reset(client, email, "WRNG-WRNG-WRNG")
    _reset(client, email, temporary)

    row = db.execute("select temp_hash from staff_password_resets where staff_user_id = %s",
                     (staff_id,)).fetchone()
    assert len(bytes(row[0])) == 32
    assert temporary.encode() not in bytes(row[0])

    logged = caplog.text
    for secret in (temporary, resets.normalise(temporary), NEW, email):
        assert secret not in logged

    payloads = json.dumps([r[0] for r in db.execute(
        "select payload from staff_events where subject = %s", (email,))])
    for secret in (temporary, resets.normalise(temporary), NEW):
        assert secret not in payloads


def test_the_temporary_password_looks_as_promised():
    for _ in range(50):
        temporary = resets.new_temporary_password()
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", temporary)
        assert not set(resets.normalise(temporary)) & set("0O1IL")


def test_health_reports_whether_it_is_switched_on(client):
    assert client.get("/health").json()["password_reset"] in ("configured", "not_configured")


# --- The Supabase admin call itself ---------------------------------------------------

class _Answer:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self):
        return json.dumps(self._body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def admin_api(monkeypatch, configured):
    """Capture the HTTP request supabase_admin makes, and answer as told."""
    import urllib.error
    import urllib.request

    seen = {}
    reply = {"status": 200, "body": {"id": "x"}}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["headers"] = {k.lower(): v for k, v in request.header_items()}
        seen["body"] = json.loads(request.data) if request.data else None
        if reply["status"] >= 400:
            import io
            raise urllib.error.HTTPError(request.full_url, reply["status"], "x", {},
                                         io.BytesIO(json.dumps(reply["body"]).encode()))
        return _Answer(reply["status"], reply["body"])

    monkeypatch.setattr(supabase_admin, "get_settings", lambda: configured)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen, reply


def test_a_new_style_secret_key_goes_on_apikey_only(admin_api):
    seen, _ = admin_api
    assert supabase_admin.set_password("abc", NEW).saved
    assert seen["method"] == "PUT"
    assert seen["url"] == "https://reset-test.supabase.test/auth/v1/admin/users/abc"
    assert seen["headers"]["apikey"] == "sb_secret_test"
    assert "authorization" not in seen["headers"]
    assert seen["body"] == {"password": NEW}


def test_a_legacy_service_role_key_also_goes_as_a_bearer_token():
    headers = supabase_admin._headers("eyJlegacy.jwt.value")
    assert headers["Authorization"] == "Bearer eyJlegacy.jwt.value"


def test_supabase_weak_password_comes_back_as_its_own_sentence(admin_api):
    _, reply = admin_api
    reply.update(status=422, body={"code": "weak_password",
                                   "msg": "Password should be at least 14 characters."})
    result = supabase_admin.set_password("abc", NEW)
    assert (result.saved, result.rejected) == (False, True)
    assert result.detail == "Password should be at least 14 characters."


def test_supabase_404_and_500_are_told_apart(admin_api):
    _, reply = admin_api
    reply.update(status=404, body={"code": "user_not_found"})
    assert supabase_admin.set_password("abc", NEW).no_account
    reply.update(status=500, body={})
    result = supabase_admin.set_password("abc", NEW)
    assert not (result.saved or result.rejected or result.no_account)


def test_finding_a_user_matches_the_whole_address(admin_api):
    _, reply = admin_api
    reply.update(status=200, body={"users": [
        {"id": "1", "email": "xnelly@induduzo.test"},
        {"id": "2", "email": "Nelly@Induduzo.test"},
    ]})
    assert supabase_admin.find_user_id("nelly@induduzo.test") == "2"
    assert supabase_admin.find_user_id("nobody@induduzo.test") is None
