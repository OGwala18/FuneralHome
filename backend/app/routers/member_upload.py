"""Settings > User upload: add policies to the member book from a spreadsheet.

    POST /api/admin/member-upload/check    the .xlsx as the body: every row checked
    POST /api/admin/member-upload/import   the same file again: the ready policies added

Both are admin and owner only, like enrolling one member. Nothing is kept
between the two calls: the import checks the file again from scratch and adds
only the policies that pass, so what is added is always what the rules allow,
never what a browser says was checked. `?checksum=` must match the file the
staff member looked at, so a different file cannot slip in between.

The rules are in services/member_upload.py. Logs carry counts and policy
numbers, never a name or an ID number.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel

from ..auth import StaffUser, require_role, require_staff
from ..config import get_settings
from ..db import staff_connection
from ..errors import ApiError
from ..services import member_upload
from ..services.staff import log_staff_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/member-upload", tags=["admin"],
                   dependencies=[Depends(require_staff)])

CHECK_PATH = "/api/admin/member-upload/check"
IMPORT_PATH = "/api/admin/member-upload/import"


class ProblemOut(BaseModel):
    row: int
    column: str
    message: str


class LifeOut(BaseModel):
    row: int
    member_type: str | None
    name: str
    id_number_given: bool
    date_of_birth: date | None


class PolicyOut(BaseModel):
    policy_number: str
    # ready: will be added. fix: a row failed. exists: already in the book, skipped.
    state: str
    first_row: int
    last_row: int
    main_member: str | None
    lives: list[LifeOut]
    product: str | None
    entry_date: date | None
    premium_cents: int | None
    cover_cents: int | None
    currency: str = "ZAR"
    status: str
    problems: list[ProblemOut]


class CheckOut(BaseModel):
    checksum: str
    rows: int
    policies: list[PolicyOut]
    file_problems: list[ProblemOut]
    ignored_columns: list[str]
    ready: int
    to_fix: int
    already_in_book: int


class ImportOut(BaseModel):
    added: list[str]
    failed: dict[str, str]
    check: CheckOut


async def _read(request: Request) -> bytes:
    data = await request.body()
    limit = get_settings().max_banner_image_bytes
    if not data:
        raise ApiError(422, "validation_failed", "Choose the filled-in template to upload.")
    if len(data) > limit:
        raise ApiError(413, "request_too_large", "That file is too large. Upload at most "
                                                 "5,000 rows at a time.")
    return data


def _check(conn, data: bytes) -> member_upload.CheckResult:
    try:
        return member_upload.check(conn, data)
    except member_upload.UnreadableFile as exc:
        raise ApiError(422, "validation_failed", str(exc)) from None


def _out(result: member_upload.CheckResult) -> CheckOut:
    policies = []
    for p in result.policies:
        main = p.main_member
        policies.append(PolicyOut(
            policy_number=p.policy_number,
            state="exists" if p.exists else ("ready" if p.ok else "fix"),
            first_row=p.first_row,
            last_row=p.rows[-1] if p.rows else p.first_row,
            main_member=f"{main.first_names} {main.surname}".strip() if main else None,
            lives=[LifeOut(row=life.row, member_type=life.member_type,
                           name=f"{life.first_names} {life.surname}".strip(),
                           id_number_given=bool(life.id_number),
                           date_of_birth=life.date_of_birth) for life in p.lives],
            product=member_upload.PRODUCT_LABEL.get(p.plan_code or ""),
            entry_date=p.entry_date,
            premium_cents=p.premium_cents,
            cover_cents=p.cover_cents,
            status=p.status_code,
            problems=[ProblemOut(row=x.row, column=x.column, message=x.message)
                      for x in p.problems],
        ))
    return CheckOut(
        checksum=result.checksum,
        rows=result.rows,
        policies=policies,
        file_problems=[ProblemOut(row=x.row, column=x.column, message=x.message)
                       for x in result.file_problems],
        ignored_columns=result.ignored_columns,
        ready=sum(1 for p in policies if p.state == "ready"),
        to_fix=sum(1 for p in policies if p.state == "fix"),
        already_in_book=sum(1 for p in policies if p.state == "exists"),
    )


@router.post("/check", response_model=CheckOut)
async def check_upload(request: Request,
                       staff: StaffUser = Depends(require_role("admin"))) -> CheckOut:
    data = await _read(request)
    with staff_connection(staff.email) as conn:
        result = _check(conn, data)
        out = _out(result)
        log_staff_event(conn, staff.email, "member_upload_checked", None, {
            "rows": out.rows, "ready": out.ready, "to_fix": out.to_fix,
            "already_in_book": out.already_in_book})
    logger.info("Member upload checked: %s rows, %s ready, %s to fix",
                out.rows, out.ready, out.to_fix)
    return out


@router.post("/import", response_model=ImportOut)
async def import_upload(request: Request,
                        checksum: str = Query(pattern=r"^[0-9a-f]{64}$"),
                        staff: StaffUser = Depends(require_role("admin"))) -> ImportOut:
    data = await _read(request)
    with staff_connection(staff.email) as conn:
        result = _check(conn, data)
        if result.checksum != checksum:
            raise ApiError(status.HTTP_409_CONFLICT, "conflict",
                           "This is not the file you checked. Check it again before adding it.")
        added, failed = member_upload.import_all(conn, result, staff_email=staff.email)
        log_staff_event(conn, staff.email, "member_upload_imported", None, {
            "added": added, "failed": sorted(failed), "rows": result.rows})
        # The state after the import: what was added now reads "already in the book".
        after = _out(_check(conn, data))
    logger.info("Member upload imported: %s policies added, %s failed", len(added), len(failed))
    return ImportOut(added=added, failed=failed, check=after)
