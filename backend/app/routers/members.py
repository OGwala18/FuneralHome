"""Protected, audited reads of the imported Supabase member and policy book."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from ..auth import StaffUser, require_staff
from ..db import connection
from ..services.member_book import member_book_get
from ..services.staff import log_staff_event

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_staff)])


def _jwt(request: Request) -> str:
    # require_staff has already checked this exact token and the local staff row.
    return request.headers["authorization"].split(" ", 1)[1]


def _audit(staff: StaffUser, event_type: str, subject: str | None = None,
           payload: dict | None = None) -> None:
    with connection() as conn:
        log_staff_event(conn, staff.email, event_type, subject, payload)


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
    policy_number: str
    status_code: str
    plan_code: str | None = None
    entry_date: str | None = None
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
    date_of_birth: str | None = None
    email: str | None = None
    source: str
    phones: list[MemberPhone]
    policies: list[MemberPolicy]


class PolicyRow(BaseModel):
    policy_id: str
    policy_number: str
    status_code: str
    status_label: str
    plan_code: str | None = None
    branch_code: str | None = None
    entry_date: str | None = None
    premium_cents: int | None = None
    cover_cents: int | None = None
    currency: str
    main_member_id: str | None = None
    main_member_surname: str | None = None
    main_member_first_names: str | None = None
    lives_covered: int


@router.get("/members", response_model=MemberPage)
def list_members(request: Request, staff: StaffUser = Depends(require_staff),
                 search: str | None = Query(default=None, max_length=120),
                 limit: int = Query(default=25, ge=1, le=100),
                 offset: int = Query(default=0, ge=0)) -> MemberPage:
    params = {
        "select": "id,surname,first_names,email,id_number_status,created_at",
        "order": "surname.asc,first_names.asc,id.asc",
        "limit": str(limit),
        "offset": str(offset),
        "archived_at": "is.null",
    }
    if search:
        term = search.strip()
        # PostgREST parses operators inside an OR expression. Keep user text
        # out of that grammar while supporting ordinary names and ID numbers.
        if not re.fullmatch(r"[\w\s.'-]+", term):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Search contains unsupported characters.")
        params["or"] = (
            "(surname.ilike.*%s*,first_names.ilike.*%s*," 
            "email.ilike.*%s*,id_number.eq.%s)" % (term, term, term, term)
        )

    rows, total = member_book_get("people", params, _jwt(request), count=True)
    _audit(staff, "member_list_viewed", payload={"rows": len(rows)})
    return MemberPage(rows=rows, total=total if total is not None else len(rows),
                      limit=limit, offset=offset)


@router.get("/members/{member_id}", response_model=MemberDetail)
def get_member(member_id: str, request: Request,
               staff: StaffUser = Depends(require_staff)) -> MemberDetail:
    try:
        member_id = str(uuid.UUID(member_id))
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member.")
    rows, _ = member_book_get("people", {
        "select": "id,surname,first_names,initials,id_number,id_number_status,date_of_birth,email,source",
        "id": "eq." + member_id,
        "archived_at": "is.null",
        "limit": "1",
    }, _jwt(request))
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member.")

    memberships, _ = member_book_get("policy_members", {
        "select": "member_type,entry_age,is_inferred,policies(policy_number,status_code,plan_code,entry_date,premium_cents,cover_cents,currency)",
        "person_id": "eq." + member_id,
        "archived_at": "is.null",
    }, _jwt(request))
    phones, _ = member_book_get("person_phones", {
        "select": "number,phone_type,is_primary",
        "person_id": "eq." + member_id,
        "archived_at": "is.null",
        "order": "is_primary.desc,created_at.desc",
    }, _jwt(request))
    policies: list[dict[str, Any]] = []
    for membership in memberships:
        policy = membership.get("policies")
        if isinstance(policy, dict):
            policies.append({**policy, "member_type": membership["member_type"],
                             "entry_age": membership.get("entry_age"),
                             "is_inferred": membership["is_inferred"]})
    _audit(staff, "member_detail_viewed", subject=member_id)
    return MemberDetail(**rows[0], phones=phones, policies=policies)


@router.get("/policies", response_model=list[PolicyRow])
def list_policies(request: Request,
                  staff: StaffUser = Depends(require_staff)) -> list[PolicyRow]:
    rows, _ = member_book_get("policy_overview", {
        "select": "policy_id,policy_number,status_code,status_label,plan_code,branch_code,entry_date,premium_cents,cover_cents,currency,main_member_id,main_member_surname,main_member_first_names,lives_covered",
        "order": "policy_number.asc",
        "limit": "1000",
    }, _jwt(request))
    _audit(staff, "policy_list_viewed", payload={"rows": len(rows)})
    return [PolicyRow(**row) for row in rows]
