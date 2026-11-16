"""Correcting a member after enrolment, and moving a policy to another plan.

Staff fix their own capture mistakes (an ID number, a surname, a mobile, an
address, the compliance answers, how the family pays) and change a family's
plan without enrolling them again: the person, the policy number, the lives
and the payment history all stay where they are.

What is NOT editable here, on purpose: the policy number, the person's and the
policy's ids, the start date, and the premium and cover, which only ever come
from the price list. A plan, option or frequency change goes through
change_plan(), which re-prices and replaces the unpaid premiums from today.

Every value overwritten here is kept by the history triggers (migration 0031),
under the staff member's email that the route sets on the transaction.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg import errors as pg_errors

from ..schemas import valid_sa_id
from . import enrolment, instalments
from .enrolment import Conflict, Invalid, NotFound
from .staff import log_staff_event

_LIVE_STATUSES = ("pending", "active")

# Columns of the history that say nothing a person needs to read.
_HISTORY_NOISE = {"id", "tenant_id", "created_at", "updated_at", "person_id", "policy_id",
                  "id_number_raw", "number_raw", "policy_number_raw"}

# Data-quality flags an edit can settle, by what it fixes.
_ID_FLAGS = ["id_number_missing", "id_number_malformed", "id_checksum_failed",
             "id_date_impossible", "dob_id_mismatch"]
_PHONE_FLAGS = ["phone_number_missing"]


def _main_member(conn: Any, policy_id: str, *, lock: bool = False) -> dict | None:
    return conn.execute(
        f"""
        select p.id as policy_id, p.policy_number, p.status_code, p.plan_code, p.plan_option,
               p.entry_date, p.premium_cents, p.cover_cents, pm.person_id,
               pe.date_of_birth, pe.id_number, pe.id_number_status::text as id_number_status,
               pe.gender::text as gender, pe.date_of_birth_source
          from policies p
          join policy_members pm on pm.policy_id = p.id and pm.member_type = 'main_member'
                                and pm.archived_at is null
          join people pe on pe.id = pm.person_id
         where p.id = %s and p.archived_at is null
        {"for update of p, pe" if lock else ""}
        """,
        (policy_id,),
    ).fetchone()


def _active_payment(conn: Any, policy_id: str) -> dict | None:
    return conn.execute(
        """
        select id, method, debit_day, frequency::text as frequency, pay_branch_code
          from policy_payments
         where policy_id = %s and is_active and archived_at is null
         for update
        """,
        (policy_id,),
    ).fetchone()


def load(conn: Any, policy_id: str) -> dict | None:
    """The policy's main member, as the edit form starts from them."""
    return conn.execute(
        """
        select p.id as policy_id, p.policy_number, p.status_code, s.label as status_label,
               p.plan_code, p.plan_option, p.entry_date, p.premium_cents, p.cover_cents,
               p.currency, p.notes,
               pe.id as person_id, pe.surname, pe.first_names, pe.initials, pe.id_number,
               pe.id_number_status::text as id_number_status, pe.date_of_birth,
               pe.gender::text as gender, pe.language_preference::text as language_preference,
               pe.email, pe.country_of_birth, pe.citizenship, pe.passport_number,
               pe.employment_status, pe.employer_name, pe.industry, pe.occupation,
               pe.job_role, pe.source_of_funds, pe.source_of_funds_other, pe.salary_day,
               (select ph.number from person_phones ph
                 where ph.person_id = pe.id and ph.archived_at is null
                 order by ph.is_primary desc, ph.created_at desc limit 1) as mobile,
               a.line1 as address_line1, a.line2 as address_line2, a.suburb, a.city,
               a.province, a.postal_code,
               pay.method as payment_method, pay.debit_day, pay.frequency::text as frequency,
               pay.pay_branch_code
          from policies p
          join ref_policy_statuses s on s.code = p.status_code
          join policy_members pm on pm.policy_id = p.id and pm.member_type = 'main_member'
                                and pm.archived_at is null
          join people pe on pe.id = pm.person_id
          left join addresses a on a.person_id = pe.id and a.address_type = 'residential'
                               and a.is_primary and a.archived_at is null
          left join policy_payments pay on pay.policy_id = p.id and pay.is_active
                                       and pay.archived_at is null
         where p.id = %s and p.archived_at is null
        """,
        (policy_id,),
    ).fetchone()


