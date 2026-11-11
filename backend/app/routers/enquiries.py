"""The two-stage capture endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from psycopg import errors as pg_errors

from ..db import connection, log_event
from ..idempotency import fingerprint, idempotency_key, mark_replayed, refuse_mismatch
from ..ratelimit import application_limiter, enforce, lead_limiter
from ..schemas import ApplicationIn, EnquiryOut, LeadIn
from ..services.email import send_completed_application, send_new_lead
from ..services.whatsapp import _plain_body, send_registration_confirmation
from ..services.whatsapp_line import record_confirmation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/enquiries", tags=["enquiries"])

# The whole row: the API response uses a narrow subset (EnquiryOut), but the
# admin notification email needs every captured field.
_RETURNING = "*"


def _to_out(row: dict) -> EnquiryOut:
    return EnquiryOut(
        id=str(row["id"]),
        reference=row["reference"],
        first_name=row["first_name"],
        surname=row["surname"],
        mobile_number=row["mobile_number"],
        plan_interest=row["plan_interest"],
    )


@router.post("", response_model=EnquiryOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadIn, background: BackgroundTasks, request: Request, response: Response
) -> EnquiryOut:
    """Stage 1. Commits the lead immediately, then emails the office.

    This is the point of the two-step split: the moment somebody gives us a name
    and a number, that lead is ours, whether or not they ever reach stage 2.
    The notification goes out on THIS step for the same reason — the office
    should be able to phone someone who abandoned the second page.
    """
    key = idempotency_key(request)
    data = payload.model_dump()
    data_fingerprint = fingerprint(data)

    # A retry of a submission we already hold is answered before the rate limit,
    # so a family's second tap never counts against them.
    if key is not None:
        existing = _find_by_key(key)
        if existing is not None:
            return _replay_lead(existing, data_fingerprint, response)

    enforce(lead_limiter, request)

    data["idempotency_key"] = key
    data["idempotency_fingerprint"] = data_fingerprint if key is not None else None

    with connection() as conn:
        row = conn.execute(
            f"""
            insert into plan_enquiries (
                first_name, surname, mobile_number, email, city, suburb_or_town,
                province, language_preference, plan_interest, best_contact_time,
                how_heard, contact_consent, marketing_consent, consented_at, source,
                idempotency_key, idempotency_fingerprint
            ) values (
                %(first_name)s, %(surname)s, %(mobile_number)s, %(email)s, %(city)s,
                %(suburb_or_town)s, %(province)s, %(language_preference)s,
                %(plan_interest)s, %(best_contact_time)s, %(how_heard)s,
                %(contact_consent)s, %(marketing_consent)s, now(), 'website',
                %(idempotency_key)s, %(idempotency_fingerprint)s
            )
            on conflict (idempotency_key) where idempotency_key is not null do nothing
            returning {_RETURNING}
            """,
            data,
        ).fetchone()

        if row is None:
            # Two tries with the same key arrived together and the other one
            # won. Answer with its enquiry; it is the one that notifies.
            existing = conn.execute(
                f"select {_RETURNING} from plan_enquiries where idempotency_key = %s", (key,)
            ).fetchone()
            return _replay_lead(existing, data_fingerprint, response)

        log_event(
            conn,
            row["id"],
            "lead_captured",
            {
                "plan_interest": payload.plan_interest,
                "language": payload.language_preference,
                "how_heard": payload.how_heard,
                "marketing_consent": payload.marketing_consent,
            },
        )

    # After commit, never before: the office must only be told about a record
    # that actually exists.
    background.add_task(_notify_new_lead, dict(row))

    logger.info("Lead captured: %s", row["reference"])
    return _to_out(row)


def _find_by_key(key: str) -> dict | None:
    with connection() as conn:
        return conn.execute(
            f"select {_RETURNING} from plan_enquiries where idempotency_key = %s", (key,)
        ).fetchone()


def _replay_lead(row: dict, data_fingerprint: str, response: Response) -> EnquiryOut:
    """The answer to a repeated stage-1 request: the original, and nothing sent."""
    if row["idempotency_fingerprint"] != data_fingerprint:
        raise refuse_mismatch()
    mark_replayed(response)
    logger.info("Lead replayed: %s", row["reference"])
    return _to_out(row)


def _notify_new_lead(row: dict) -> None:
    """Email the office about a stage-1 enquiry, and record the outcome."""
    result = send_new_lead(row)
    _record_email_outcome(row["id"], "lead_email", result)


def _record_email_outcome(enquiry_id: str, kind: str, result) -> None:
    try:
        with connection() as conn:
            log_event(
                conn,
                str(enquiry_id),
                "%s_sent" % kind if result.sent else "%s_failed" % kind,
                {"error": result.error},
                actor="system",
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not record %s outcome", kind)


@router.patch("/{enquiry_id}/application", response_model=EnquiryOut)
def submit_application(
    enquiry_id: str,
    payload: ApplicationIn,
    background: BackgroundTasks,
    request: Request,
    response: Response,
) -> EnquiryOut:
    """Stage 2. Promotes an existing lead to a full application.

    Sending the identical application again changes nothing and notifies no
    one; a real correction (any field different) updates as before.
    """
    enforce(application_limiter, request)

    try:
        uuid.UUID(enquiry_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="We could not find your registration. Please start again.",
        ) from exc

    data = payload.model_dump()
    data["application_fingerprint"] = fingerprint(data)
    data["enquiry_id"] = enquiry_id
    # The same plan code again, as plain text, to look up its price.
    data["plan_for_price"] = payload.plan_selected

    with connection() as conn:
        unchanged = conn.execute(
            f"""
            select {_RETURNING} from plan_enquiries
             where id = %(enquiry_id)s
               and archived_at is null
               and application_fingerprint = %(application_fingerprint)s
            """,
            data,
        ).fetchone()
        if unchanged is not None:
            mark_replayed(response)
            logger.info("Application replayed: %s", unchanged["reference"])
            return _to_out(unchanged)

        try:
            row = conn.execute(
                f"""
                update plan_enquiries set
                    id_number                = %(id_number)s,
                    date_of_birth            = %(date_of_birth)s,
                    marital_status           = %(marital_status)s,
                    address_line1            = %(address_line1)s,
                    address_line2            = %(address_line2)s,
                    postal_code              = %(postal_code)s,
                    cover_area               = %(cover_area)s,
                    plan_selected            = %(plan_selected)s,
                    coffin_choice            = %(coffin_choice)s,
                    age_band                 = %(age_band)s,
                    -- Set by the plan, never by the browser: the price of a
                    -- plan with exactly one price (A, B, Dome). Plan C depends
                    -- on single or couple and age, which staff confirm at
                    -- enrolment, so it stays empty here.
                    premium_amount_cents     = (
                        select min(premium_cents) from ref_plan_prices
                         where plan_code = %(plan_for_price)s and is_active
                        having count(*) = 1
                    ),
                    payment_frequency        = %(payment_frequency)s,
                    payment_preference       = %(payment_preference)s,
                    number_of_dependants     = %(number_of_dependants)s,
                    next_of_kin_name         = %(next_of_kin_name)s,
                    next_of_kin_mobile       = %(next_of_kin_mobile)s,
                    next_of_kin_relationship = %(next_of_kin_relationship)s,
                    beneficiary_name         = %(beneficiary_name)s,
                    beneficiary_mobile       = %(beneficiary_mobile)s,
                    beneficiary_relationship = %(beneficiary_relationship)s,
                    notes                    = %(notes)s,
                    terms_accepted           = %(terms_accepted)s,
                    application_fingerprint  = %(application_fingerprint)s,
                    stage                    = 'application',
                    status                   = 'application_submitted',
                    application_submitted_at = now()
                where id = %(enquiry_id)s
                  and archived_at is null
                returning {_RETURNING}
                """,
                data,
            ).fetchone()
        except pg_errors.UniqueViolation as exc:
            # The partial unique index on id_number caught a second application
            # for a person we already hold.
            logger.info("Duplicate ID number on %s", enquiry_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "We already have an application with this ID number. "
                    "Please phone us and we will find your record."
                ),
            ) from exc
        except pg_errors.InvalidTextRepresentation as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="We could not find your registration. Please start again.",
            ) from exc

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="We could not find your registration. Please start again.",
            )

        log_event(
            conn,
            row["id"],
            "application_submitted",
            {
                "plan_selected": payload.plan_selected,
                "cover_area": payload.cover_area,
                "coffin_choice": payload.coffin_choice,
                "payment_preference": payload.payment_preference,
            },
        )

    # After commit, never before: a confirmation must only go out for a record
    # that actually exists.
    background.add_task(
        _send_confirmation, str(row["id"]), row["mobile_number"], row["first_name"], row["reference"]
    )
    background.add_task(_notify_completed_application, dict(row))

    logger.info("Application submitted: %s", row["reference"])
    return _to_out(row)


def _notify_completed_application(row: dict) -> None:
    """Email the office the full application. Separate from the stage-1 mail so
    the office sees both the early lead and the finished form."""
    result = send_completed_application(row)
    _record_email_outcome(row["id"], "application_email", result)


def _send_confirmation(enquiry_id: str, mobile: str, first_name: str, reference: str) -> None:
    result = send_registration_confirmation(
        to_mobile=mobile, first_name=first_name, reference=reference
    )
    try:
        with connection() as conn:
            if result.sent:
                conn.execute(
                    """
                    update plan_enquiries
                       set whatsapp_sent_at = now(), whatsapp_message_sid = %s
                     where id = %s
                    """,
                    (result.message_sid, enquiry_id),
                )
            log_event(
                conn,
                enquiry_id,
                "whatsapp_sent" if result.sent else "whatsapp_failed",
                {"message_sid": result.message_sid, "error": result.error},
                actor="system",
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not record WhatsApp outcome for %s", reference)
    # Also in the line's own record, so the conversation shows it if the
    # family replies. Separate, so a problem here can't undo the record above.
    try:
        with connection() as conn:
            record_confirmation(conn, enquiry_id=enquiry_id, to_number=mobile,
                                body=_plain_body(first_name, reference), result=result)
    except Exception:  # noqa: BLE001
        logger.exception("Could not store the WhatsApp confirmation for %s", reference)
