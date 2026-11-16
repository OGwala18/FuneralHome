"""A forgotten staff password: /api/auth/password.

Two public routes, because someone who has forgotten their password has no
token to send:

  POST /forgot  {email}
      Emails a temporary password to that address IF it belongs to an active
      member of staff. The answer is the same 202 whether it does or not, so
      the form cannot be used to find out who works here. The email goes out
      after the response, in the background, for the same reason.

  POST /reset   {email, temporary_password, new_password}
      The temporary password works as the "old password": right, live and
      unused, it lets the new password be set in Supabase, once. The portal then
      signs the person in with the new password, and the second step follows as
      on any sign-in.

Not under /api/admin: those routes all need a signed-in staff token and the
second step (tests/test_two_step_gate.py), and these exist for people who
cannot sign in. Their protection is the temporary password itself (59 bits,
30 minutes, five tries), the per-person send limits in the database, and the
per-connection limits in ratelimit.py.

As in routers/two_step.py, failures are committed BEFORE the error is raised:
a raised error rolls the transaction back, and a wrong guess that left no trace
could be repeated forever. So the handler decides inside the transaction and
raises after it.

Never logged: the address, the temporary password, the new password.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..db import connection
from ..errors import ApiError
from ..ratelimit import enforce, password_forgot_limiter, password_reset_limiter
from ..services import password_reset as resets
from ..services import supabase_admin, two_step
from ..services.email import send_temporary_password
from ..services.two_step_crypto import code_matches, hash_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/password", tags=["auth", "password-reset"])

FORGOT_ANSWER = (
    "If that address belongs to a member of staff, a temporary password is on its "
    "way. It works once, for 30 minutes. Check your spam folder if it hasn't "
    "arrived in a few minutes."
)
_TOO_MANY = "Too many tries from this connection. Wait a while, or ask the owner to reset it."


class ForgotIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: str = Field(min_length=3, max_length=254)


class ForgotOut(BaseModel):
    detail: str


class ResetIn(BaseModel):
    # Not stripped: a password may begin or end with a space on purpose.
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    temporary_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=1, max_length=200)


class ResetOut(BaseModel):
    reset: bool


def _not_configured() -> ApiError:
    logger.error("Password reset is not configured: %s",
                 ", ".join(get_settings().password_reset_missing))
    return ApiError(
        status.HTTP_503_SERVICE_UNAVAILABLE, "password_reset_not_configured",
        "Resetting a password isn't switched on here yet. Ask the owner to reset it for you.",
    )


def _reset_url() -> str | None:
    portal = get_settings().portal_url
    return f"{portal}/reset-password" if portal else None


def _email_it(staff_id: str, address: str, temporary: str, expires_at: datetime) -> None:
    """After the response: send, and record a failure where the owner can see it."""
    try:
        result = send_temporary_password(address, temporary, expires_at, _reset_url())
        if not result.sent:
            with connection() as conn:
                two_step.log_event(conn, address, "password_reset_email_failed", address,
                                   two_step.now(), {"error": result.error})
            logger.warning("Temporary password email for staff %s was not sent: %s",
                           staff_id, result.error)
    except Exception as exc:  # noqa: BLE001 - nothing is waiting on this any more
        logger.warning("Temporary password email for staff %s failed: %s",
                       staff_id, type(exc).__name__)


@router.post("/forgot", status_code=status.HTTP_202_ACCEPTED, response_model=ForgotOut)
def forgot(body: ForgotIn, request: Request, background: BackgroundTasks) -> ForgotOut:
    """Email a temporary password, if the address is active staff. Always 202."""
    enforce(password_forgot_limiter, request, _TOO_MANY)
    settings = get_settings()
    if not settings.password_reset_configured:
        raise _not_configured()

    at = resets.now()
    temporary = resets.new_temporary_password()
    send: tuple[str, str, datetime] | None = None

    with connection() as conn:
        staff = resets.find_staff(conn, body.email)
        if staff is None:
            logger.info("Password reset asked for an address that is not active staff")
        elif resets.send_wait(conn, str(staff["id"]), at):
            # Quietly: saying "wait" would say the address is real.
            logger.info("Password reset for staff %s held back by the send limit", staff["id"])
        else:
            _, expires_at = resets.issue(conn, str(staff["id"]), temporary,
                                         settings.two_step_code_pepper, at)
            two_step.log_event(conn, staff["email"], "password_reset_sent", staff["email"], at)
            send = (str(staff["id"]), staff["email"], expires_at)

    # Committed first, so what the email says is what we hold.
    if send is not None:
        staff_id, address, expires_at = send
        background.add_task(_email_it, staff_id, address, temporary, expires_at)

    return ForgotOut(detail=FORGOT_ANSWER)


def _check_new_password(new: str, temporary: str) -> str | None:
    """Our own floor, before Supabase applies the project's rules."""
    if len(new) < resets.MIN_PASSWORD:
        return f"Use at least {resets.MIN_PASSWORD} characters; a short sentence is easiest."
    if len(new.encode("utf-8")) > resets.MAX_PASSWORD_BYTES:
        return f"Use at most {resets.MAX_PASSWORD_BYTES} characters."
    if resets.normalise(new) == resets.normalise(temporary):
        return "Choose your own new password, not the temporary one."
    return None


