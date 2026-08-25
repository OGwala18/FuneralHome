"""Request and response contracts.

Everything the browser sends is revalidated here. The client-side checks in
`registration.ts` exist to give people fast, kind feedback; these exist because
the browser is hostile and client validation is a courtesy, not a control
(AIA foundation 03 §6).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    first_name: str = Field(min_length=1, max_length=100)
    surname: str = Field(min_length=1, max_length=100)
    mobile_number: str
    email: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    suburb_or_town: str | None = Field(default=None, max_length=120)
    province: str | None = Field(default=None, max_length=120)
    language_preference: LanguageCode = "zu"
    plan_interest: PlanCode = "unsure"
    best_contact_time: str | None = Field(default=None, max_length=60)
    how_heard: str | None = Field(default=None, max_length=120)
    contact_consent: bool
    marketing_consent: bool = False

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
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
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
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    postal_code: str | None = Field(default=None, max_length=10)
    cover_area: CoverArea | None = None
    plan_selected: PlanCode | None = None
    coffin_choice: CoffinOption | None = None
    age_band: str | None = Field(default=None, max_length=20)
    premium_amount_cents: int | None = Field(default=None, ge=0)
    payment_frequency: PaymentFrequency | None = None
    payment_preference: PaymentPreference | None = None
    number_of_dependants: int | None = Field(default=None, ge=0, le=20)
    next_of_kin_name: str | None = Field(default=None, max_length=200)
    next_of_kin_mobile: str | None = None
    next_of_kin_relationship: str | None = Field(default=None, max_length=100)
    beneficiary_name: str | None = Field(default=None, max_length=200)
    beneficiary_mobile: str | None = None
    beneficiary_relationship: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
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
