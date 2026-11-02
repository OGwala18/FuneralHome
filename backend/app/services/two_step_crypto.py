"""The cryptography behind staff two-step sign-in.

docs/feature-2-staff-two-factor.md §6, §7 and §9. Small pure functions, with no
database, no network and no logging, so each one is tested on its own and the
rules in §15 are easy to check in one place:

* an authenticator app's secret is stored only encrypted;
* an emailed or recovery code is stored only as an HMAC, keyed with a pepper
  the database never sees;
* a trusted computer's token is stored only as its SHA-256 hash.

Never log what goes into or comes out of these functions, here or in a caller.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Sequence
from uuid import UUID

from cryptography.fernet import Fernet, MultiFernet

from ..config import MIN_PEPPER_BYTES

# Six digits: what every authenticator app shows, and what someone can read
# from an email and type in.
CODE_DIGITS = 6

# 256 bits. Far too many to guess, which is why a plain SHA-256, with no salt
# and no pepper, is enough to store the token.
DEVICE_TOKEN_BYTES = 32

# Shown in place of the hidden part of an email address.
_MASK = "•••"  # •••


# --- Authenticator-app secrets ----------------------------------------------

def _cipher(keys: Sequence[str]) -> MultiFernet:
    if not keys:
        raise ValueError("TWO_STEP_ENCRYPTION_KEYS is not set.")
    # The first key encrypts and every key decrypts, so a key is rotated by
    # putting a new one first and keeping the old one while it is still needed.
    return MultiFernet([Fernet(key) for key in keys])


def encrypt_secret(secret: str, keys: Sequence[str]) -> bytes:
    """Encrypt an authenticator-app secret, for staff_totp_factors.secret_encrypted.

    Authenticated encryption with a fresh random IV, so the same secret never
    encrypts to the same bytes twice, and any change to the stored value is
    caught when it is decrypted.
    """
    return _cipher(keys).encrypt(secret.encode("utf-8"))


def decrypt_secret(encrypted: bytes, keys: Sequence[str]) -> str:
    """The secret back again.

    Raises cryptography.fernet.InvalidToken if none of the keys opens it, or if
    the stored value was altered.
    """
    return _cipher(keys).decrypt(encrypted).decode("utf-8")


# --- Emailed and recovery codes ---------------------------------------------

def new_code() -> str:
    """A fresh 6-digit code, zero-padded. Every value from 000000 to 999999 is
    equally likely."""
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def hash_code(pepper: str | None, context: str | UUID, code: str) -> bytes:
    """HMAC-SHA256 of a code, bound to what it was issued for.

    This is the only form a code is ever stored in. `context` is the challenge
    id for an emailed code, so the same six digits hash differently on every
    challenge. `code` must be exactly as issued, so normalise what someone typed
    before checking it.

    Refuses a missing or short pepper rather than produce a hash anyone could
    recompute.
    """
    key = (pepper or "").encode("utf-8")
    if len(key) < MIN_PEPPER_BYTES:
        raise ValueError("TWO_STEP_CODE_PEPPER is missing or too short.")
    return hmac.new(key, f"{context}:{code}".encode("utf-8"), hashlib.sha256).digest()


def code_matches(pepper: str | None, context: str | UUID, code: str, stored: bytes) -> bool:
    """Whether `code` is the one behind a stored hash.

    Compared in constant time, so how long the check takes says nothing about
    how close a guess was.
    """
    return hmac.compare_digest(hash_code(pepper, context, code), stored)


# --- Trusted computers ------------------------------------------------------

def new_device_token() -> str:
    """A trusted-computer token for the browser to keep: 32 random bytes, base64url.

    Handed to the portal once and never stored. The database keeps only
    hash_device_token() of it.
    """
    return secrets.token_urlsafe(DEVICE_TOKEN_BYTES)


def hash_device_token(token: str) -> bytes:
    """SHA-256 of a device token, as staff_trusted_devices.token_hash holds it.

    Hashes exactly what the browser sent, so a malformed header simply matches
    no row.
    """
    return hashlib.sha256(token.encode("utf-8")).digest()


# --- Showing where a code went ----------------------------------------------

def mask_email(email: str) -> str:
    """t•••@induduzo.co.za: enough to recognise your own address, no more.

    The first character and the domain, around a mask of fixed length, so the
    length of the name isn't given away either. Anything that doesn't look like
    an address is masked completely.
    """
    local, at, domain = email.strip().rpartition("@")
    if not (at and local and domain):
        return _MASK
    return f"{local[0]}{_MASK}@{domain}"
