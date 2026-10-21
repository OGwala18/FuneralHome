"""Who the WhatsApp line may message, and what its logs may say: Bit W1 of
docs/feature-3-whatsapp-line.md.

No message is ever sent. Twilio's Client is replaced by a fake that records
what it was asked to send. The two checks on the Twilio library's own logging
run the real library, because it is what logs, over a fake transport: nothing
leaves the process, and the credentials are made up.

The numbers are placeholders, the same ones test_api.py uses.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import twilio.rest
from twilio.base.exceptions import TwilioRestException

from app.config import Settings
from app.services import whatsapp

BACKEND = Path(__file__).resolve().parents[1]

ACCOUNT_SID = "AC" + "0" * 30 + "f1"
MESSAGE_SID = "SM" + "0" * 32
STAFF_PHONE = "+27820000001"
FAMILY_PHONE = "+27820000002"
REFERENCE = "IND-2026-999001"


def _settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "twilio_account_sid": ACCOUNT_SID,
        "twilio_auth_token": "made-up-auth-token",
        "twilio_whatsapp_from": "+27820000000",
        "twilio_content_sid": "HX" + "0" * 32,
        "whatsapp_outbound": "on",
        "whatsapp_test_recipients": frozenset({STAFF_PHONE}),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def use(monkeypatch):
    """Run the WhatsApp service with these settings instead of the environment's."""
    def apply(**overrides) -> Settings:
        settings = _settings(**overrides)
        monkeypatch.setattr(whatsapp, "get_settings", lambda: settings)
        return settings

    return apply


