"""The member and policy book: protected, audited reads, and enrolment.

Everything here goes through the API's own restricted database login
(induduzo_api), so a staff member's role is checked by require_staff /
require_role before any row is read or written, and an enrolment is one
transaction. Each read and write is recorded in staff_events.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from ..auth import StaffUser, require_role, require_staff
from ..db import connection
from ..schemas import _MOBILE_RE, LanguageCode, normalise_mobile, valid_sa_id
from ..services import enrolment
from ..services.staff import log_staff_event
from .payments import Instalment, PaymentMethod

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_staff)])


def _audit(staff: StaffUser, event_type: str, subject: str | None = None,
           payload: dict | None = None) -> None:
    with connection() as conn:
        log_staff_event(conn, staff.email, event_type, subject, payload)


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------

class MemberRow(BaseModel):
    id: str
    surname: str
    first_names: str
    email: str | None = None
    id_number_status: str
    created_at: str


class MemberPage(BaseModel):
    rows: list[MemberRow]
    total: int
    limit: int
    offset: int


class MemberPolicy(BaseModel):
    policy_id: UUID
    policy_number: str
    status_code: str
    plan_code: str | None = None
    entry_date: date | None = None
    premium_cents: int | None = None
    cover_cents: int | None = None
    currency: str
    member_type: str
    entry_age: int | None = None
    is_inferred: bool


class MemberPhone(BaseModel):
    number: str
    phone_type: str
    is_primary: bool


class MemberDetail(BaseModel):
    id: str
    surname: str
    first_names: str
    initials: str | None = None
    id_number: str | None = None
    id_number_status: str
    date_of_birth: date | None = None
    email: str | None = None
    source: str
    country_of_birth: str | None = None
    citizenship: str | None = None
    passport_number: str | None = None
    employment_status: str | None = None
    employer_name: str | None = None
    industry: str | None = None
    occupation: str | None = None
    job_role: str | None = None
    source_of_funds: str | None = None
    source_of_funds_other: str | None = None
    salary_day: int | None = None
    phones: list[MemberPhone]
    policies: list[MemberPolicy]


class PolicyRow(BaseModel):
    policy_id: UUID
    policy_number: str
    status_code: str
    status_label: str
    plan_code: str | None = None
    branch_code: str | None = None
    entry_date: date | None = None
    premium_cents: int | None = None
    cover_cents: int | None = None
    currency: str
    main_member_id: UUID | None = None
    main_member_surname: str | None = None
    main_member_first_names: str | None = None
    lives_covered: int


class PolicyLife(BaseModel):
    policy_member_id: UUID
    person_id: UUID
    surname: str
    first_names: str
    id_number: str | None = None
    date_of_birth: date | None = None
    member_type: str
    member_type_label: str
    entry_age: int | None = None
    joined_at: date | None = None


class PolicyPayment(BaseModel):
    method: str
    debit_day: int | None = None
    frequency: str


class PolicyDetail(BaseModel):
    policy_id: UUID
    policy_number: str
    status_code: str
    status_label: str
    plan_code: str | None = None
    plan_option: str | None = None
    branch_code: str | None = None
    entry_date: date | None = None
    premium_cents: int | None = None
    cover_cents: int | None = None
    currency: str
    enquiry_id: UUID | None = None
    enquiry_reference: str | None = None
    # How many dependants the family said they had on the website form. A hint
    # for staff adding them, not a limit.
    dependants_expected: int | None = None
    lives: list[PolicyLife]
    payment: PolicyPayment | None = None
    instalments: list[Instalment]


# ---------------------------------------------------------------------------
# Write models
# ---------------------------------------------------------------------------

Gender = Literal["male", "female", "unspecified"]
BookPlan = Literal["plan_a", "plan_b", "plan_c", "dome_plan"]
DependantType = Literal["spouse", "child", "extended", "beneficiary"]
Frequency = Literal["monthly", "quarterly", "annually", "once_off"]

# The compliance questions asked of a main member (migration 0018).
EmploymentStatus = Literal["full_time", "part_time", "pensioner", "self_employed", "unemployed"]
WORKING = ("full_time", "part_time", "self_employed")
Industry = Literal[
    "agriculture", "construction", "domestic_work", "education", "finance", "government",
    "health", "hospitality", "informal_trade", "manufacturing", "mining", "retail",
    "security", "transport", "other",
]
JobRole = Literal[
    "manager", "supervisor", "admin", "professional", "skilled", "general_worker",
    "owner", "other",
]
SourceOfFunds = Literal["employment", "inheritance", "allowance", "pension", "other"]

# The day of the month a family pays, whatever the method (EFT, deposit, cash,
# later debit order). The owner, 11 Nov 2026: the 1st, the 25th or the 30th.
# The WhatsApp reminder goes out on that day, and a second one the day after if
# it is still unpaid (app/jobs/payment_reminders.py). Stored in
# policy_payments.debit_day. The 30th falls on the 28th or 29th in February.
PAYMENT_DAYS = (1, 25, 30)
DEBIT_DAYS = PAYMENT_DAYS  # the old name, kept for anything that imports it


class _PersonIn(BaseModel):
    """What every life on a policy has, whether main member or dependant."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    surname: str = Field(min_length=1, max_length=100)
    first_names: str = Field(min_length=1, max_length=150)
    id_number: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    mobile: str | None = None
    language_preference: LanguageCode = "zu"

    @field_validator("id_number")
    @classmethod
    def _id_number(cls, value: str | None) -> str | None:
        if not value:
            return None
        digits = re.sub(r"\s", "", value)
        if not valid_sa_id(digits):
            raise ValueError("That ID number is not valid. Please check all 13 digits")
        return digits

    @field_validator("date_of_birth")
    @classmethod
    def _date_of_birth(cls, value: date | None, info: ValidationInfo) -> date | None:
        if value is None:
            return None
        if value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        id_number = info.data.get("id_number")
        if id_number:
            born, _ = enrolment.decode_id(id_number)
            if born is not None and born != value:
                raise ValueError("This date of birth does not match the ID number")
        return value

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalised = normalise_mobile(value)
        if not _MOBILE_RE.fullmatch(normalised):
            raise ValueError("Enter a valid South African mobile number, e.g. 082 123 4567")
        return normalised


