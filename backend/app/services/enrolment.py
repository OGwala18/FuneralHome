"""Turning an enquiry, or a walk-in, into a person, a policy and its lives.

Everything one enrolment writes happens in the caller's single transaction:
the person, their phone and address, the policy, its main member, how it is
paid, the first year of instalments, and the link back to the enquiry. If any
of it fails, none of it exists. A half-enrolled family (a policy with no main
member, a person with no policy) is worse than a clear error, because staff
would trust it.

Uniqueness is enforced by the database, not by a check-then-insert here: the
partial unique indexes on people.id_number and policies.policy_number are what
actually refuse a duplicate, and this module only turns that refusal into a
sentence a person can act on.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg import errors as pg_errors

from ..db import log_event
from . import instalments
from .staff import log_staff_event

TENANT = "00000000-0000-0000-0000-000000000001"


class Conflict(Exception):
    """The request clashes with what is already recorded. Maps to 409."""


class NotFound(Exception):
    """The thing to act on does not exist. Maps to 404."""


# ---------------------------------------------------------------------------
# South African ID numbers
# ---------------------------------------------------------------------------

def decode_id(id_number: str, today: date | None = None) -> tuple[date | None, str]:
    """(date of birth, gender) from a checksum-valid 13-digit ID number.

    The century comes from today's date rather than a fixed split: a child born
    this year is added to policies as a dependant, and must not decode as born
    in the 1900s.
    """
    today = today or date.today()
    yy, mm, dd = int(id_number[0:2]), int(id_number[2:4]), int(id_number[4:6])
    year = 2000 + yy if 2000 + yy <= today.year else 1900 + yy
    try:
        born: date | None = date(year, mm, dd)
    except ValueError:
        born = None
    # Digits 7-10: 5000 and above is male. Same rule as the importer.
    gender = "male" if int(id_number[6:10]) >= 5000 else "female"
    return born, gender


def age_on(born: date | None, on: date) -> int | None:
    if born is None:
        return None
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def suggest_policy_number(conn: Any) -> str:
    """The number after the highest AA-series policy, keeping its zero padding.

    Archived policies count too, so a retired number is never handed out again.
    """
    row = conn.execute(
        r"""
        select policy_number from policies
         where policy_number ~ '^AA[0-9]+$'
         order by length(policy_number) desc, policy_number desc
         limit 1
        """
    ).fetchone()
    if row is None:
        return "AA0001"
    digits = row["policy_number"][2:]
    return "AA" + str(int(digits) + 1).zfill(len(digits))


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _identity(data: Any, today: date) -> dict:
    """Resolve ID status, date of birth and gender for one person."""
    if data.id_number:
        born_from_id, gender = decode_id(data.id_number, today)
        born = data.date_of_birth or born_from_id
        return {
            "id_number": data.id_number,
            "id_number_status": "valid",
            "date_of_birth": born,
            "date_of_birth_source": "supplied" if data.date_of_birth else (
                "derived_from_id" if born_from_id else None),
            "gender": gender,
        }
    return {
        "id_number": None,
        "id_number_status": "missing",
        "date_of_birth": data.date_of_birth,
        "date_of_birth_source": "supplied" if data.date_of_birth else None,
        "gender": data.gender or "unspecified",
    }


def _insert_person(conn: Any, data: Any, identity: dict, *, email: str | None,
                   language: str, source: str) -> str:
    return str(conn.execute(
        """
        insert into people (surname, first_names, initials, id_number, id_number_raw,
                            id_number_status, date_of_birth, date_of_birth_source,
                            gender, email, language_preference, source)
        values (%(surname)s, %(first_names)s, %(initials)s, %(id_number)s, %(id_number)s,
                %(id_number_status)s, %(date_of_birth)s, %(date_of_birth_source)s,
                %(gender)s, %(email)s, %(language)s, %(source)s)
        returning id
        """,
        {
            "surname": data.surname,
            "first_names": data.first_names,
            "initials": getattr(data, "initials", None),
            "email": email,
            "language": language,
            "source": source,
            **identity,
        },
    ).fetchone()["id"])


def _add_phone(conn: Any, person_id: str, number: str) -> None:
    """Record a mobile number. Primary only if the person has none yet."""
    conn.execute(
        """
        insert into person_phones (person_id, phone_type, number, number_raw,
                                   is_primary, is_whatsapp, source)
        select %(person)s, 'mobile', %(number)s, %(number)s,
               not exists (select 1 from person_phones
                            where person_id = %(person)s and is_primary
                              and archived_at is null),
               true, 'portal'
        on conflict (person_id, number) where archived_at is null do nothing
        """,
        {"person": person_id, "number": number},
    )


def _flag(conn: Any, *, person_id: str, issue: str, field: str, detail: str) -> None:
    conn.execute(
        """
        insert into data_quality_flags (person_id, issue_code, severity, field, detail, source)
        values (%s, %s, 'high', %s, %s, 'portal')
        on conflict do nothing
        """,
        (person_id, issue, field, detail),
    )


def _conflict_message(exc: pg_errors.UniqueViolation, data: Any) -> str:
    constraint = getattr(exc.diag, "constraint_name", "") or ""
    if constraint == "people_id_number_idx":
        return ("Someone with this ID number is already in the member book. "
                "Search Members for them instead of enrolling them again.")
    if constraint == "policies_number_idx":
        return f"Policy number {data.policy_number} is already in use. Choose another."
    if constraint == "policy_members_unique_idx":
        return "This person is already on this policy."
    if constraint == "policy_members_one_main_idx":
        return "This policy already has a main member."
    return "That clashes with a record that already exists."


def enrol(conn: Any, data: Any, *, staff_email: str, today: date | None = None) -> dict:
    """Create the person, policy, main member, payment arrangement and schedule."""
    today = today or date.today()
    entry_date = data.entry_date or today

    enquiry = None
    if data.enquiry_id:
        # Lock the enquiry so two staff members cannot enrol it at once.
        enquiry = conn.execute(
            """
            select id, person_id from plan_enquiries
             where id = %s and archived_at is null
             for update
            """,
            (data.enquiry_id,),
        ).fetchone()
        if enquiry is None:
            raise NotFound("That enquiry no longer exists.")
        if enquiry["person_id"] is not None:
            raise Conflict("This enquiry has already been enrolled as a member.")

    identity = _identity(data, today)

    try:
        person_id = _insert_person(conn, data, identity, email=data.email,
                                   language=data.language_preference, source="portal")
        if data.mobile:
            _add_phone(conn, person_id, data.mobile)

        if data.address_line1:
            conn.execute(
                """
                insert into addresses (person_id, address_type, line1, line2, suburb,
                                       city, province, postal_code, is_primary)
                values (%s, 'residential', %s, %s, %s, %s, %s, %s, true)
                """,
                (person_id, data.address_line1, data.address_line2, data.suburb,
                 data.city, data.province, data.postal_code),
            )

        policy_id = str(conn.execute(
            """
            insert into policies (policy_number, policy_number_raw, status_code, plan_code,
                                  branch_code, entry_date, premium_cents, cover_cents,
                                  enquiry_id, source)
            values (%s, %s, 'pending', %s, %s, %s, %s, %s, %s, 'portal')
            returning id
            """,
            (data.policy_number, data.policy_number, data.plan_code, data.branch_code,
             entry_date, data.premium_cents, data.cover_cents,
             data.enquiry_id if enquiry else None),
        ).fetchone()["id"])

        conn.execute(
            """
            insert into policy_members (policy_id, person_id, member_type, entry_age, joined_at)
            values (%s, %s, 'main_member', %s, %s)
            """,
            (policy_id, person_id, age_on(identity["date_of_birth"], entry_date), entry_date),
        )

        conn.execute(
            """
            insert into policy_payments (policy_id, method, debit_day, frequency)
            values (%s, %s, %s, %s)
            """,
            (policy_id, data.payment_method, data.debit_day, data.frequency),
        )
    except pg_errors.UniqueViolation as exc:
        raise Conflict(_conflict_message(exc, data)) from exc

    scheduled = instalments.generate(conn, policy_id, today=today)

    # The office's correction queue, for the gaps that matter on a main member.
    if not data.id_number:
        _flag(conn, person_id=person_id, issue="id_number_missing", field="id_number",
              detail="No ID number was captured when this member was enrolled.")
    if not data.mobile:
        _flag(conn, person_id=person_id, issue="phone_number_missing", field="mobile",
              detail="No phone number was captured when this member was enrolled.")

    if enquiry is not None:
        conn.execute(
            """
            update plan_enquiries
               set person_id = %s, status = 'awaiting_payment'
             where id = %s
            """,
            (person_id, enquiry["id"]),
        )
        log_event(conn, str(enquiry["id"]), "converted_to_policy",
                  {"policy_number": data.policy_number}, actor=staff_email)

    # The policy number identifies the record without carrying personal data.
    log_staff_event(conn, staff_email, "member_enrolled", person_id,
                    {"policy_number": data.policy_number, "from_enquiry": enquiry is not None})

    return {
        "person_id": person_id,
        "policy_id": policy_id,
        "policy_number": data.policy_number,
        "instalments_scheduled": scheduled,
    }


def add_dependant(conn: Any, policy_id: str, data: Any, *, staff_email: str,
                  today: date | None = None) -> dict:
    """Put one more life on a policy.

    Someone already in the book (matched by ID number) is linked rather than
    created again: the same human on their own policy and on their mother's is
    exactly what policy_members exists for.
    """
    today = today or date.today()
    policy = conn.execute(
        "select id, policy_number from policies where id = %s and archived_at is null",
        (policy_id,),
    ).fetchone()
    if policy is None:
        raise NotFound("That policy no longer exists.")

    identity = _identity(data, today)

    existing = None
    if data.id_number:
        existing = conn.execute(
            "select id, date_of_birth from people where id_number = %s and archived_at is null",
            (data.id_number,),
        ).fetchone()

    try:
        if existing is not None:
            person_id = str(existing["id"])
            born = existing["date_of_birth"] or identity["date_of_birth"]
        else:
            person_id = _insert_person(conn, data, identity, email=None,
                                       language=data.language_preference, source="portal")
            born = identity["date_of_birth"]

        if data.mobile:
            _add_phone(conn, person_id, data.mobile)

        member_id = str(conn.execute(
            """
            insert into policy_members (policy_id, person_id, member_type, entry_age, joined_at)
            values (%s, %s, %s, %s, %s)
            returning id
            """,
            (policy_id, person_id, data.member_type, age_on(born, today), today),
        ).fetchone()["id"])
    except pg_errors.UniqueViolation as exc:
        raise Conflict(_conflict_message(exc, data)) from exc

    log_staff_event(conn, staff_email, "dependant_added", person_id,
                    {"policy_number": policy["policy_number"], "member_type": data.member_type,
                     "existing_person": existing is not None})

    return {
        "person_id": person_id,
        "policy_member_id": member_id,
        "existing_person": existing is not None,
    }