def _identity(data: Any, stored: dict, today: date) -> dict:
    """ID status, date of birth and gender after the edit.

    An ID number left as it was keeps whatever status it had, so an imported
    member whose number fails its checksum can still have their address fixed.
    A CHANGED ID number must be a valid one.
    """
    if data.id_number and data.id_number == stored["id_number"] \
            and stored["id_number_status"] != "valid":
        return {
            "id_number": stored["id_number"],
            "id_number_status": stored["id_number_status"],
            "date_of_birth": data.date_of_birth or stored["date_of_birth"],
            "date_of_birth_source": "supplied" if data.date_of_birth
                                    else stored["date_of_birth_source"],
            "gender": data.gender or stored["gender"],
        }
    if data.id_number and not valid_sa_id(data.id_number):
        raise Invalid("id_number", "That ID number is not valid. Please check all 13 digits")
    return enrolment._identity(data, today)


def _set_mobile(conn: Any, person_id: str, mobile: str | None) -> None:
    """Make `mobile` the person's primary number. The number it replaces is
    archived (kept, not deleted), so it stays in the history."""
    current = conn.execute(
        """
        select id, number from person_phones
         where person_id = %s and is_primary and archived_at is null
        """,
        (person_id,),
    ).fetchone()
    if current is not None and current["number"] == mobile:
        return
    if current is not None:
        conn.execute(
            "update person_phones set is_primary = false, archived_at = now() where id = %s",
            (current["id"],),
        )
    if not mobile:
        return
    existing = conn.execute(
        """
        select id from person_phones
         where person_id = %s and number = %s and archived_at is null
        """,
        (person_id, mobile),
    ).fetchone()
    if existing is not None:
        conn.execute("update person_phones set is_primary = true where id = %s",
                     (existing["id"],))
    else:
        conn.execute(
            """
            insert into person_phones (person_id, phone_type, number, number_raw,
                                       is_primary, is_whatsapp, source)
            values (%s, 'mobile', %s, %s, true, true, 'portal')
            """,
            (person_id, mobile, mobile),
        )


_ADDRESS_FIELDS = ("address_line1", "address_line2", "suburb", "city", "province", "postal_code")


def _set_address(conn: Any, person_id: str, data: Any) -> None:
    values = {f: getattr(data, f) or None for f in _ADDRESS_FIELDS}
    current = conn.execute(
        """
        select id from addresses
         where person_id = %s and address_type = 'residential' and is_primary
           and archived_at is null
        """,
        (person_id,),
    ).fetchone()
    if not any(values.values()):
        if current is not None:
            conn.execute("update addresses set archived_at = now(), is_primary = false "
                         "where id = %s", (current["id"],))
        return
    if current is None:
        conn.execute(
            """
            insert into addresses (person_id, address_type, line1, line2, suburb,
                                   city, province, postal_code, is_primary)
            values (%(person_id)s, 'residential', %(address_line1)s, %(address_line2)s,
                    %(suburb)s, %(city)s, %(province)s, %(postal_code)s, true)
            """,
            {**values, "person_id": person_id},
        )
        return
    conn.execute(
        """
        update addresses
           set line1 = %(address_line1)s, line2 = %(address_line2)s, suburb = %(suburb)s,
               city = %(city)s, province = %(province)s, postal_code = %(postal_code)s
         where id = %(id)s
        """,
        {**values, "id": current["id"]},
    )


def _resolve_flags(conn: Any, person_id: str, issues: list[str], staff_email: str) -> None:
    conn.execute(
        """
        update data_quality_flags
           set resolved_at = now(), resolved_by = %s, resolution = 'Corrected in the portal'
         where person_id = %s and resolved_at is null and issue_code = any(%s)
        """,
        (staff_email, person_id, issues),
    )


