"""Request and response contracts.

Everything the browser sends is revalidated here. The client-side checks in
`registration.ts` exist to give people fast, kind feedback; these exist because
the browser is hostile and client validation is a courtesy, not a control
(AIA foundation 03 §6).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

PlanCode = Literal["plan_a", "plan_b", "plan_c", "dome_plan", "unsure"]
CoverArea = Literal["edolobheni", "emakhaya"]
CoffinOption = Literal["flat_lid", "casket"]
LanguageCode = Literal["zu", "en", "xh", "af", "st", "other"]
PaymentFrequency = Literal["monthly", "once_off"]
PaymentPreference = Literal["debit_order", "eft", "cash", "card", "undecided"]
MaritalStatus = Literal[
    "single", "married", "customary_union", "divorced", "widowed", "other"
]

_MOBILE_RE = re.compile(r"^\+27[6-8][0-9]{8}$")
_ID_RE = re.compile(r"^[0-9]{13}$")

# --- What a typed field may contain -------------------------------------------------
#
# Refused because no person types them, and each one is a way in:
# - control characters: a NUL (\x00) made the insert itself fail with a 500,
#   because Postgres text cannot hold one;
# - Unicode direction overrides and invisible characters (U+202E, U+200B, ...):
#   they make a name DISPLAY as something other than what is stored, in the
#   portal and in the office's email;
# - a leading = + or @: spreadsheet programs run such a cell as a formula when
#   the office exports and opens the data (CSV injection).
# U+200C/U+200D (zero-width joiners) stay allowed: real scripts and emoji use them.
_CONTROL = "\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
_INVISIBLE = "​‎‏‪-‮⁦-⁩﻿"
_BAD_IN_LINE = re.compile(f"[\t\n\r{_CONTROL}{_INVISIBLE}]")
_BAD_IN_TEXT = re.compile(f"[{_CONTROL}{_INVISIBLE}]")  # notes may span lines
_FORMULA_START = ("=", "+", "@")
# A practical address: no spaces, commas, quotes or angle brackets, so one
# field can only ever name one mailbox when it becomes an email's To: header.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_UNUSUAL = "Please use only letters, numbers and ordinary punctuation"


def clean_line(value: str | None) -> str | None:
    """A single-line text field: no hidden characters, no leading formula."""
    if value is None:
        return None
    if _BAD_IN_LINE.search(value):
        raise ValueError(_UNUSUAL)
    if value.startswith(_FORMULA_START):
        raise ValueError("This can't start with = + or @")
    return value


def clean_text(value: str | None) -> str | None:
    """Free text (notes): line breaks allowed, nothing hidden."""
    if value is None:
        return None
    if _BAD_IN_TEXT.search(value):
        raise ValueError(_UNUSUAL)
    if value.startswith(_FORMULA_START):
        raise ValueError("This can't start with = + or @")
    return value


def clean_name(value: str | None) -> str | None:
    """A person's name: at least one letter, no markup, single spaces."""
    value = clean_line(value)
    if value is None:
        return None
    if "<" in value or ">" in value or not any(char.isalpha() for char in value):
        raise ValueError("Please enter a name using letters")
    return " ".join(value.split())


Line = Annotated[str, AfterValidator(clean_line)]
Text = Annotated[str, AfterValidator(clean_text)]
Name = Annotated[str, AfterValidator(clean_name)]


def normalise_mobile(raw: str) -> str:
    digits = re.sub(r"[\s()-]", "", raw or "")
    if re.fullmatch(r"0[6-8][0-9]{8}", digits):
        return "+27" + digits[1:]
    if re.fullmatch(r"\+?27[6-8][0-9]{8}", digits):
        return digits if digits.startswith("+") else "+" + digits
    return digits


def valid_sa_id(raw: str) -> bool:
    """13 digits, a plausible birth date, and a valid Luhn check digit."""
    digits = re.sub(r"\s", "", raw or "")
    if not _ID_RE.fullmatch(digits):
        return False
    month, day = int(digits[2:4]), int(digits[4:6])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    # Standard Luhn: every second digit counting from the RIGHT of the 12-digit
    # payload is doubled, i.e. the digit immediately left of the check digit.
    total = 0
    for index, char in enumerate(reversed(digits[:12])):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - total % 10) % 10 == int(digits[12])


