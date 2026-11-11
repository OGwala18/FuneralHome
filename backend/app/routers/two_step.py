"""The staff second step: /api/admin/2fa.

These routes use require_staff_identity (password only), because they are how
a signed-in person who has NOT yet passed the second step gets past it. Every
other /api/admin route uses the strict require_staff; the guard test in
tests/test_two_step_gate.py proves it, and lists the routes allowed here.

Bit 4 added /status; Bit 5 the emailed code. Trusted computers, the app and
passkeys arrive in Bits 6 onward (docs/feature-2-staff-two-factor.md §12).

Failures are committed BEFORE the error is raised: a raised error rolls the
transaction back, and a wrong guess that left no trace could be repeated
forever. So each handler decides inside the transaction and raises after it.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict

from ..auth import DEVICE_HEADER, StaffGateError, StaffUser, require_staff_identity
from ..config import get_settings
from ..db import connection
from ..services import two_step
from ..services.email import send_sign_in_code
from ..services.two_step_crypto import code_matches, hash_code, mask_email, new_code

logger = logging.getLogger(__name__)

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


# --- Emailed code --------------------------------------------------------------------

class EmailSendOut(BaseModel):
    challenge_id: str
    expires_at: datetime
    # When "Send a new code" may be pressed again.
    resend_after: datetime
    email_hint: str


class EmailVerifyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    challenge_id: str
    code: str
    # "Trust this computer for 30 days". Accepted now; Bit 6 acts on it.
    trust_device: bool = False


class VerifiedOut(BaseModel):
    verified: bool
    verified_by: str
    verified_until: datetime


_SIX_DIGITS = re.compile(r"^\d{6}$")
_CODE_MESSAGES = {
    "code_wrong": "That code isn't right. Check the email and try again.",
    "code_expired": "That code has expired. Ask for a new one.",
    "code_used_up": "That code can't be used any more. Ask for a new one.",
}


def _needs_session(staff: StaffUser) -> str:
    if staff.session_id is None:
        raise StaffGateError(
            status.HTTP_401_UNAUTHORIZED, "session_missing",
            "Your sign-in has no session. Please sign in again.",
        )
    return staff.session_id


def _locked(seconds: int) -> StaffGateError:
    return StaffGateError(
        status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts",
        "Too many wrong attempts. Try again in 15 minutes, or ask the owner.",
        headers={"Retry-After": str(seconds)},
    )


def _as_uuid(value: str) -> str | None:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


@router.post("/email/send", response_model=EmailSendOut)
def email_send(staff: StaffUser = Depends(require_staff_identity)) -> EmailSendOut:
    """Make a code, replace any older one, and email it to the staff record's address.

    Nothing ever sends a code except this, when the person presses the button:
    an expired code is never followed by an automatic new one.
    """
    session_id = _needs_session(staff)
    pepper = get_settings().two_step_code_pepper
    at = two_step.now()
    code = new_code()

    with connection() as conn:
        locked = two_step.locked_for(conn, staff.email, at)
        wait = 0 if locked else two_step.resend_wait(conn, staff.staff_id, at)
        if not locked and not wait:
            challenge_id, expires_at = two_step.issue_email_code(
                conn, staff.staff_id, session_id,
                lambda cid: hash_code(pepper, cid, code), at,
            )
            two_step.log_event(conn, staff.email, "2fa_code_sent", staff.email, at,
                               {"method": "email_code"})

    if locked:
        raise _locked(locked)
    if wait:
        raise StaffGateError(
            status.HTTP_429_TOO_MANY_REQUESTS, "resend_too_soon",
            "A code was sent a moment ago. Please wait before asking for another.",
            headers={"Retry-After": str(wait)},
        )

    # The code is committed first, so what the email says is what we hold. Sent
    # inside the request: the person is waiting and must hear if it failed.
    result = send_sign_in_code(staff.email, code, expires_at)
    if not result.sent:
        logger.warning("Sign-in code email was not sent")
        raise StaffGateError(
            status.HTTP_502_BAD_GATEWAY, "email_send_failed",
            "We couldn't email your code just now. Try again shortly, or use another method.",
        )

    return EmailSendOut(
        challenge_id=challenge_id,
        expires_at=expires_at,
        resend_after=at + two_step.RESEND_GAP,
        email_hint=mask_email(staff.email),
    )


@router.post("/email/verify", response_model=VerifiedOut)
def email_verify(
    body: EmailVerifyIn, staff: StaffUser = Depends(require_staff_identity)
) -> VerifiedOut:
    """Check an emailed code. Right code, in time, same session: this session passes."""
    session_id = _needs_session(staff)
    pepper = get_settings().two_step_code_pepper
    at = two_step.now()
    typed = re.sub(r"[\s-]", "", body.code)
    challenge_id = _as_uuid(body.challenge_id)

    passed = None
    with connection() as conn:
        locked = two_step.locked_for(conn, staff.email, at)
        if locked:
            outcome = "locked"
        else:
            # Only this person's code, asked for in THIS session, can be the one.
            challenge = challenge_id and conn.execute(
                """
                select id, session_id, code_hash, attempts, expires_at, used_at, replaced_at
                  from staff_mfa_challenges
                 where id = %s and staff_user_id = %s and kind = 'email_code'
                 for update
                """,
                (challenge_id, staff.staff_id),
            ).fetchone()

            if not challenge or str(challenge["session_id"]) != session_id:
                outcome = "code_wrong"
            else:
                outcome = two_step.why_dead(challenge, at) or "check"

            if outcome == "check":
                right = bool(_SIX_DIGITS.match(typed)) and code_matches(
                    pepper, challenge["id"], typed, bytes(challenge["code_hash"])
                )
                if right:
                    conn.execute(
                        "update staff_mfa_challenges set used_at = %s where id = %s",
                        (at, challenge["id"]),
                    )
                    passed = two_step.record_verification(
                        conn, staff.staff_id, session_id, "email_code", at
                    )
                    two_step.log_event(conn, staff.email, "2fa_passed", staff.email,
                                       at, {"method": "email_code"})
                    outcome = "passed"
                else:
                    conn.execute(
                        "update staff_mfa_challenges set attempts = attempts + 1 where id = %s",
                        (challenge["id"],),
                    )
                    outcome = "code_wrong"

            if outcome != "passed" and two_step.record_failure(
                conn, staff.email, "email_code", outcome, at
            ):
                locked = two_step.locked_for(conn, staff.email, at)
                logger.warning("Staff second step locked after repeated failures")

    if outcome == "passed":
        return VerifiedOut(verified=True, verified_by="email_code",
                           verified_until=passed["expires_at"])
    if locked:
        raise _locked(locked)
    raise StaffGateError(status.HTTP_400_BAD_REQUEST, outcome, _CODE_MESSAGES[outcome])