def update(conn: Any, policy_id: str, data: Any, *, staff_email: str,
           today: date | None = None) -> dict:
    """Correct the main member and how the policy is paid. One transaction."""
    today = today or date.today()
    stored = _main_member(conn, policy_id, lock=True)
    if stored is None:
        raise NotFound("That policy no longer exists, or has no main member.")
    person_id = str(stored["person_id"])
    identity = _identity(data, stored, today)

    payment = _active_payment(conn, policy_id)
    frequency = payment["frequency"] if payment else "monthly"
    debit_day = None if frequency == "once_off" else data.debit_day
    if frequency != "once_off" and debit_day is None:
        raise Invalid("debit_day", "Choose the payment day: the 1st, the 25th or the last day")

    try:
        conn.execute(
            """
            update people
               set surname = %(surname)s, first_names = %(first_names)s,
                   initials = %(initials)s,
                   id_number = %(id_number)s,
                   id_number_raw = case when %(id_number)s::text is distinct from id_number
                                        then %(id_number)s else id_number_raw end,
                   id_number_status = %(id_number_status)s,
                   date_of_birth = %(date_of_birth)s,
                   date_of_birth_source = %(date_of_birth_source)s,
                   gender = %(gender)s, email = %(email)s,
                   language_preference = %(language)s,
                   country_of_birth = %(country_of_birth)s, citizenship = %(citizenship)s,
                   passport_number = %(passport_number)s,
                   employment_status = %(employment_status)s,
                   employer_name = %(employer_name)s, industry = %(industry)s,
                   occupation = %(occupation)s, job_role = %(job_role)s,
                   source_of_funds = %(source_of_funds)s,
                   source_of_funds_other = %(source_of_funds_other)s,
                   salary_day = %(salary_day)s
             where id = %(person_id)s
            """,
            {
                "person_id": person_id,
                "surname": data.surname,
                "first_names": data.first_names,
                "initials": data.initials,
                "email": data.email,
                "language": data.language_preference,
                **{field: getattr(data, field) for field in enrolment._COMPLIANCE},
                **identity,
            },
        )
        _set_mobile(conn, person_id, data.mobile)
    except pg_errors.UniqueViolation as exc:
        raise Conflict(enrolment._conflict_message(exc, data)) from exc

    _set_address(conn, person_id, data)

    if payment is None:
        conn.execute(
            """
            insert into policy_payments (policy_id, method, debit_day, frequency, pay_branch_code)
            values (%s, %s, %s, 'monthly', %s)
            """,
            (policy_id, data.payment_method, debit_day, data.pay_branch_code),
        )
    else:
        conn.execute(
            """
            update policy_payments
               set method = %s, debit_day = %s, pay_branch_code = %s
             where id = %s
            """,
            (data.payment_method, debit_day, data.pay_branch_code, payment["id"]),
        )

    conn.execute("update policies set notes = %s where id = %s",
                 ((data.notes or "").strip() or None, policy_id))

    # A new payment day moves every premium still to come onto it.
    moved = (0, 0)
    if frequency != "once_off" and (payment is None or payment["debit_day"] != debit_day):
        moved = instalments.reschedule(conn, policy_id, staff_email=staff_email,
                                       reason="Payment day changed", today=today)

    if identity["id_number_status"] == "valid":
        _resolve_flags(conn, person_id, _ID_FLAGS, staff_email)
    if data.mobile:
        _resolve_flags(conn, person_id, _PHONE_FLAGS, staff_email)

    # References only: what changed is in member_book_history, not here.
    log_staff_event(conn, staff_email, "member_details_updated", person_id,
                    {"policy_number": stored["policy_number"],
                     "instalments_moved": moved[0]})
    return load(conn, policy_id)


