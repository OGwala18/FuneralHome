"""The daily scheduled jobs (app/jobs/daily.py).

The one rule that costs money if broken: payment reminders must claim nothing
while WhatsApp can't deliver, because a claimed reminder that fails is never
sent again. Settings are built from made-up values, like test_two_step_settings.
"""

from __future__ import annotations

import contextlib
import secrets
import sys
from types import SimpleNamespace

import pytest
import requests
import twilio.rest
from cryptography.fernet import Fernet
from twilio.base.exceptions import TwilioRestException

from app.config import Settings
from app.jobs import daily
from app.jobs import payment_reminders as reminder_jobs
from app.services import whatsapp
from app.services.payment_reminders import not_ready


def _settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "two_step_enforcement": "on",
        "two_step_encryption_keys": [Fernet.generate_key().decode()],
        "two_step_code_pepper": secrets.token_urlsafe(32),
        "twilio_account_sid": "AC" + "0" * 32,
        "twilio_auth_token": "made-up",
        "twilio_whatsapp_from": "whatsapp:+27000000000",
        "twilio_payment_due_sid": "HX" + "1" * 32,
        "twilio_payment_missed_sid": "HX" + "2" * 32,
        "whatsapp_outbound": "on",
    }
    values.update(overrides)
    return Settings(**values)


def test_ready_when_whatsapp_and_both_templates_are_configured():
    assert not_ready(_settings()) == []


def test_not_ready_without_twilio_or_templates():
    missing = not_ready(_settings(twilio_auth_token=None, twilio_payment_missed_sid=None))
    assert any("TWILIO_AUTH_TOKEN" in name for name in missing)
    assert any("TWILIO_PAYMENT_MISSED_SID" in name for name in missing)


def test_production_needs_outbound_on():
    # 'known' would refuse most families, burning each reminder as failed.
    assert not_ready(_settings(whatsapp_outbound="known"))
    assert not_ready(_settings(whatsapp_outbound="off"))
    # Internal tests with an allowlist on purpose.
    assert not_ready(_settings(environment="internal", whatsapp_outbound="allowlist")) == []


def test_not_ready_names_settings_never_values():
    secret = "do-not-print-this"
    missing = not_ready(_settings(twilio_payment_due_sid=None, twilio_auth_token=secret,
                                  twilio_account_sid=None))
    assert secret not in " ".join(missing)


def test_reminder_days(monkeypatch):
    monkeypatch.delenv("REMINDER_DAYS", raising=False)
    assert daily.reminder_days() == {25}
    monkeypatch.setenv("REMINDER_DAYS", "1, 2,25,26,x")
    assert daily.reminder_days() == {1, 2, 25, 26}


def test_backup_script_is_where_the_runner_looks():
    assert (daily.ROOT / "db" / "backup.py").is_file()


# --- Does Twilio accept the token? --------------------------------------------
#
# Railway seals the token, /health and not_ready() only see that it exists, and
# a wrong one would burn every reminder on the 25th. The check reads the account
# and must never send. Twilio's Client is a fake: nothing leaves the process.

ACCOUNT_SID = "AC" + "0" * 32
TOKEN = "made-up"


class FakeTwilioAccount:
    """Stands in for twilio.rest.Client. Answers an account fetch with `status`,
    or raises `error`. Any attempt to send a message fails the test."""

    def __init__(self) -> None:
        self.status = "active"
        self.error: Exception | None = None
        self.logins: list[tuple[str, str]] = []
        self.fetched: list[str] = []

    def client(self, account_sid: str, auth_token: str) -> SimpleNamespace:
        self.logins.append((account_sid, auth_token))
        return SimpleNamespace(
            api=SimpleNamespace(v2010=SimpleNamespace(
                accounts=lambda sid: SimpleNamespace(fetch=lambda: self._fetch(sid)))),
            messages=SimpleNamespace(create=self._send),
        )

    def _fetch(self, sid: str) -> SimpleNamespace:
        if self.error:
            raise self.error
        self.fetched.append(sid)
        return SimpleNamespace(sid=sid, status=self.status)

    def _send(self, **_params):
        raise AssertionError("the credentials check must never send a message")


@pytest.fixture
def twilio_account(monkeypatch) -> FakeTwilioAccount:
    fake = FakeTwilioAccount()
    monkeypatch.setattr(twilio.rest, "Client", fake.client)
    return fake


def _wrong_token() -> TwilioRestException:
    # What Twilio answers a bad token with. Its message quotes the account SID.
    return TwilioRestException(
        status=401, uri=f"/2010-04-01/Accounts/{ACCOUNT_SID}.json",
        msg=f"Authenticate: unable to fetch record for {ACCOUNT_SID}", code=20003,
        method="GET",
    )


