"""The staff second step: /api/admin/2fa.

These routes use require_staff_identity (password only), because they are how
a signed-in person who has NOT yet passed the second step gets past it. Every
other /api/admin route uses the strict require_staff; the guard test in
tests/test_two_step_gate.py proves it, and lists the routes allowed here.

Bit 4 adds only /status. The emailed code, trusted computers, the app and
passkeys arrive in Bits 5 onward (docs/feature-2-staff-two-factor.md §12).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..auth import DEVICE_HEADER, StaffUser, require_staff_identity
from ..config import get_settings
from ..db import connection
from ..services import two_step
from ..services.two_step_crypto import mask_email

router = APIRouter(prefix="/api/admin/2fa", tags=["admin", "two-step"])


class MethodsOut(BaseModel):
    email_code: bool
    authenticator_app: bool
    passkeys: int


class StatusOut(BaseModel):
    # False only while TWO_STEP_ENFORCEMENT is off; the portal then skips the
    # "Confirm it's you" screen entirely.
    enforced: bool
    session_verified: bool
    verified_by: str | None
    verified_until: datetime | None
    trusted_device: bool
    methods: MethodsOut
    # Where an emailed code would go, masked: t•••@induduzo.co.za
    email_hint: str


@router.get("/status", response_model=StatusOut)
def status_(request: Request, staff: StaffUser = Depends(require_staff_identity)) -> StatusOut:
    """What this person has set up, and whether this session has passed."""
    at = two_step.now()
    with connection() as conn:
        passed = (
            two_step.find_verification(conn, staff.staff_id, staff.session_id, at)
            if staff.session_id
            else None
        )
        device = two_step.find_trusted_device(
            conn, staff.staff_id, request.headers.get(DEVICE_HEADER), at
        )
        methods = two_step.methods_set_up(conn, staff.staff_id)

    return StatusOut(
        enforced=get_settings().two_step_enforced,
        session_verified=passed is not None or device is not None,
        verified_by=passed["method"] if passed else (two_step.TRUSTED_DEVICE if device else None),
        verified_until=passed["expires_at"] if passed else None,
        trusted_device=device is not None,
        methods=MethodsOut(**methods),
        email_hint=mask_email(staff.email),
    )
