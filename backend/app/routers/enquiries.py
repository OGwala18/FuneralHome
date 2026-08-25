"""The two-stage capture endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from psycopg import errors as pg_errors

from ..db import connection, log_event
from ..schemas import ApplicationIn, EnquiryOut, LeadIn
from ..services.whatsapp import send_registration_confirmation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/enquiries", tags=["enquiries"])

_RETURNING = "id, reference, first_name, surname, mobile_number, plan_interest"


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
def create_lead(payload: LeadIn) -> EnquiryOut:
    """Stage 1. Commits the lead immediately.

    This is the point of the two-step split: the moment somebody gives us a name
    and a number, that lead is ours, whether or not they ever reach stage 2.
    """
    with connection() as conn:
        row = conn.execute(
            f"""
            insert into plan_enquiries (
                first_name, surname, mobile_number, email, city, suburb_or_town,
                province, language_preference, plan_interest, best_contact_time,
                how_heard, contact_consent, marketing_consent, consented_at, source
            ) values (
                %(first_name)s, %(surname)s, %(mobile_number)s, %(email)s, %(city)s,
                %(suburb_or_town)s, %(province)s, %(language_preference)s,
                %(plan_interest)s, %(best_contact_time)s, %(how_heard)s,
                %(contact_consent)s, %(marketing_consent)s, now(), 'website'
            )
            returning {_RETURNING}
            """,
            payload.model_dump(),
        ).fetchone()

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

    logger.info("Lead captured: %s", row["reference"])
    return _to_out(row)


@router.patch("/{enquiry_id}/application", response_model=EnquiryOut)
def submit_application(
    enquiry_id: str, payload: ApplicationIn, background: BackgroundTasks
) -> EnquiryOut:
    """Stage 2. Promotes an existing lead to a full application."""
    data = payload.model_dump()
    data["enquiry_id"] = enquiry_id

    with connection() as conn:
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
                    premium_amount_cents     = %(premium_amount_cents)s,
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

    logger.info("Application submitted: %s", row["reference"])
    return _to_out(row)


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