class LeadIn(BaseModel):
    """Stage 1 — the minimum needed to phone somebody back."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    first_name: Name = Field(min_length=1, max_length=100)
    surname: Name = Field(min_length=1, max_length=100)
    mobile_number: str
    email: str | None = Field(default=None, max_length=255)
    city: Line | None = Field(default=None, max_length=120)
    suburb_or_town: Line | None = Field(default=None, max_length=120)
    province: Line | None = Field(default=None, max_length=120)
    language_preference: LanguageCode = "zu"
    plan_interest: PlanCode = "unsure"
    best_contact_time: Line | None = Field(default=None, max_length=60)
    how_heard: Line | None = Field(default=None, max_length=120)
    contact_consent: bool
    marketing_consent: bool = False

    # Honeypot. The form renders this hidden and off-screen, so a person never
    # sees it and never fills it. Automated form-fillers populate every input
    # they find, which is exactly what gives them away.
    #
    # Named to look attractive to a bot rather than like a trap.
    website: str = ""

    @field_validator("website")
    @classmethod
    def _honeypot(cls, value: str) -> str:
        if value.strip():
            # Deliberately the same generic message a real validation failure
            # gives, so a bot author learns nothing about why it was rejected.
            raise ValueError("Enter a valid value")
        return ""

    @field_validator("mobile_number")
    @classmethod
    def _mobile(cls, value: str) -> str:
        normalised = normalise_mobile(value)
        if not _MOBILE_RE.fullmatch(normalised):
            raise ValueError("Enter a valid South African mobile number, e.g. 082 123 4567")
        return normalised

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if not value:
            return None
        if not _EMAIL_RE.fullmatch(value) or value.startswith(_FORMULA_START):
            raise ValueError("Enter a valid email address")
        return value.lower()

    @field_validator("contact_consent")
    @classmethod
    def _consent(cls, value: bool) -> bool:
        # POPIA: without consent there is no lawful basis to store or use this.
        if not value:
            raise ValueError("We need your permission before we may contact you")
        return value


class ApplicationIn(BaseModel):
    """Stage 2 — everything needed to actually open a policy.

    Note what is NOT here: account number, branch code, card number. Those are
    the payment provider's job, never ours.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id_number: str | None = None
    date_of_birth: date | None = None
    marital_status: MaritalStatus | None = None
    address_line1: Line | None = Field(default=None, max_length=200)
    address_line2: Line | None = Field(default=None, max_length=200)
    postal_code: Line | None = Field(default=None, max_length=10)
    cover_area: CoverArea | None = None
    plan_selected: PlanCode | None = None
    coffin_choice: CoffinOption | None = None
    age_band: Line | None = Field(default=None, max_length=20)
    # No premium field, on purpose: the API sets it from the price list for the
    # chosen plan (enquiries.py). A premium sent by a browser is refused (422),
    # because anyone can send any number.
    payment_frequency: PaymentFrequency | None = None
    payment_preference: PaymentPreference | None = None
    number_of_dependants: int | None = Field(default=None, ge=0, le=20)
    next_of_kin_name: Name | None = Field(default=None, max_length=200)
    next_of_kin_mobile: str | None = None
    next_of_kin_relationship: Line | None = Field(default=None, max_length=100)
    beneficiary_name: Name | None = Field(default=None, max_length=200)
    beneficiary_mobile: str | None = None
    beneficiary_relationship: Line | None = Field(default=None, max_length=100)
    notes: Text | None = Field(default=None, max_length=2000)
    terms_accepted: bool

    @field_validator("id_number")
    @classmethod
    def _id_number(cls, value: str | None) -> str | None:
        if not value:
            return None
        digits = re.sub(r"\s", "", value)
        if not valid_sa_id(digits):
            raise ValueError("That ID number is not valid. Please check all 13 digits")
        return digits

    @field_validator("next_of_kin_mobile", "beneficiary_mobile")
    @classmethod
    def _optional_mobile(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalised = normalise_mobile(value)
        if not _MOBILE_RE.fullmatch(normalised):
            raise ValueError("Enter a valid South African mobile number")
        return normalised

    @field_validator("terms_accepted")
    @classmethod
    def _terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Please accept the terms to submit your application")
        return value


class EnquiryOut(BaseModel):
    """What the browser gets back. Deliberately narrow — no full record echo."""

    id: str
    reference: str
    first_name: str
    surname: str
    mobile_number: str
    plan_interest: PlanCode
