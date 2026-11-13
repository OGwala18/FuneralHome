"""Turn a workbook of transcribed membership application forms into SQL.

    python db/seed/import_application_forms.py <workbook.xlsx> > db/seed/import_forms.sql

THE INPUT
A workbook with a "Members" sheet (one row per signed application: reference
number, cover, premium, the main member, address, phone, date signed) and a
"Dependants" sheet (one row per life, keyed by the member's reference number).
These are transcriptions of handwriting, so the workbook carries its own
doubts: an "ID check" column and a "Notes" column per row.

THE SAME RULES AS import_policy_template.py
It does not repair data. A value goes in exactly as transcribed, the ID
number's trust is recorded in `id_number_status`, and every doubt becomes a
`data_quality_flags` row the office works through against the paper form.
Notes from the transcriber are kept on the person, so the doubt travels with
the record instead of staying in a spreadsheet.

WHAT IT DECIDES, AND WHY
- Status is 'pending': these are new applications; a policy becomes active
  with its first premium, as in the portal's own enrolment.
- No plan is set. The forms carry a premium and sometimes a cover, not a plan
  code, and a premium that is not on the price list (R200, R450) cannot be
  mapped to one. Each policy gets a 'plan_missing' flag instead of a guess.
- Cover goes in only when it is an amount ("R7,500"). Anything else ("Casket")
  is kept as the flag's raw value, with no amount.
- A dependant listed as a child but whose ID says they were 21 or over on the
  date signed is not recorded as a child: their role is left 'unspecified' and
  flagged, because the form and the ID disagree.

The generated SQL holds personal information. Write it under db/seed/, where
*.sql is gitignored, never anywhere tracked. Reading uses only the standard
library, like the first importer.
"""

from __future__ import annotations

import datetime
import os
import re
import sys
import uuid
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_policy_template import (  # noqa: E402
    NS,
    TENANT,
    id_birth_date,
    id_checksum_ok,
    id_digits,
    id_gender,
    normalise_policy_number,
    q,
    read_sheet,
)

SOURCE = "import:application_forms_2026_11"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
LANGUAGES = {"zulu": "zu", "isizulu": "zu", "english": "en"}
ADULT_AGE = 21


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def load_sheets(path: str) -> dict[str, list[dict[str, str]]]:
    """Every sheet as a list of {header: value} dicts, by sheet name."""
    zf = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

    rels = {
        r.get("Id"): r.get("Target")
        for r in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")).iter(f"{PKG_REL}Relationship")
    }
    sheets = {}
    for sheet in ET.fromstring(zf.read("xl/workbook.xml")).iter(f"{NS}sheet"):
        target = rels[sheet.get(f"{REL_NS}id")].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        raw = read_sheet(zf, target, shared)
        if not raw:
            continue
        width = max((max(r) for r in raw if r), default=-1) + 1
        header = [raw[0].get(i, "") for i in range(width)]
        sheets[sheet.get("name")] = [
            {header[i]: r.get(i, "") for i in range(width)}
            for r in raw[1:]
            if any(v for v in r.values())
        ]
    return sheets


# --------------------------------------------------------------------------
# Normalising
# --------------------------------------------------------------------------

def parse_signed(raw: str) -> datetime.date | None:
    """The forms mix '07/11/2026', '18/06/26 (entry date)' and '2026/10/08'.

    Day-first when the year is last, as South African forms are written. A
    date the transcriber marked as partly legible still parses if all three
    parts are there; its doubt is already in the row's notes.
    """
    if not raw:
        return None
    try:  # an Excel serial number
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(raw)))
    except ValueError:
        pass
    parts = re.findall(r"\d+", raw)
    if len(parts) < 3:
        return None
    a, b, c = parts[:3]
    try:
        if len(a) == 4:
            return datetime.date(int(a), int(b), int(c))
        year = int(c) if len(c) == 4 else 2000 + int(c)
        return datetime.date(year, int(b), int(a))
    except ValueError:
        return None


def rand_to_cents(raw: str) -> int | None:
    """'350', 'R7,500', '7500.00' -> cents. Anything that is not an amount -> None."""
    cleaned = re.sub(r"[R\s,]", "", raw or "", flags=re.IGNORECASE)
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None
    rands, _, cents = cleaned.partition(".")
    return int(rands) * 100 + int((cents + "00")[:2])


