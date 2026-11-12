"""The daily scheduled jobs (app/jobs/daily.py).

The one rule that costs money if broken: payment reminders must claim nothing
while WhatsApp can't deliver, because a claimed reminder that fails is never
sent again. Settings are built from made-up values, like test_two_step_settings.
"""

from __future__ import annotations

import secrets

from cryptography.fernet import Fernet

from app.config import Settings
from app.jobs import daily
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
