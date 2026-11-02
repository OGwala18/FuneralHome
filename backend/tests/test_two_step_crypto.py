"""The crypto helpers behind staff two-step sign-in, as §11A of
docs/feature-2-staff-two-factor.md lists them.

Pure functions, so nothing here touches the database. (conftest still wants
DATABASE_URL, because it imports the whole app.) Every key, pepper, secret and
token is made up on the spot.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.config import MIN_PEPPER_BYTES
from app.services import two_step_crypto as crypto

PEPPER = secrets.token_urlsafe(32)
DOTS = "•" * 3  # •••


def _key() -> str:
    return Fernet.generate_key().decode()


def _app_secret() -> str:
    """Shaped like pyotp.random_base32(): 160 bits as 32 base32 characters."""
    return base64.b32encode(secrets.token_bytes(20)).decode()


# --- Authenticator-app secrets ----------------------------------------------

def test_an_app_secret_survives_the_round_trip():
    key, secret = _key(), _app_secret()

    assert crypto.decrypt_secret(crypto.encrypt_secret(secret, [key]), [key]) == secret


def test_the_stored_value_is_not_the_secret():
    key, secret = _key(), _app_secret()

    stored = crypto.encrypt_secret(secret, [key])

    assert secret.encode() not in stored
    assert secret.encode() not in base64.urlsafe_b64decode(stored)
    # A fresh IV every time, so the same secret never encrypts the same way.
    assert crypto.encrypt_secret(secret, [key]) != stored


def test_a_wrong_key_cannot_decrypt():
    stored = crypto.encrypt_secret(_app_secret(), [_key()])

    with pytest.raises(InvalidToken):
        crypto.decrypt_secret(stored, [_key()])


def test_an_altered_value_is_refused():
    key = _key()
    raw = bytearray(base64.urlsafe_b64decode(crypto.encrypt_secret(_app_secret(), [key])))
    raw[-40] ^= 1  # one bit of the ciphertext, just before the 32-byte HMAC

    with pytest.raises(InvalidToken):
        crypto.decrypt_secret(base64.urlsafe_b64encode(bytes(raw)), [key])


def test_rotation_the_old_key_still_decrypts_and_the_new_key_encrypts():
    old, new = _key(), _key()
    secret = _app_secret()
    stored_before = crypto.encrypt_secret(secret, [old])

    # The new key goes first; the old one stays while anything still needs it.
    assert crypto.decrypt_secret(stored_before, [new, old]) == secret

    stored_after = crypto.encrypt_secret(secret, [new, old])
    assert crypto.decrypt_secret(stored_after, [new]) == secret
    with pytest.raises(InvalidToken):
        crypto.decrypt_secret(stored_after, [old])


def test_without_a_key_nothing_is_encrypted():
    with pytest.raises(ValueError):
        crypto.encrypt_secret(_app_secret(), [])


# --- Emailed and recovery codes ---------------------------------------------

def test_codes_are_always_six_digits():
    for _ in range(2000):
        assert re.fullmatch(r"\d{6}", crypto.new_code())


@pytest.mark.parametrize("drawn, code", [(0, "000000"), (42, "000042"), (999_999, "999999")])
def test_codes_are_zero_padded_and_drawn_from_all_million(monkeypatch, drawn, code):
    asked = []

    def randbelow(limit: int) -> int:
        asked.append(limit)
        return drawn

    monkeypatch.setattr(crypto.secrets, "randbelow", randbelow)

    assert crypto.new_code() == code
    assert asked == [1_000_000]


def test_a_code_hash_is_hmac_sha256_of_the_challenge_and_the_code():
    challenge_id = uuid.uuid4()
    expected = hmac.new(
        PEPPER.encode(), f"{challenge_id}:123456".encode(), hashlib.sha256
    ).digest()

    assert crypto.hash_code(PEPPER, challenge_id, "123456") == expected
    assert crypto.hash_code(PEPPER, str(challenge_id), "123456") == expected
    # 32 bytes: the only size the database accepts for a code.
    assert len(expected) == 32


def test_the_same_code_hashes_differently_on_each_challenge():
    first = crypto.hash_code(PEPPER, uuid.uuid4(), "123456")
    second = crypto.hash_code(PEPPER, uuid.uuid4(), "123456")

    assert first != second


def test_only_the_right_code_for_the_right_challenge_matches():
    challenge_id = uuid.uuid4()
    stored = crypto.hash_code(PEPPER, challenge_id, "123456")

    assert crypto.code_matches(PEPPER, challenge_id, "123456", stored)
    assert not crypto.code_matches(PEPPER, challenge_id, "123457", stored)
    assert not crypto.code_matches(PEPPER, uuid.uuid4(), "123456", stored)
    assert not crypto.code_matches(secrets.token_urlsafe(32), challenge_id, "123456", stored)


def test_codes_are_compared_in_constant_time(monkeypatch):
    compared = []
    real_compare = hmac.compare_digest

    def spy(a, b):
        compared.append((a, b))
        return real_compare(a, b)

    monkeypatch.setattr(crypto.hmac, "compare_digest", spy)
    challenge_id = uuid.uuid4()
    stored = crypto.hash_code(PEPPER, challenge_id, "123456")

    assert crypto.code_matches(PEPPER, challenge_id, "123456", stored)
    assert compared == [(stored, stored)]


@pytest.mark.parametrize("pepper", [None, "", "x" * (MIN_PEPPER_BYTES - 1)])
def test_a_missing_or_short_pepper_is_refused(pepper):
    with pytest.raises(ValueError):
        crypto.hash_code(pepper, uuid.uuid4(), "123456")


# --- Trusted computers ------------------------------------------------------

def test_a_device_token_is_32_random_bytes():
    token = crypto.new_device_token()

    assert len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) == 32
    assert len({crypto.new_device_token() for _ in range(1000)}) == 1000


def test_only_the_hash_of_a_device_token_is_kept():
    token = crypto.new_device_token()

    stored = crypto.hash_device_token(token)

    assert stored == hashlib.sha256(token.encode()).digest()
    # The database takes 32 bytes and nothing else. The token as the browser
    # holds it is 43 characters, so storing it by mistake would be refused.
    assert len(stored) == 32
    assert len(token.encode()) == 43


def test_a_device_is_found_again_by_the_hash_of_its_token():
    tokens = [crypto.new_device_token() for _ in range(5)]
    devices = {crypto.hash_device_token(token): n for n, token in enumerate(tokens)}

    assert devices[crypto.hash_device_token(tokens[3])] == 3
    assert crypto.hash_device_token(crypto.new_device_token()) not in devices


# --- Masking ----------------------------------------------------------------

@pytest.mark.parametrize(
    "email, shown",
    [
        ("thandi@example.test", f"t{DOTS}@example.test"),
        ("t@example.test", f"t{DOTS}@example.test"),
        ("  thandi@example.test ", f"t{DOTS}@example.test"),
        ("no-at-sign", DOTS),
        ("@example.test", DOTS),
        ("thandi@", DOTS),
        ("", DOTS),
    ],
)
def test_an_email_is_masked_to_its_first_letter_and_domain(email, shown):
    assert crypto.mask_email(email) == shown


def test_masking_hides_how_long_the_name_is():
    assert crypto.mask_email("t@example.test") == crypto.mask_email("thandiwe.m@example.test")