def change_plan(conn: Any, policy_id: str, data: Any, *, staff_email: str,
                today: date | None = None) -> dict:
    """Re-price the policy on another plan, option or frequency and replace the
    premiums still to come. Priced at the main member's age today (or on the
    start date, if that is still ahead)."""
    today = today or date.today()
    stored = _main_member(conn, policy_id, lock=True)
    if stored is None:
        raise NotFound("That policy no longer exists, or has no main member.")
    if stored["status_code"] not in _LIVE_STATUSES:
        raise Conflict("Only a pending or active policy can change plan. "
                       f"This one is {stored['status_code'].replace('_', ' ')}.")

    on = max(stored["entry_date"] or today, today)
    premium_cents, plan_option, cover_cents = enrolment.price(
        conn, plan_code=data.plan_code, plan_option=data.plan_option,
        born=stored["date_of_birth"], on=on, frequency=data.frequency)

    payment = _active_payment(conn, policy_id)
    old_frequency = payment["frequency"] if payment else "monthly"
    if (data.plan_code, plan_option, data.frequency, premium_cents, cover_cents) == (
            stored["plan_code"], stored["plan_option"], old_frequency,
            stored["premium_cents"], stored["cover_cents"]):
        raise Invalid("plan_code", "The policy is already on this plan, at this price.")

    if data.frequency == "once_off":
        debit_day = None
    else:
        debit_day = data.debit_day or (payment["debit_day"] if payment else None)
        if debit_day is None:
            raise Invalid("debit_day", "Choose the payment day: the 1st, the 25th or the last day")

    conn.execute(
        """
        update policies
           set plan_code = %s, plan_option = %s, premium_cents = %s, cover_cents = %s
         where id = %s
        """,
        (data.plan_code, plan_option, premium_cents, cover_cents, policy_id),
    )
    if payment is None:
        conn.execute(
            """
            insert into policy_payments (policy_id, method, debit_day, frequency)
            values (%s, 'undecided', %s, %s)
            """,
            (policy_id, debit_day, data.frequency),
        )
    else:
        conn.execute(
            "update policy_payments set frequency = %s, debit_day = %s where id = %s",
            (data.frequency, debit_day, payment["id"]),
        )

    replaced, scheduled = instalments.reschedule(
        conn, policy_id, staff_email=staff_email, today=today,
        reason=f"Plan changed to {data.plan_code} ({plan_option})")

    # Plan codes and amounts identify nothing about the family.
    log_staff_event(conn, staff_email, "plan_changed", str(stored["person_id"]), {
        "policy_number": stored["policy_number"],
        "from": {"plan_code": stored["plan_code"], "plan_option": stored["plan_option"],
                 "frequency": old_frequency, "premium_cents": stored["premium_cents"]},
        "to": {"plan_code": data.plan_code, "plan_option": plan_option,
               "frequency": data.frequency, "premium_cents": premium_cents},
        "instalments_replaced": replaced,
    })
    return {
        "policy_id": policy_id,
        "plan_code": data.plan_code,
        "plan_option": plan_option,
        "frequency": data.frequency,
        "premium_cents": premium_cents,
        "cover_cents": cover_cents,
        "instalments_replaced": replaced,
        "instalments_scheduled": scheduled,
    }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def history(conn: Any, policy_id: str, limit: int = 300) -> list[dict] | None:
    """The policy's history and its main member's, newest first. None if the
    policy does not exist."""
    policy = conn.execute(
        """
        select p.id, pm.person_id
          from policies p
          left join policy_members pm on pm.policy_id = p.id
                                     and pm.member_type = 'main_member'
                                     and pm.archived_at is null
         where p.id = %s
        """,
        (policy_id,),
    ).fetchone()
    if policy is None:
        return None
    rows = conn.execute(
        """
        select changed_at, changed_by, table_name, operation, old_values, new_values
          from member_book_history
         where policy_id = %(policy)s
            or (person_id = %(person)s and policy_id is null)
         order by changed_at desc, id desc
         limit %(limit)s
        """,
        {"policy": policy_id, "person": policy["person_id"], "limit": limit},
    ).fetchall()

    entries = []
    for row in rows:
        old = row["old_values"] or {}
        new = row["new_values"] or {}
        fields = [f for f in dict.fromkeys([*old, *new]) if f not in _HISTORY_NOISE]
        changes = [{"field": f, "old": _text(old.get(f)), "new": _text(new.get(f))}
                   for f in fields
                   if row["operation"] == "update" or (old.get(f) or new.get(f)) is not None]
        entries.append({
            "changed_at": row["changed_at"],
            "changed_by": row["changed_by"],
            "table_name": row["table_name"],
            "operation": row["operation"],
            "changes": changes,
        })
    return entries