def mobile_e164(raw: str) -> str | None:
    """A South African number as +27..., or None if it is not one."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits.startswith("0"):
        return "+27" + digits[1:]
    if len(digits) == 11 and digits.startswith("27"):
        return "+" + digits
    return None


def age_on(born: datetime.date, on: datetime.date) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------

def flag(target: str, target_id: str, code: str, severity: str, field: str,
         raw, detail: str) -> str:
    return (
        f"insert into data_quality_flags (tenant_id, {target}, issue_code, severity, field, "
        f"raw_value, detail, source) values ({q(TENANT)}, {q(target_id)}, {q(code)}, "
        f"{q(severity)}, {q(field)}, {q(raw or None)}, {q(detail)}, 'import');"
    )


def person(sql: dict, row_id: str, surname: str, first_names: str, raw_id: str,
           notes: str | None, language: str | None = None) -> tuple[str, datetime.date | None]:
    """people row plus its ID flags. Returns (person_id, date of birth from the ID)."""
    person_id = str(uuid.uuid4())
    digits = id_digits(raw_id)
    if not digits:
        status = "missing"
    elif len(digits) != 13:
        status = "malformed"
    elif id_checksum_ok(digits):
        status = "valid"
    else:
        status = "checksum_failed"
    encoded = id_birth_date(digits)
    dob = encoded if isinstance(encoded, datetime.date) else None

    sql["people"].append(
        "insert into people (id, tenant_id, surname, first_names, id_number, id_number_raw, "
        "id_number_status, date_of_birth, date_of_birth_source, gender, language_preference, "
        "source, notes) values ("
        f"{q(person_id)}, {q(TENANT)}, {q(surname)}, {q(first_names)}, {q(digits or None)}, "
        f"{q(raw_id or None)}, {q(status)}, {q(dob.isoformat() if dob else None)}, "
        f"{q('derived_from_id' if dob else None)}, {q(id_gender(digits))}, "
        f"{q(language or 'zu')}, {q(SOURCE)}, {q(notes)});"
    )

    id_flags = {
        "missing": ("id_number_missing", "No ID number was transcribed from the form."),
        "malformed": ("id_number_malformed", f"ID number is {len(digits)} digits, not 13."),
        "checksum_failed": ("id_checksum_failed",
                            "ID number fails its checksum, so at least one digit was misread. "
                            "Check it against the paper form."),
    }
    if status in id_flags:
        code, detail = id_flags[status]
        sql["flags"].append(flag("person_id", person_id, code, "high", "ID number",
                                 raw_id, f"{row_id}: {detail}"))
    if encoded == "impossible":
        sql["flags"].append(flag("person_id", person_id, "id_date_impossible", "high",
                                 "ID number", raw_id,
                                 f"{row_id}: the first six digits are not a real date."))
    return person_id, dob


def build(sheets: dict[str, list[dict[str, str]]]) -> dict[str, list[str]]:
    sql: dict[str, list[str]] = {k: [] for k in
                                 ("people", "phones", "addresses", "policies", "members", "flags")}
    members, dependants = sheets["Members"], sheets["Dependants"]

    numbers = [normalise_policy_number(m["Reference no."]) for m in members]
    if len(set(numbers)) != len(numbers):
        raise SystemExit("Two forms share a reference number; resolve that before importing.")

    for m in members:
        number = normalise_policy_number(m["Reference no."])
        signed = parse_signed(m.get("Date signed", ""))
        premium = rand_to_cents(m.get("Total premium (R)", ""))
        cover = rand_to_cents(m.get("Cover amount", ""))
        policy_id = str(uuid.uuid4())

        policy_notes = "; ".join(x for x in (
            f"Transcribed from application form #{m.get('Form #')}",
            f"number read from '{m['Appears in field']}'" if m.get("Appears in field") else "",
            f"premium note: {m['Premium note']}" if m.get("Premium note") else "",
            f"medical questionnaire: {m['Medical questionnaire']}"
            if m.get("Medical questionnaire") else "",
            f"date signed as written: {m['Date signed']}" if m.get("Date signed") else "",
        ) if x)
        sql["policies"].append(
            "insert into policies (id, tenant_id, policy_number, policy_number_raw, status_code, "
            "plan_code, entry_date, premium_cents, cover_cents, currency, source, notes) values ("
            f"{q(policy_id)}, {q(TENANT)}, {q(number)}, {q(m['Reference no.'])}, 'pending', null, "
            f"{q(signed.isoformat() if signed else None)}, {q(premium)}, {q(cover)}, 'ZAR', "
            f"{q(SOURCE)}, {q(policy_notes)});"
        )
        sql["flags"].append(flag(
            "policy_id", policy_id, "plan_missing", "high", "Plan", None,
            f"{number}: the form gives a premium but no plan. Set the plan from the paper form."))
        if cover is None:
            sql["flags"].append(flag(
                "policy_id", policy_id, "cover_missing", "high", "Cover", m.get("Cover amount"),
                f"{number}: no cover amount was transcribed"
                + (f" (the form says '{m['Cover amount']}')" if m.get("Cover amount") else "")
                + ". Set it from the paper form."))
        if premium is None:
            sql["flags"].append(flag(
                "policy_id", policy_id, "premium_missing", "high", "Premium",
                m.get("Total premium (R)"), f"{number}: no premium was transcribed."))
        if signed is None:
            sql["flags"].append(flag(
                "policy_id", policy_id, "entry_date_missing", "medium", "Date signed",
                m.get("Date signed"), f"{number}: no usable date signed on the form."))

        language = LANGUAGES.get((m.get("Language") or "").strip().lower())
        main_id, main_dob = person(sql, number, m["Surname"].strip(), m["Full names"].strip(),
                                   m.get("ID number", "").strip(), m.get("Notes") or None,
                                   language)
        _member(sql, policy_id, main_id, "main_member", main_dob, signed)

        phone = mobile_e164(m.get("Tel", ""))
        if phone:
            sql["phones"].append(
                "insert into person_phones (tenant_id, person_id, phone_type, number, number_raw, "
                f"is_primary) values ({q(TENANT)}, {q(main_id)}, 'mobile', {q(phone)}, "
                f"{q(m['Tel'])}, true);"
            )
        else:
            sql["flags"].append(flag(
                "person_id", main_id, "phone_number_missing", "high", "Tel", m.get("Tel"),
                f"{number}: no usable phone number on the form."))

        if m.get("Address"):
            sql["addresses"].append(
                "insert into addresses (tenant_id, person_id, address_type, line1, is_primary) "
                f"values ({q(TENANT)}, {q(main_id)}, 'residential', {q(m['Address'].strip())}, true);"
            )

        for d in (d for d in dependants
                  if normalise_policy_number(d["Member reference"]) == number):
            notes = "; ".join(x for x in (
                f"Listed on the form as: {d['Listed as']}" if d.get("Listed as") else "",
                d.get("Notes") or "",
            ) if x) or None
            dep_id, dep_dob = person(sql, number, d["Surname"].strip(), d["Name(s)"].strip(),
                                     d.get("ID number", "").strip(), notes)
            listed_child = "child" in (d.get("Listed as") or "").lower()
            adult = dep_dob is not None and signed is not None and \
                age_on(dep_dob, signed) >= ADULT_AGE
            role = "child" if listed_child and not adult else "unspecified"
            member_id = _member(sql, policy_id, dep_id, role, dep_dob, signed)
            if role == "unspecified":
                sql["flags"].append(flag(
                    "policy_member_id", member_id, "member_type_unknown", "medium", "Listed as",
                    d.get("Listed as"),
                    f"{number}: listed as a child, but the ID number gives an adult. "
                    "Set the relationship (spouse, extended family) from the paper form."
                    if listed_child else
                    f"{number}: the relationship was not clear on the form."))

    declared = {normalise_policy_number(m["Reference no."]): m.get("# Dependants") for m in members}
    orphans = [d["Member reference"] for d in dependants
               if normalise_policy_number(d["Member reference"]) not in declared]
    if orphans:
        raise SystemExit(f"Dependants reference forms that are not in Members: {sorted(set(orphans))}")
    return sql


def _member(sql: dict, policy_id: str, person_id: str, role: str,
            dob: datetime.date | None, signed: datetime.date | None) -> str:
    member_id = str(uuid.uuid4())
    entry_age = age_on(dob, signed) if dob and signed else None
    sql["members"].append(
        "insert into policy_members (id, tenant_id, policy_id, person_id, member_type, "
        "entry_age, joined_at, is_inferred) values ("
        f"{q(member_id)}, {q(TENANT)}, {q(policy_id)}, {q(person_id)}, {q(role)}, "
        f"{q(entry_age)}, {q(signed.isoformat() if signed else None)}, false);"
    )
    return member_id


def main() -> int:
    if len(sys.argv) != 2:
        return print(__doc__) or 1
    sql = build(load_sheets(sys.argv[1]))
    out = sys.stdout
    out.write("-- Generated by db/seed/import_application_forms.py. Do not edit by hand.\n")
    out.write("-- Contains personal information: never commit this file.\n")
    out.write("-- " + ", ".join(f"{len(v)} {k}" for k, v in sql.items()) + "\n")
    out.write("-- One transaction: a half-loaded set of applications is worse than none.\n")
    out.write("begin;\n\n")
    for title in ("people", "phones", "addresses", "policies", "members", "flags"):
        out.write(f"-- ---------- {title} ({len(sql[title])}) ----------\n")
        out.write("\n".join(sql[title]) + "\n\n")
    out.write("commit;\n")
    print("-- " + ", ".join(f"{len(v)} {k}" for k, v in sql.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
