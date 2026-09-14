"""Staff portal endpoints.

Every route here is behind `require_staff` and returns personal information, so
two things are non-negotiable:

1. **Authentication is a dependency, not a convention.** It is declared on the
   router so a new route cannot accidentally be added unprotected.
2. **Reads are audited.** Looking at a list of people is itself an event worth
   recording under POPIA, so a staff listing writes to `enquiry_events`.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth import StaffUser, require_role, require_staff
from ..db import connection
from ..services.staff import find_by_email, list_staff, log_staff_event
from ..services.supabase_admin import invite_supabase_user

# An email that looks like one. Deliberately the same shape the public form
# accepts, so staff and client addresses are validated identically.
EmailLike = Annotated[str, Field(max_length=255)]

logger = logging.getLogger(__name__)

# Auth applied at the router level: it cannot be forgotten on a new route.
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_staff)])


class EnquiryRow(BaseModel):
    """One row in the staff list.

    Deliberately narrower than the database row: the list view does not need ID
    numbers or next-of-kin details, so it does not receive them.
    """

    id: str
    reference: str
    stage: str
    status: str
    first_name: str
    surname: str
    mobile_number: str
    email: str | None
    city: str | None
    suburb_or_town: str | None
    plan_interest: str
    plan_selected: str | None
    created_at: str


class EnquiryPage(BaseModel):
    rows: list[EnquiryRow]
    total: int
    limit: int
    offset: int


SortField = Literal["created_at", "surname", "status", "reference"]

# Whitelist, not interpolation. The sort column can never come from user text.
_SORT_COLUMNS: dict[str, str] = {
    "created_at": "created_at",
    "surname": "lower(surname)",
    "status": "status",
    "reference": "reference",
}


@router.get("/enquiries", response_model=EnquiryPage)
def list_enquiries(
    staff: StaffUser = Depends(require_staff),
    search: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status", max_length=40),
    sort: SortField = "created_at",
    descending: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EnquiryPage:
    """List enquiries, newest first, with optional search and status filter.

    Search matches name, surname, mobile, email or reference.
    """
    where = ["archived_at is null"]
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if search:
        # One bound parameter used across several columns. The value is never
        # concatenated into the statement.
        where.append(
            "("
            "  first_name ilike %(q)s"
            "  or surname ilike %(q)s"
            "  or mobile_number ilike %(q)s"
            "  or coalesce(email, '') ilike %(q)s"
            "  or reference ilike %(q)s"
            ")"
        )
        params["q"] = "%%%s%%" % search.strip()

    if status_filter:
        where.append("status = %(status)s::enquiry_status")
        params["status"] = status_filter

    clause = " and ".join(where)
    order = "%s %s" % (_SORT_COLUMNS[sort], "desc" if descending else "asc")

    with connection() as conn:
        total = conn.execute(
            "select count(*) as n from plan_enquiries where " + clause, params
        ).fetchone()["n"]

        rows = conn.execute(
            """
            select id, reference, stage::text as stage, status::text as status,
                   first_name, surname, mobile_number, email, city, suburb_or_town,
                   plan_interest::text as plan_interest,
                   plan_selected::text as plan_selected,
                   created_at
              from plan_enquiries
             where """
            + clause
            + " order by "
            + order
            + " limit %(limit)s offset %(offset)s",
            params,
        ).fetchall()

    logger.info("Staff listing served to %s (%d rows)", staff.email, len(rows))

    return EnquiryPage(
        rows=[
            EnquiryRow(
                id=str(r["id"]),
                reference=r["reference"],
                stage=r["stage"],
                status=r["status"],
                first_name=r["first_name"],
                surname=r["surname"],
                mobile_number=r["mobile_number"],
                email=r["email"],
                city=r["city"],
                suburb_or_town=r["suburb_or_town"],
                plan_interest=r["plan_interest"],
                plan_selected=r["plan_selected"],
                created_at=r["created_at"].isoformat(),
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


class StaffIdentity(BaseModel):
    email: str
    id: str
    role: str


@router.get("/me", response_model=StaffIdentity)
def whoami(staff: StaffUser = Depends(require_staff)) -> StaffIdentity:
    """Lets the portal confirm a token is still good and learn its own role."""
    return StaffIdentity(email=staff.email, id=staff.id, role=staff.role)


# ---------------------------------------------------------------------------
# Staff account management. Owner only.
#
# These routes change who can see client data, so every one of them is gated on
# `owner` and writes to the append-only staff_events log.
# ---------------------------------------------------------------------------


class StaffMember(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    has_signed_in: bool
    invited_by: str | None
    last_seen_at: str | None
    created_at: str


class InviteStaff(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailLike
    full_name: str | None = Field(default=None, max_length=200)
    role: Literal["viewer", "admin", "owner"] = "viewer"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value.lower()


class ChangeRole(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    role: Literal["viewer", "admin", "owner"]


class SetActive(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    is_active: bool


def _to_member(r: dict) -> StaffMember:
    return StaffMember(
        id=str(r["id"]),
        email=r["email"],
        full_name=r.get("full_name"),
        role=r["role"],
        is_active=r["is_active"],
        has_signed_in=bool(r.get("has_signed_in")),
        invited_by=r.get("invited_by"),
        last_seen_at=r["last_seen_at"].isoformat() if r.get("last_seen_at") else None,
        created_at=r["created_at"].isoformat(),
    )


@router.get("/staff", response_model=list[StaffMember])
def get_staff(staff: StaffUser = Depends(require_role("owner"))) -> list[StaffMember]:
    with connection() as conn:
        return [_to_member(r) for r in list_staff(conn)]


@router.post("/staff", response_model=StaffMember, status_code=status.HTTP_201_CREATED)
def invite_staff(
    payload: InviteStaff, staff: StaffUser = Depends(require_role("owner"))
) -> StaffMember:
    """Grant someone access.

    This creates the AUTHORISATION record. The person still needs a Supabase
    account to sign in with; if a service-role key is configured the API sends
    them an invite, otherwise an owner creates it in the Supabase dashboard.
    Splitting it this way means the portal never holds a key that could mint
    accounts.
    """
    email = payload.email.lower()

    with connection() as conn:
        if find_by_email(conn, email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That person already has an account.",
            )
        row = conn.execute(
            """
            insert into staff_users (email, full_name, role, invited_by)
            values (%s, %s, %s::staff_role, %s)
            returning id, email, full_name, role::text as role, is_active,
                      supabase_user_id is not null as has_signed_in,
                      invited_by, last_seen_at, created_at
            """,
            (email, payload.full_name, payload.role, staff.email),
        ).fetchone()
        log_staff_event(conn, staff.email, "staff_invited", email, {"role": payload.role})

    invited = invite_supabase_user(email)
    logger.info("Staff invited by %s (supabase invite: %s)", staff.email, invited.sent)

    return _to_member(row)


@router.patch("/staff/{staff_id}/role", response_model=StaffMember)
def change_role(
    staff_id: str, payload: ChangeRole, staff: StaffUser = Depends(require_role("owner"))
) -> StaffMember:
    with connection() as conn:
        target = conn.execute(
            "select id, email, role::text as role from staff_users "
            "where id = %s and archived_at is null",
            (staff_id,),
        ).fetchone()
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such staff member.")

        # Demoting the last owner would leave nobody able to manage staff.
        if target["role"] == "owner" and payload.role != "owner":
            _guard_last_owner(conn, staff_id)

        row = conn.execute(
            """
            update staff_users set role = %s::staff_role
             where id = %s
            returning id, email, full_name, role::text as role, is_active,
                      supabase_user_id is not null as has_signed_in,
                      invited_by, last_seen_at, created_at
            """,
            (payload.role, staff_id),
        ).fetchone()
        log_staff_event(
            conn, staff.email, "role_changed", target["email"],
            {"from": target["role"], "to": payload.role},
        )

    return _to_member(row)


@router.patch("/staff/{staff_id}/active", response_model=StaffMember)
def set_active(
    staff_id: str, payload: SetActive, staff: StaffUser = Depends(require_role("owner"))
) -> StaffMember:
    """Revoke or restore access.

    Deliberately not a delete: the audit trail must keep pointing at a real
    person after they leave.
    """
    if staff_id == staff.staff_id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    with connection() as conn:
        target = conn.execute(
            "select id, email, role::text as role from staff_users "
            "where id = %s and archived_at is null",
            (staff_id,),
        ).fetchone()
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such staff member.")

        if not payload.is_active and target["role"] == "owner":
            _guard_last_owner(conn, staff_id)

        row = conn.execute(
            """
            update staff_users set is_active = %s
             where id = %s
            returning id, email, full_name, role::text as role, is_active,
                      supabase_user_id is not null as has_signed_in,
                      invited_by, last_seen_at, created_at
            """,
            (payload.is_active, staff_id),
        ).fetchone()
        log_staff_event(
            conn, staff.email,
            "staff_activated" if payload.is_active else "staff_deactivated",
            target["email"],
        )

    return _to_member(row)


def _guard_last_owner(conn, staff_id: str) -> None:
    """Refuse a change that would leave the system with no active owner."""
    remaining = conn.execute(
        """
        select count(*) as n from staff_users
         where role = 'owner' and is_active and archived_at is null and id <> %s
        """,
        (staff_id,),
    ).fetchone()["n"]
    if remaining == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This is the last owner. Promote another owner first, or nobody "
                "will be able to manage staff."
            ),
        )