class FakeTwilio:
    """Stands in for twilio.rest.Client. Records each message instead of
    sending it, or raises `error` if one is set."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.error: Exception | None = None

    def client(self, account_sid: str, auth_token: str) -> SimpleNamespace:
        return SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params) -> SimpleNamespace:
        if self.error:
            raise self.error
        self.sent.append(params)
        return SimpleNamespace(sid=MESSAGE_SID)


@pytest.fixture
def fake_twilio(monkeypatch) -> FakeTwilio:
    fake = FakeTwilio()
    monkeypatch.setattr(twilio.rest, "Client", fake.client)
    return fake


def _confirm(to_mobile: str):
    return whatsapp.send_registration_confirmation(
        to_mobile=to_mobile, first_name="Test", reference=REFERENCE
    )


def _mentions_a_number(text: str) -> bool:
    """Whether either test number appears, as +27… or as 0…"""
    return any(number[3:] in text for number in (STAFF_PHONE, FAMILY_PHONE))


# --- The switch -----------------------------------------------------------------

def test_on_sends_to_anyone(use, fake_twilio):
    use(whatsapp_outbound="on")

    result = _confirm(FAMILY_PHONE)

    assert result.sent
    assert result.message_sid == MESSAGE_SID
    assert [message["to"] for message in fake_twilio.sent] == [f"whatsapp:{FAMILY_PHONE}"]


def test_allowlist_sends_to_a_listed_number(use, fake_twilio):
    use(whatsapp_outbound="allowlist")

    result = _confirm(STAFF_PHONE)

    assert result.sent
    assert [message["to"] for message in fake_twilio.sent] == [f"whatsapp:{STAFF_PHONE}"]


def test_allowlist_refuses_every_other_number(use, fake_twilio):
    use(whatsapp_outbound="allowlist")

    result = _confirm(FAMILY_PHONE)

    assert not result.sent
    assert result.error == "whatsapp_not_allowlisted"
    assert fake_twilio.sent == []


def test_an_empty_allowlist_sends_to_nobody(use, fake_twilio):
    use(whatsapp_outbound="allowlist", whatsapp_test_recipients=frozenset())

    assert _confirm(STAFF_PHONE).error == "whatsapp_not_allowlisted"
    assert fake_twilio.sent == []


# STAFF_PHONE is on the allowlist, and off still sends it nothing.
@pytest.mark.parametrize("to_mobile", [STAFF_PHONE, FAMILY_PHONE])
def test_off_sends_to_nobody(use, fake_twilio, to_mobile):
    use(whatsapp_outbound="off")

    result = _confirm(to_mobile)

    assert not result.sent
    assert result.error == "whatsapp_outbound_off"
    assert fake_twilio.sent == []


def test_without_credentials_nothing_is_sent_even_when_on(use, fake_twilio):
    use(whatsapp_outbound="on", twilio_auth_token=None)

    assert _confirm(FAMILY_PHONE).error == "whatsapp_not_configured"
    assert fake_twilio.sent == []


# --- The settings ---------------------------------------------------------------

def _settings_at_start_up(**env: str) -> dict:
    """Build Settings in a fresh process, as the API does at start-up, with
    the three W1 variables unset except for those given in `env`."""
    names = ("WHATSAPP_OUTBOUND", "WHATSAPP_TEST_RECIPIENTS", "PUBLIC_API_URL")
    environment = {name: value for name, value in os.environ.items() if name not in names}
    script = (
        "import json; from app.config import Settings; s = Settings(); "
        "print(json.dumps({'outbound': s.whatsapp_outbound, "
        "'recipients': sorted(s.whatsapp_test_recipients), "
        "'public_api_url': s.public_api_url}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env={**environment, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_unset_means_off():
    # An environment with Twilio credentials messages nobody until someone
    # chooses who it may message.
    assert _settings_at_start_up() == {"outbound": "off", "recipients": [], "public_api_url": None}


def test_the_settings_are_read_the_way_people_type_them():
    settings = _settings_at_start_up(
        WHATSAPP_OUTBOUND=" Allowlist ",
        WHATSAPP_TEST_RECIPIENTS="+27 82 000 0001, +27-82-000-0002,",
        PUBLIC_API_URL="https://api.example.test/",
    )

    assert settings == {
        "outbound": "allowlist",
        "recipients": [STAFF_PHONE, FAMILY_PHONE],
        "public_api_url": "https://api.example.test",
    }


@pytest.mark.parametrize("value", ["yes", "true", "1", "all", "allow"])
def test_anything_but_off_allowlist_or_on_will_not_start(value):
    with pytest.raises(ValueError, match="WHATSAPP_OUTBOUND"):
        _settings(whatsapp_outbound=value)


def test_the_api_refuses_to_start_with_an_unknown_mode():
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND,
        env={**os.environ, "WHATSAPP_OUTBOUND": "yes"},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode != 0
    assert "WHATSAPP_OUTBOUND must be 'off', 'allowlist' or 'on'." in result.stderr


@pytest.mark.parametrize("number", ["0820000001", "27820000001", "+0820000001", "+2782000000123456"])
def test_an_allowlist_number_not_in_e164_will_not_start(number):
    with pytest.raises(ValueError, match="WHATSAPP_TEST_RECIPIENTS") as raised:
        _settings(whatsapp_test_recipients=frozenset({number}))

    # The numbers are personal, so the error names the setting only.
    assert number not in str(raised.value)


def test_the_test_numbers_stay_out_of_repr():
    assert not _mentions_a_number(repr(_settings()))


# --- Logs: the reference, never the number ----------------------------------------

@pytest.mark.parametrize("mode", ["off", "allowlist"])
def test_a_skipped_message_is_logged_by_reference_only(use, fake_twilio, caplog, mode):
    use(whatsapp_outbound=mode)

    with caplog.at_level(logging.INFO):
        _confirm(FAMILY_PHONE)

    assert REFERENCE in caplog.text
    assert not _mentions_a_number(caplog.text)


def test_a_twilio_failure_is_logged_as_its_code_not_its_message(use, fake_twilio, caplog):
    use(whatsapp_outbound="on")
    fake_twilio.error = TwilioRestException(
        status=400,
        uri=f"/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json",
        msg=f"Unable to create record: Invalid 'To' Phone Number: whatsapp:{FAMILY_PHONE}",
        code=21211,
        method="POST",
    )

    with caplog.at_level(logging.INFO):
        result = _confirm(FAMILY_PHONE)

    assert not result.sent
    # Also what enquiry_events records, so the audit trail stays clean too.
    assert result.error == "twilio_21211"
    assert f"{REFERENCE}: twilio_21211" in caplog.text
    assert not _mentions_a_number(caplog.text)
    assert "Invalid 'To' Phone Number" not in caplog.text
    assert ACCOUNT_SID not in caplog.text


def test_any_other_failure_is_logged_as_its_kind_only(use, fake_twilio, caplog):
    use(whatsapp_outbound="on")
    fake_twilio.error = requests.ConnectionError(f"could not send to whatsapp:{FAMILY_PHONE}")

    with caplog.at_level(logging.INFO):
        result = _confirm(FAMILY_PHONE)

    assert result.error == "ConnectionError"
    assert f"{REFERENCE}: ConnectionError" in caplog.text
    assert not _mentions_a_number(caplog.text)


# --- The Twilio library's own logging ---------------------------------------------

def _twilio_answers(monkeypatch, status: int, body: dict) -> list[requests.PreparedRequest]:
    """Answer every request the Twilio library makes with `body`, without it
    reaching the network. Returns the requests it tried to make."""
    attempted: list[requests.PreparedRequest] = []

    def send(session, request, **kwargs):
        attempted.append(request)
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.encoding = "utf-8"
        response.headers["Content-Type"] = "application/json"
        response.request = request
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    return attempted


def test_the_twilio_library_does_not_log_each_request(use, monkeypatch, caplog):
    use(whatsapp_outbound="on")
    attempted = _twilio_answers(monkeypatch, 201, {"sid": MESSAGE_SID, "status": "queued"})

    with caplog.at_level(logging.INFO):
        result = _confirm(FAMILY_PHONE)

    # The real library ran and made its one request...
    assert result.sent
    assert len(attempted) == 1
    assert ACCOUNT_SID in attempted[0].url
    # ...and logged none of it, so the account SID in its URL stays out.
    assert ACCOUNT_SID not in caplog.text
    assert "Twilio API Request" not in caplog.text


def test_a_real_twilio_error_reaches_the_logs_as_a_code_only(use, monkeypatch, caplog):
    use(whatsapp_outbound="on")
    _twilio_answers(monkeypatch, 400, {
        "code": 21211,
        "message": f"Invalid 'To' Phone Number: whatsapp:{FAMILY_PHONE}",
        "more_info": "https://www.twilio.com/docs/errors/21211",
        "status": 400,
    })

    with caplog.at_level(logging.INFO):
        result = _confirm(FAMILY_PHONE)

    assert result.error == "twilio_21211"
    assert not _mentions_a_number(caplog.text)
    assert "Invalid 'To' Phone Number" not in caplog.text
    assert ACCOUNT_SID not in caplog.text


# --- Through the registration form -------------------------------------------------

def _register(client, mobile_number: str) -> dict:
    """Stage 1 then stage 2, as the website does. Stage 2 sends the confirmation."""
    lead = client.post("/api/enquiries", json={
        "first_name": "Test",
        "surname": "Applicant",
        "mobile_number": mobile_number,
        "plan_interest": "plan_a",
        "contact_consent": True,
    }).json()
    response = client.patch(
        f"/api/enquiries/{lead['id']}/application",
        json={"plan_selected": "plan_a", "terms_accepted": True},
    )
    assert response.status_code == 200
    return lead


def _whatsapp_events(db, enquiry_id: str) -> list[tuple]:
    return db.execute(
        "select event_type, payload->>'message_sid', payload->>'error' from enquiry_events "
        "where enquiry_id = %s and event_type like 'whatsapp%%'",
        (enquiry_id,),
    ).fetchall()


def test_internal_never_confirms_to_a_number_off_the_allowlist(client, db, use, fake_twilio, caplog):
    use(whatsapp_outbound="allowlist")

    with caplog.at_level(logging.INFO):
        lead = _register(client, "082 000 0002")

    # The registration still succeeds; only the message is held back.
    assert fake_twilio.sent == []
    assert _whatsapp_events(db, lead["id"]) == [
        ("whatsapp_failed", None, "whatsapp_not_allowlisted")
    ]
    assert lead["reference"] in caplog.text
    assert not _mentions_a_number(caplog.text)


def test_internal_confirms_to_an_allowlisted_number(client, db, use, fake_twilio):
    use(whatsapp_outbound="allowlist")

    lead = _register(client, "082 000 0001")

    assert [message["to"] for message in fake_twilio.sent] == [f"whatsapp:{STAFF_PHONE}"]
    assert _whatsapp_events(db, lead["id"]) == [("whatsapp_sent", MESSAGE_SID, None)]