def test_a_token_twilio_accepts_passes(twilio_account):
    assert whatsapp.credentials_problem(_settings()) is None
    assert twilio_account.logins == [(ACCOUNT_SID, TOKEN)]
    assert twilio_account.fetched == [ACCOUNT_SID]


def test_a_wrong_token_is_reported_as_twilios_code(twilio_account):
    twilio_account.error = _wrong_token()
    assert whatsapp.credentials_problem(_settings()) == "twilio_20003"


@pytest.mark.parametrize("status", ["suspended", "closed"])
def test_an_account_that_cannot_send_is_reported(twilio_account, status):
    twilio_account.status = status
    assert whatsapp.credentials_problem(_settings()) == f"twilio_account_{status}"


def test_twilio_out_of_reach_is_reported_not_raised(twilio_account):
    twilio_account.error = requests.exceptions.ConnectionError("api.twilio.com unreachable")
    assert whatsapp.credentials_problem(_settings()) == "ConnectionError"


def test_no_credentials_means_no_call_to_twilio(twilio_account):
    assert (whatsapp.credentials_problem(_settings(twilio_auth_token=None))
            == "whatsapp_not_configured")
    assert twilio_account.logins == []


def test_the_morning_run_checks_the_token(monkeypatch, capsys, twilio_account):
    monkeypatch.setattr(daily, "get_settings", lambda: _settings())
    assert daily.twilio_credentials() == 0
    assert "twilio credentials: accepted" in capsys.readouterr().out


def test_a_wrong_token_fails_the_morning_run_and_prints_no_secret(
        monkeypatch, capsys, twilio_account):
    monkeypatch.setattr(daily, "get_settings", lambda: _settings())
    twilio_account.error = _wrong_token()

    assert daily.twilio_credentials() == 1

    out = capsys.readouterr().out
    assert "twilio credentials: refused (twilio_20003)" in out
    assert TOKEN not in out
    assert ACCOUNT_SID not in out


def test_the_morning_run_skips_the_check_where_whatsapp_is_not_set_up(
        monkeypatch, capsys, twilio_account):
    monkeypatch.setattr(daily, "get_settings",
                        lambda: _settings(twilio_account_sid=None, twilio_auth_token=None))
    assert daily.twilio_credentials() == 0
    assert "not configured, skipped" in capsys.readouterr().out
    assert twilio_account.logins == []


def test_every_morning_runs_the_check_and_its_failure_fails_the_run(monkeypatch, capsys):
    monkeypatch.setenv("REMINDER_DAYS", "x")  # no reminder day: the check runs anyway
    ran: list[str] = []
    monkeypatch.setattr(daily, "backup", lambda: ran.append("backup") or 0)
    monkeypatch.setattr(daily.schedule_instalments, "main",
                        lambda: ran.append("schedule") or 0)
    monkeypatch.setattr(daily, "twilio_credentials", lambda: ran.append("twilio") or 1)

    assert daily.main() == 1

    assert ran == ["backup", "schedule", "twilio"]
    assert "failed: twilio credentials" in capsys.readouterr().out


@pytest.fixture
def reminder_job(monkeypatch):
    """The reminder job with ready settings, today's date, and a database that
    records whether it was ever opened: opening it is what claims reminders."""
    opened: list[str] = []

    @contextlib.contextmanager
    def connect(url, **_kwargs):
        opened.append(url)
        yield object()

    monkeypatch.setattr(sys, "argv", ["payment_reminders"])
    monkeypatch.setattr(reminder_jobs, "get_settings",
                        lambda: _settings(database_url="postgresql://made-up"))
    monkeypatch.setattr(reminder_jobs.psycopg, "connect", connect)
    monkeypatch.setattr(reminder_jobs.payment_reminders, "run", lambda conn, today: {})
    return opened


def test_reminders_claim_nothing_while_twilio_refuses_the_token(
        reminder_job, twilio_account, capsys):
    twilio_account.error = _wrong_token()

    assert reminder_jobs.main() == 1

    assert reminder_job == []  # the database was never opened, so nothing was claimed
    out = capsys.readouterr().out
    assert "twilio_20003" in out and "Nothing was claimed" in out
    assert TOKEN not in out


def test_reminders_go_ahead_once_twilio_accepts_the_token(reminder_job, twilio_account):
    assert reminder_jobs.main() == 0
    assert reminder_job == ["postgresql://made-up"]