class BeneficiaryIn(_PersonIn):
    """Who the policy pays out to. The ID number is optional; the date of birth
    is not, though a valid ID number supplies it."""

    date_of_birth: date | None = Field(default=None, validate_default=True)
    member_type: Literal["beneficiary"] = "beneficiary"

    @field_validator("date_of_birth")
    @classmethod
    def _born(cls, value: date | None, info: ValidationInfo) -> date | None:
        if value is None and not info.data.get("id_number"):
            raise ValueError("Enter the date of birth, or a valid ID number")
        return value


class EnrolmentIn(_PersonIn):
    enquiry_id: UUID | None = None
    initials: str | None = Field(default=None, max_length=10)
    email: str | None = Field(default=None, max_length=255)

    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    suburb: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    province: str | None = Field(default=None, max_length=120)
    postal_code: str | None = None

    # Compliance. ISO 3166 two-letter country codes; 'ZA' is South Africa.
    country_of_birth: str
    citizenship: str
    passport_number: str | None = Field(default=None, validate_default=True)
    employment_status: EmploymentStatus
    employer_name: str | None = Field(default=None, max_length=150, validate_default=True)
    industry: Industry | None = Field(default=None, validate_default=True)
    occupation: str | None = Field(default=None, max_length=100, validate_default=True)
    job_role: JobRole | None = Field(default=None, validate_default=True)
    source_of_funds: SourceOfFunds
    source_of_funds_other: str | None = Field(default=None, max_length=150,
                                              validate_default=True)
    salary_day: int | None = Field(default=None, ge=1, le=31)

    policy_number: str
    plan_code: BookPlan
    # Which price of the plan, e.g. 'single_casket' on Plan C. May be left out
    # for a plan with only one. The premium itself is read from the price list.
    plan_option: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,39}$")
    # One branch is in the reference table today. More arrive with their codes.
    branch_code: Literal["pmburg"] = "pmburg"
    entry_date: date | None = None
    # No premium and no cover here, on purpose: both are read from the price
    # list for the plan, option and age (0020, 0021). Sending either is a 422.

    payment_method: PaymentMethod = "undecided"
    frequency: Frequency = "monthly"
    # The payment day (1st, 25th or 30th) for every method, not only debit
    # orders. Required unless the plan is paid once-off. After `frequency`, so
    # its check can see it.
    debit_day: int | None = Field(default=None, validate_default=True)

    beneficiary: BeneficiaryIn

    @field_validator("debit_day")
    @classmethod
    def _payment_day_needed(cls, value: int | None, info: ValidationInfo) -> int | None:
        if value is None and info.data.get("frequency", "monthly") != "once_off":
            raise ValueError("Choose the payment day: the 1st, 25th or 30th")
        return value

    @field_validator("country_of_birth", "citizenship")
    @classmethod
    def _country(cls, value: str) -> str:
        code = value.upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError("Choose a country")
        return code

    @field_validator("passport_number")
    @classmethod
    def _passport_number(cls, value: str | None, info: ValidationInfo) -> str | None:
        citizenship = info.data.get("citizenship")
        if citizenship == "ZA":
            if value:
                raise ValueError("Only for people who are not South African citizens")
            return None
        if not value:
            if citizenship and not info.data.get("id_number"):
                raise ValueError("Needed for someone who is not a South African citizen "
                                 "and has no SA ID number")
            return None
        normalised = re.sub(r"\s", "", value).upper()
        if not re.fullmatch(r"[A-Z0-9]{5,20}", normalised):
            raise ValueError("A passport number is 5 to 20 letters and digits")
        return normalised

    @field_validator("employer_name", "industry", "occupation", "job_role")
    @classmethod
    def _work(cls, value: str | None, info: ValidationInfo) -> str | None:
        # Only asked of someone who works. Anything sent for anyone else is dropped.
        if info.data.get("employment_status") not in WORKING:
            return None
        if not value:
            raise ValueError("Needed for someone who works")
        return value

    @field_validator("source_of_funds_other")
    @classmethod
    def _funds_other(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("source_of_funds") != "other":
            return None
        if not value:
            raise ValueError("Say where the money comes from")
        return value

    @field_validator("debit_day")
    @classmethod
    def _debit_day(cls, value: int | None) -> int | None:
        if value is not None and value not in PAYMENT_DAYS:
            raise ValueError("Choose the 1st, 25th or 30th of the month")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if not value:
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value.lower()

    @field_validator("postal_code")
    @classmethod
    def _postal_code(cls, value: str | None) -> str | None:
        if not value:
            return None
        if not re.fullmatch(r"[0-9]{4}", value):
            raise ValueError("A postal code is 4 digits")
        return value

    @field_validator("policy_number")
    @classmethod
    def _policy_number(cls, value: str) -> str:
        # 'AA 1332' and 'aa1332' are the same policy as 'AA1332'.
        normalised = re.sub(r"\s+", "", value).upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,29}", normalised):
            raise ValueError("Use letters and digits only, e.g. AA1332")
        return normalised


