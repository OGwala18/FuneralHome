"""The settings behind staff two-step sign-in: §7 of
docs/feature-2-staff-two-factor.md.

Production refuses to start with enforcement off, and "fully configured" means
every setting is there and usable, which is what lets later bits fail closed.
Settings are built directly from made-up values, so the environment the tests
run in doesn't matter, except for the two start-up checks, which import the
real app in a separate process.
"""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import MIN_PEPPER_BYTES, Settings

BACKEND = Path(__file__).resolve().parents[1]


def _complete(**overrides) -> Settings:
    values = {
        "environment": "test",
        "two_step_enforcement": "on",
        "two_step_encryption_keys": [Fernet.generate_key().decode()],
        "two_step_code_pepper": secrets.token_urlsafe(32),
        "webauthn_rp_id": "localhost",
        "webauthn_rp_name": "Induduzo Staff Portal",
        "webauthn_origins": ["http://localhost:8090"],
    }
    values.update(overrides)
    return Settings(**values)


# --- Enforcement ------------------------------------------------------------

def test_production_will_not_start_with_enforcement_off():
    with pytest.raises(RuntimeError, match="TWO_STEP_ENFORCEMENT"):
        Settings(environment="production", two_step_enforcement="off")


def test_production_starts_with_enforcement_on():
    assert Settings(environment="production", two_step_enforcement="on").two_step_enforced


@pytest.mark.parametrize("environment", ["development", "test", "internal"])
def test_enforcement_may_be_off_outside_production(environment):
    settings = Settings(environment=environment, two_step_enforcement="off")

    assert not settings.two_step_enforced


@pytest.mark.parametrize("value", ["yes", "true", "1", "enabled"])
def test_anything_but_on_or_off_will_not_start(value):
    with pytest.raises(ValueError, match="TWO_STEP_ENFORCEMENT"):
        Settings(environment="development", two_step_enforcement=value)


def _import_the_api(**env: str) -> subprocess.CompletedProcess:
    """Import the app as Uvicorn does, in a fresh process, with `env` set."""
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_api_refuses_to_start_in_production_with_enforcement_off():
    # Blank, as a variable nobody filled in on Railway would be.
    result = _import_the_api(ENVIRONMENT="production", TWO_STEP_ENFORCEMENT="")

    assert result.returncode != 0
    assert "TWO_STEP_ENFORCEMENT is off and ENVIRONMENT is production" in result.stderr


def test_the_api_starts_in_production_with_enforcement_on():
    result = _import_the_api(ENVIRONMENT="production", TWO_STEP_ENFORCEMENT="on")

    assert result.returncode == 0, result.stderr


# --- Fully configured, so later bits can fail closed ------------------------

def test_everything_set_is_fully_configured():
    settings = _complete()

    assert settings.two_step_missing == []
    assert settings.two_step_configured


@pytest.mark.parametrize(
    "change, name",
    [
        ({"two_step_encryption_keys": []}, "TWO_STEP_ENCRYPTION_KEYS"),
        ({"two_step_encryption_keys": ["not-a-fernet-key"]}, "TWO_STEP_ENCRYPTION_KEYS"),
        (
            {"two_step_encryption_keys": [base64.urlsafe_b64encode(bytes(31)).decode()]},
            "TWO_STEP_ENCRYPTION_KEYS",
        ),
        # A rotation list is only usable if every key in it is.
        (
            {"two_step_encryption_keys": [Fernet.generate_key().decode(), "typo"]},
            "TWO_STEP_ENCRYPTION_KEYS",
        ),
        ({"two_step_code_pepper": None}, "TWO_STEP_CODE_PEPPER"),
        ({"two_step_code_pepper": "x" * (MIN_PEPPER_BYTES - 1)}, "TWO_STEP_CODE_PEPPER"),
        ({"webauthn_rp_id": None}, "WEBAUTHN_RP_ID"),
        ({"webauthn_rp_name": " "}, "WEBAUTHN_RP_NAME"),
        ({"webauthn_origins": []}, "WEBAUTHN_ORIGINS"),
    ],
)
def test_a_missing_or_unusable_setting_is_named(change, name):
    settings = _complete(**change)

    assert settings.two_step_missing == [name]
    assert not settings.two_step_configured


def test_missing_settings_do_not_stop_the_api_starting():
    # Enforcement on with nothing configured still starts, so the public
    # enquiry form keeps working. Staff routes are the ones that refuse.
    settings = _complete(
        environment="production",
        two_step_encryption_keys=[],
        two_step_code_pepper=None,
        webauthn_rp_id=None,
        webauthn_origins=[],
    )

    assert settings.two_step_enforced
    assert not settings.two_step_configured


def test_the_keys_and_the_pepper_stay_out_of_repr():
    settings = _complete()

    shown = repr(settings)

    assert settings.two_step_code_pepper not in shown
    assert settings.two_step_encryption_keys[0] not in shown