@router.post("/reset", response_model=ResetOut)
def reset(body: ResetIn, request: Request) -> ResetOut:
    """Set a new password with the emailed temporary one as the old password."""
    enforce(password_reset_limiter, request, _TOO_MANY)
    settings = get_settings()
    if not settings.password_reset_configured:
        raise _not_configured()

    problem = _check_new_password(body.new_password, body.temporary_password)
    if problem:
        raise ApiError(422, "password_rejected", problem)

    pepper = settings.two_step_code_pepper
    typed = resets.normalise(body.temporary_password)
    at = resets.now()
    outcome = "invalid"
    refused: str | None = None

    with connection() as conn:
        staff = resets.find_staff(conn, body.email.strip())
        row = resets.live(conn, str(staff["id"]), at) if staff else None

        if row is None:
            # The same work as a real check, so the time taken says nothing.
            hash_code(pepper, uuid.uuid4(), typed)
            if staff is not None:
                two_step.log_event(conn, staff["email"], "password_reset_failed",
                                   staff["email"], at, {"reason": "none_live"})
        elif not code_matches(pepper, row["id"], typed, bytes(row["temp_hash"])):
            resets.count_wrong(conn, row["id"])
            two_step.log_event(conn, staff["email"], "password_reset_failed",
                               staff["email"], at, {"reason": "wrong"})
        else:
            stored = str(staff["supabase_user_id"]) if staff["supabase_user_id"] else None
            user_id = stored or supabase_admin.find_user_id(staff["email"])
            result = (supabase_admin.set_password(user_id, body.new_password)
                      if user_id else None)
            if result is not None and result.no_account and stored:
                # The stored id is stale (the account was made again by hand).
                user_id = supabase_admin.find_user_id(staff["email"])
                result = (supabase_admin.set_password(user_id, body.new_password)
                          if user_id else None)

            if result is None or result.no_account:
                outcome = "no_account"
            elif result.saved:
                resets.mark_used(conn, row["id"], at)
                two_step.log_event(conn, staff["email"], "password_reset_done",
                                   staff["email"], at)
                outcome = "done"
            elif result.rejected:
                # The temporary password stays alive: the person tries another.
                outcome = "rejected"
                refused = result.detail
            else:
                outcome = "upstream"

    if outcome == "done":
        logger.info("Password reset completed for staff %s", staff["id"])
        return ResetOut(reset=True)
    if outcome == "rejected":
        raise ApiError(
            422, "password_rejected",
            refused or "That password isn't allowed. Try a longer one.",
        )
    if outcome == "no_account":
        logger.warning("Password reset for staff %s: no Supabase sign-in found", staff["id"])
        raise ApiError(
            status.HTTP_409_CONFLICT, "sign_in_missing",
            "Your staff account has no sign-in yet. Ask the owner to create it.",
        )
    if outcome == "upstream":
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY, "upstream_failed",
            "We couldn't reach the sign-in service. Your temporary password still "
            "works; try again in a minute.",
            headers={"Retry-After": "30"},
        )
    raise ApiError(
        status.HTTP_400_BAD_REQUEST, "temporary_password_invalid",
        "That temporary password isn't right, or it has expired or been used. "
        "Check the email, or ask for a new one.",
    )