class DependantIn(_PersonIn):
    member_type: DependantType

    @field_validator("member_type")
    @classmethod
    def _beneficiary_born(cls, value: str, info: ValidationInfo) -> str:
        # As on the enrolment form: a beneficiary always has a date of birth.
        if value == "beneficiary" and not info.data.get("date_of_birth") \
                and not info.data.get("id_number"):
            raise ValueError("A beneficiary needs a date of birth or a valid ID number")
        return value


class EnrolmentOut(BaseModel):
    person_id: UUID
    policy_id: UUID
    policy_number: str
    premium_cents: int
    cover_cents: int | None
    instalments_scheduled: int


class PlanPrice(BaseModel):
    plan_code: str
    option_code: str
    option_label: str
    min_age: int | None = None
    max_age: int | None = None
    premium_cents: int
    # None until the owner gives the cover for this line (0021).
    cover_cents: int | None = None
    currency: str
    billing: Literal["monthly", "once_off"]


class DependantOut(BaseModel):
    person_id: UUID
    policy_member_id: UUID
    existing_person: bool


class PolicyNumber(BaseModel):
    policy_number: str


def _raise_for(exc: Exception) -> None:
    if isinstance(exc, enrolment.Invalid):
        # The same {field: message} shape as any other validation error.
        raise RequestValidationError([{"loc": ("body", *exc.field.split(".")),
                                       "msg": str(exc), "type": "value_error"}]) from exc
    if isinstance(exc, enrolment.Conflict):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if isinstance(exc, enrolment.NotFound):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    raise exc


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@router.get("/members", response_model=MemberPage)
def list_members(staff: StaffUser = Depends(require_staff),
                 search: str | None = Query(default=None, max_length=120),
                 limit: int = Query(default=25, ge=1, le=100),
                 offset: int = Query(default=0, ge=0)) -> MemberPage:
    where = "archived_at is null"
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if search and search.strip():
        # Bound parameters only; the search text never becomes SQL.
        where += (" and (surname ilike %(q)s or first_names ilike %(q)s"
                  " or coalesce(email, '') ilike %(q)s or id_number = %(term)s)")
        params["q"] = "%%%s%%" % search.strip()
        params["term"] = re.sub(r"\s", "", search)

    with connection() as conn:
        total = conn.execute(f"select count(*) as n from people where {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"""
            select id, surname, first_names, email, id_number_status::text as id_number_status,
                   created_at
              from people
             where {where}
             order by lower(surname), lower(first_names), id
             limit %(limit)s offset %(offset)s
            """,
            params,
        ).fetchall()

    _audit(staff, "member_list_viewed", payload={"rows": len(rows)})
    return MemberPage(
        rows=[MemberRow(**{**r, "id": str(r["id"]), "created_at": r["created_at"].isoformat()})
              for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.post("/members", response_model=EnrolmentOut, status_code=status.HTTP_201_CREATED)
def enrol_member(payload: EnrolmentIn,
                 staff: StaffUser = Depends(require_role("admin"))) -> EnrolmentOut:
    """Enrol a main member: person, policy, payment arrangement and schedule."""
    try:
        with connection() as conn:
            result = enrolment.enrol(conn, payload, staff_email=staff.email)
    except (enrolment.Conflict, enrolment.NotFound, enrolment.Invalid) as exc:
        _raise_for(exc)
    return EnrolmentOut(**result)


@router.get("/members/{member_id}", response_model=MemberDetail)
def get_member(member_id: UUID, staff: StaffUser = Depends(require_staff)) -> MemberDetail:
    with connection() as conn:
        person = conn.execute(
            """
            select id, surname, first_names, initials, id_number,
                   id_number_status::text as id_number_status, date_of_birth, email, source,
                   country_of_birth, citizenship, passport_number, employment_status,
                   employer_name, industry, occupation, job_role, source_of_funds,
                   source_of_funds_other, salary_day
              from people
             where id = %s and archived_at is null
            """,
            (member_id,),
        ).fetchone()
        if person is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member.")

        policies = conn.execute(
            """
            select p.id as policy_id, p.policy_number, p.status_code, p.plan_code,
                   p.entry_date, p.premium_cents, p.cover_cents, p.currency,
                   pm.member_type, pm.entry_age, pm.is_inferred
              from policy_members pm
              join policies p on p.id = pm.policy_id and p.archived_at is null
             where pm.person_id = %s and pm.archived_at is null
             order by p.policy_number
            """,
            (member_id,),
        ).fetchall()
        phones = conn.execute(
            """
            select number, phone_type::text as phone_type, is_primary
              from person_phones
             where person_id = %s and archived_at is null
             order by is_primary desc, created_at desc
            """,
            (member_id,),
        ).fetchall()

    _audit(staff, "member_detail_viewed", subject=str(member_id))
    return MemberDetail(
        **{**person, "id": str(person["id"])},
        phones=[MemberPhone(**p) for p in phones],
        policies=[MemberPolicy(**p) for p in policies],
    )


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

@router.get("/policies", response_model=list[PolicyRow])
def list_policies(staff: StaffUser = Depends(require_staff)) -> list[PolicyRow]:
    with connection() as conn:
        rows = conn.execute(
            """
            select policy_id, policy_number, status_code, status_label, plan_code,
                   branch_code, entry_date, premium_cents, cover_cents, currency,
                   main_member_id, main_member_surname, main_member_first_names,
                   lives_covered
              from policy_overview
             order by policy_number
             limit 1000
            """
        ).fetchall()
    _audit(staff, "policy_list_viewed", payload={"rows": len(rows)})
    return [PolicyRow(**r) for r in rows]


# Declared before /policies/{policy_id} so the literal path is matched first.
@router.get("/policies/next-number", response_model=PolicyNumber)
def next_policy_number() -> PolicyNumber:
    with connection() as conn:
        return PolicyNumber(policy_number=enrolment.suggest_policy_number(conn))


@router.get("/plans/prices", response_model=list[PlanPrice])
def plan_prices() -> list[PlanPrice]:
    """The price list, so the enrolment form shows the premium before saving.
    The API prices the policy again from the same rows when it is saved."""
    with connection() as conn:
        return [PlanPrice(**r) for r in enrolment.price_list(conn)]


@router.get("/policies/{policy_id}", response_model=PolicyDetail)
def get_policy(policy_id: UUID, staff: StaffUser = Depends(require_staff)) -> PolicyDetail:
    with connection() as conn:
        policy = conn.execute(
            """
            select p.id as policy_id, p.policy_number, p.status_code, s.label as status_label,
                   p.plan_code, p.plan_option, p.branch_code, p.entry_date, p.premium_cents,
                   p.cover_cents, p.currency, p.enquiry_id, e.reference as enquiry_reference,
                   e.number_of_dependants as dependants_expected
              from policies p
              join ref_policy_statuses s on s.code = p.status_code
              left join plan_enquiries e on e.id = p.enquiry_id
             where p.id = %s and p.archived_at is null
            """,
            (policy_id,),
        ).fetchone()
        if policy is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such policy.")

        lives = conn.execute(
            """
            select pm.id as policy_member_id, pe.id as person_id, pe.surname, pe.first_names,
                   pe.id_number, pe.date_of_birth, pm.member_type,
                   t.label as member_type_label, pm.entry_age, pm.joined_at
              from policy_members pm
              join people pe on pe.id = pm.person_id
              join ref_member_types t on t.code = pm.member_type
             where pm.policy_id = %s and pm.archived_at is null
             order by t.sort_order, pe.date_of_birth nulls last, pe.surname
            """,
            (policy_id,),
        ).fetchall()
        payment = conn.execute(
            """
            select method, debit_day, frequency::text as frequency
              from policy_payments
             where policy_id = %s and is_active and archived_at is null
            """,
            (policy_id,),
        ).fetchone()
        schedule = conn.execute(
            """
            select id, policy_id, due_date, amount_cents, currency, status, paid_at,
                   paid_amount_cents, paid_method, recorded_by, notes
              from premium_instalments
             where policy_id = %s and archived_at is null
             order by due_date
            """,
            (policy_id,),
        ).fetchall()

    _audit(staff, "policy_detail_viewed", subject=str(policy_id))
    return PolicyDetail(
        **policy,
        lives=[PolicyLife(**r) for r in lives],
        payment=PolicyPayment(**payment) if payment else None,
        instalments=[Instalment(**r) for r in schedule],
    )


@router.post("/policies/{policy_id}/members", response_model=DependantOut,
             status_code=status.HTTP_201_CREATED)
def add_dependant(policy_id: UUID, payload: DependantIn,
                  staff: StaffUser = Depends(require_role("admin"))) -> DependantOut:
    """Add a spouse, child, extended family member or beneficiary to a policy."""
    try:
        with connection() as conn:
            result = enrolment.add_dependant(conn, str(policy_id), payload,
                                             staff_email=staff.email)
    except (enrolment.Conflict, enrolment.NotFound) as exc:
        _raise_for(exc)
    return DependantOut(**result)
