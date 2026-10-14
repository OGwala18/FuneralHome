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

    policy_number: str
    plan_code: BookPlan | None = None
    # One branch is in the reference table today. More arrive with their codes.
    branch_code: Literal["pmburg"] = "pmburg"
    entry_date: date | None = None
    premium_cents: int = Field(ge=0, le=100_000_000)
    cover_cents: int | None = Field(default=None, ge=0, le=10_000_000_000)

    payment_method: PaymentMethod = "undecided"
    debit_day: int | None = Field(default=None, ge=1, le=31)
    frequency: Literal["monthly", "once_off"] = "monthly"

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


class EnrolmentOut(BaseModel):
    person_id: UUID
    policy_id: UUID
    policy_number: str
    instalments_scheduled: int


class DependantOut(BaseModel):
    person_id: UUID
    policy_member_id: UUID
    existing_person: bool


class PolicyNumber(BaseModel):
    policy_number: str


def _raise_for(exc: Exception) -> None:
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
    except (enrolment.Conflict, enrolment.NotFound) as exc:
        _raise_for(exc)
    return EnrolmentOut(**result)


@router.get("/members/{member_id}", response_model=MemberDetail)
def get_member(member_id: UUID, staff: StaffUser = Depends(require_staff)) -> MemberDetail:
    with connection() as conn:
        person = conn.execute(
            """
            select id, surname, first_names, initials, id_number,
                   id_number_status::text as id_number_status, date_of_birth, email, source
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


@router.get("/policies/{policy_id}", response_model=PolicyDetail)
def get_policy(policy_id: UUID, staff: StaffUser = Depends(require_staff)) -> PolicyDetail:
    with connection() as conn:
        policy = conn.execute(
            """
            select p.id as policy_id, p.policy_number, p.status_code, s.label as status_label,
                   p.plan_code, p.branch_code, p.entry_date, p.premium_cents, p.cover_cents,
                   p.currency, p.enquiry_id, e.reference as enquiry_reference,
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
