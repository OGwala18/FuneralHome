"""Turn the office's funeral policy spreadsheet into SQL for the 0008-0011 tables.

    python db/seed/import_policy_template.py <workbook.xlsx> > db/seed/import.sql

WHY THIS IS A SCRIPT AND NOT A ONE-OFF PASTE
The office will send another one of these. Every correction made by hand to a
generated INSERT is a correction that is lost the next time, so the mapping
rules live here where they can be re-read and re-run.

WHAT IT REFUSES TO DO
It does not repair data. Eleven of the ID numbers in the first real file fail
their own checksum, one encodes the 38th of April, and two disagree with the
date of birth typed beside them. Guessing at those would put invented facts
about real families into the database, to be discovered at a claim. Instead the
value goes in exactly as supplied, `id_number_status` records how far it can be
trusted, and a row is written to `data_quality_flags` so the office can check it
against the paper application.

Reading the workbook uses only the standard library: an .xlsx is a zip of XML,
and adding openpyxl to the API's dependencies to read one file once is a poor
trade.
"""

from __future__ import annotations

import datetime
import re
import sys
import uuid
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Excel's day zero. 1899-12-30, not 12-31, because Excel believes 1900 was a
# leap year and the offset absorbs the phantom day.
EXCEL_EPOCH = datetime.date(1899, 12, 30)

TENANT = "00000000-0000-0000-0000-000000000001"
SOURCE = "import:funeral_policy_template1"

# Column positions in the MembersProduct sheet, from its header row.
COL = {
    "policy_number": 1,
    "policy_status": 2,
    "entry_date": 3,
    "type": 4,
    "surname": 5,
    "first_names": 6,
    "initials": 7,
    "id_number": 8,
    "dob": 9,
    "entry_age": 10,
    "product": 11,
    "premium": 13,
    "cover": 14,
    "branch": 15,
    "cell": 23,
    "email": 26,
}

BRANCH_CODES = {"pm burg": "pmburg", "pmburg": "pmburg", "pietermaritzburg": "pmburg"}


# --------------------------------------------------------------------------
# Reading the workbook
# --------------------------------------------------------------------------

def _col_index(ref: str) -> int:
    """'AB12' -> 27. Column letters to a zero-based index."""
    letters = re.match(r"([A-Z]+)", ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_sheet(zf: zipfile.ZipFile, path: str, shared: list[str]) -> list[dict[int, str]]:
    rows = []
    for row in ET.fromstring(zf.read(path)).iter(f"{NS}row"):
        cells: dict[int, str] = {}
        for c in row.findall(f"{NS}c"):
            kind, v, inline = c.get("t"), c.find(f"{NS}v"), c.find(f"{NS}is")
            if kind == "s" and v is not None:
                val = shared[int(v.text)]
            elif kind == "inlineStr" and inline is not None:
                val = "".join(t.text or "" for t in inline.iter(f"{NS}t"))
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            cells[_col_index(c.get("r"))] = str(val).strip()
        rows.append(cells)
    return rows


def load_workbook(path: str) -> list[dict[int, str]]:
    zf = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    rows = read_sheet(zf, "xl/worksheets/sheet1.xml", shared)
    # Row 0 is the banner, row 1 the headers, row 2 the template's EXAMPLE row.
    # Dropping the example is the whole reason this slice is hard-coded: its
    # phone number is the only one in the file and it belongs to nobody.
    return [r for r in rows[3:] if any(v for v in r.values())]


# --------------------------------------------------------------------------
# Normalising what the office typed
# --------------------------------------------------------------------------

def parse_date(raw: str) -> datetime.date | None:
    """Handle both of the formats this file mixes.

    Excel serial numbers ('45630.0') and hand-typed text where the separators
    landed wherever the typist's finger did ('2024 /11 29', '2012/ 03 10').
    """
    if not raw:
        return None
    try:
        return EXCEL_EPOCH + datetime.timedelta(days=int(float(raw)))
    except ValueError:
        pass
    parts = re.findall(r"\d+", raw)
    if len(parts) == 3:
        y, m, d = (int(p) for p in parts)
        try:
            return datetime.date(y, m, d)
        except ValueError:
            return None
    return None


def id_digits(raw: str) -> str:
    """'770605 1535 081' and '7706051535081' are the same person."""
    return re.sub(r"\D", "", raw or "")


def id_checksum_ok(digits: str) -> bool:
    """Luhn, as used by the South African ID number."""
    if len(digits) != 13:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def id_birth_date(digits: str) -> datetime.date | str | None:
    """Decode YYMMDD. Returns 'impossible' when the encoded date cannot exist.

    The century split is at 25: nobody on a funeral policy in 2026 was born in
    2099, and a two-digit year of 26 or more is therefore a 19xx birth.
    """
    if len(digits) != 13:
        return None
    yy, mm, dd = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])
    year = 1900 + yy if yy > 25 else 2000 + yy
    try:
        return datetime.date(year, mm, dd)
    except ValueError:
        return "impossible"


def id_gender(digits: str) -> str:
    """Digits 7-10. 5000 and above is male."""
    if len(digits) != 13:
        return "unspecified"
    return "male" if int(digits[6:10]) >= 5000 else "female"


def to_cents(raw: str) -> int | None:
    """R250.00 is 25000. Never a float (AIA 03 section 5.2)."""
    if not raw:
        return None
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return None


def normalise_policy_number(raw: str) -> str:
    """The file holds both 'AA 1324' and 'AA1324' for one policy."""
    return re.sub(r"\s+", "", raw or "").upper()


# --------------------------------------------------------------------------
# SQL emission
# --------------------------------------------------------------------------

def q(value) -> str:
    """Quote for SQL, or NULL. Doubles embedded quotes."""
    if value is None or value == "":
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build(rows: list[dict[int, str]]):
    people_sql: list[str] = []
    policy_sql: list[str] = []
    member_sql: list[str] = []
    flag_sql: list[str] = []
    # Rows for the phone capture sheet. Carrying person_id means the numbers
    # come back as an exact keyed update rather than a match on spelling.
    capture: list[tuple[str, ...]] = []

    # Group the flat sheet back into policies. A blank policy number means
    # "same policy as the row above" - the fill-down a human does in Excel.
    policies: dict[str, list[dict[int, str]]] = {}
    order: list[str] = []
    current = None
    for row in rows:
        raw_number = row.get(COL["policy_number"], "")
        if raw_number:
            current = normalise_policy_number(raw_number)
            if current not in policies:
                policies[current] = []
                order.append(current)
            policies[current].append({"_raw_number": raw_number, **row})
            continue
        if current is None:
            raise SystemExit("First data row has no policy number; cannot group.")
        policies[current].append(row)

    for number in order:
        block = policies[number]
        policy_id = str(uuid.uuid4())

        # Policy-level facts are written once somewhere in the block, not
        # necessarily on the first line: in the source file AA1321's premium
        # sits on its second life. Take the single non-empty value.
        def first(col: str):
            for r in block:
                if r.get(COL[col], ""):
                    return r[COL[col]]
            return ""

        raw_entry = first("entry_date")
        entry_date = parse_date(raw_entry)
        premium_cents = to_cents(first("premium"))
        cover_cents = to_cents(first("cover"))
        raw_branch = first("branch")
        branch_code = BRANCH_CODES.get(raw_branch.lower()) if raw_branch else None
        raw_display = block[0].get("_raw_number", number)

        policy_sql.append(
            "insert into policies (id, tenant_id, policy_number, policy_number_raw, "
            "status_code, plan_code, branch_code, entry_date, premium_cents, "
            "cover_cents, currency, source) values ("
            f"{q(policy_id)}, {q(TENANT)}, {q(number)}, {q(raw_display)}, "
            f"'active', null, {q(branch_code)}, {q(entry_date.isoformat() if entry_date else None)}, "
            f"{q(premium_cents)}, {q(cover_cents)}, 'ZAR', {q(SOURCE)});"
        )

        # Product and cover are mandatory on the template and almost entirely
        # absent from the real file. Flag only what is actually missing: one
        # policy in the first import did carry a cover amount, and raising a
        # task against it would train the office to ignore the queue.
        missing_policy_fields = []
        if first("product") == "":
            missing_policy_fields.append((
                "plan_missing", "Product",
                "No product was recorded on the import. Set the plan from the paper application."))
        if cover_cents is None:
            missing_policy_fields.append((
                "cover_missing", "Cover",
                "No cover amount was recorded on the import. Set it from the paper application."))

        for code, field, detail in missing_policy_fields:
            flag_sql.append(
                "insert into data_quality_flags (tenant_id, policy_id, issue_code, "
                "severity, field, raw_value, detail, source) values ("
                f"{q(TENANT)}, {q(policy_id)}, {q(code)}, 'high', {q(field)}, null, "
                f"{q(detail)}, 'import');"
            )
        if premium_cents is None:
            flag_sql.append(
                "insert into data_quality_flags (tenant_id, policy_id, issue_code, "
                "severity, field, raw_value, detail, source) values ("
                f"{q(TENANT)}, {q(policy_id)}, 'premium_missing', 'high', 'Premium', null, "
                f"'No premium was recorded for this policy.', 'import');"
            )
        if entry_date is None:
            flag_sql.append(
                "insert into data_quality_flags (tenant_id, policy_id, issue_code, "
                "severity, field, raw_value, detail, source) values ("
                f"{q(TENANT)}, {q(policy_id)}, 'entry_date_missing', 'medium', 'EntryDate', "
                f"{q(raw_entry)}, 'No usable entry date was recorded for this policy.', 'import');"
            )

        for position, row in enumerate(block):
            person_id = str(uuid.uuid4())
            surname = row.get(COL["surname"], "").strip()
            first_names = row.get(COL["first_names"], "").strip()
            initials = row.get(COL["initials"], "").strip() or None
            raw_id = row.get(COL["id_number"], "").strip()
            digits = id_digits(raw_id)

            # How far can this ID number be trusted?
            if not digits:
                status = "missing"
            elif len(digits) != 13:
                status = "malformed"
            elif id_checksum_ok(digits):
                status = "valid"
            else:
                status = "checksum_failed"

            supplied_dob = parse_date(row.get(COL["dob"], ""))
            encoded_dob = id_birth_date(digits)

            # The date the office typed wins, because it was read off the
            # document. Where the ID disagrees, both are kept and flagged.
            if supplied_dob:
                dob, dob_source = supplied_dob, "supplied"
            elif isinstance(encoded_dob, datetime.date):
                dob, dob_source = encoded_dob, "derived_from_id"
            else:
                dob, dob_source = None, None

            entry_age = row.get(COL["entry_age"], "")
            try:
                entry_age_val = int(float(entry_age)) if entry_age else None
            except ValueError:
                entry_age_val = None

            people_sql.append(
                "insert into people (id, tenant_id, surname, first_names, initials, "
                "id_number, id_number_raw, id_number_status, date_of_birth, "
                "date_of_birth_source, gender, source) values ("
                f"{q(person_id)}, {q(TENANT)}, {q(surname)}, {q(first_names)}, {q(initials)}, "
                f"{q(digits or None)}, {q(raw_id or None)}, {q(status)}, "
                f"{q(dob.isoformat() if dob else None)}, {q(dob_source)}, "
                f"{q(id_gender(digits))}, {q(SOURCE)});"
            )

            capture.append((
                person_id, number, "main member" if position == 0 else "",
                surname, first_names, initials or "", digits or "",
                dob.isoformat() if dob else "", "",
            ))

            # The first life on a policy is the one carrying the policy number
            # and entry date, and is taken to be the main member. It is marked
            # inferred: the Type column that should have said so was filled on
            # two of sixty-one rows, and both held a first name.
            member_id = str(uuid.uuid4())
            member_type = "main_member" if position == 0 else "unspecified"
            member_sql.append(
                "insert into policy_members (id, tenant_id, policy_id, person_id, "
                "member_type, entry_age, joined_at, is_inferred) values ("
                f"{q(member_id)}, {q(TENANT)}, {q(policy_id)}, {q(person_id)}, "
                f"{q(member_type)}, {q(entry_age_val)}, "
                f"{q(entry_date.isoformat() if entry_date else None)}, true);"
            )

            if member_type == "unspecified":
                flag_sql.append(
                    "insert into data_quality_flags (tenant_id, policy_member_id, issue_code, "
                    "severity, field, raw_value, detail, source) values ("
                    f"{q(TENANT)}, {q(member_id)}, 'member_type_unknown', 'medium', 'Type', "
                    f"{q(row.get(COL['type'], '') or None)}, "
                    f"{q(f'Role of {first_names} {surname} on policy {number} was not recorded. Set it from the paper application.')}, "
                    "'import');"
                )

            # Nobody in this file can be telephoned. That is the single most
            # important gap, so it is one flag per person, not one per import.
            if not row.get(COL["cell"], "").strip():
                flag_sql.append(
                    "insert into data_quality_flags (tenant_id, person_id, issue_code, "
                    "severity, field, raw_value, detail, source) values ("
                    f"{q(TENANT)}, {q(person_id)}, 'phone_number_missing', 'high', 'Cell', null, "
                    f"{q(f'No phone number on file for {first_names} {surname}.')}, 'import');"
                )

            id_flags = {
                "missing": ("id_number_missing", "high",
                            "No ID number was supplied."),
                "malformed": ("id_number_malformed", "high",
                              f"ID number is {len(digits)} digits, not 13."),
                "checksum_failed": ("id_checksum_failed", "high",
                                    "ID number is 13 digits but fails its checksum, so at least one digit is wrong."),
            }
            if status in id_flags:
                code, severity, detail = id_flags[status]
                flag_sql.append(
                    "insert into data_quality_flags (tenant_id, person_id, issue_code, "
                    "severity, field, raw_value, detail, source) values ("
                    f"{q(TENANT)}, {q(person_id)}, {q(code)}, {q(severity)}, 'IdentityNumber', "
                    f"{q(raw_id or None)}, {q(detail)}, 'import');"
                )

            if encoded_dob == "impossible":
                flag_sql.append(
                    "insert into data_quality_flags (tenant_id, person_id, issue_code, "
                    "severity, field, raw_value, detail, source) values ("
                    f"{q(TENANT)}, {q(person_id)}, 'id_date_impossible', 'high', 'IdentityNumber', "
                    f"{q(raw_id)}, 'The first six digits of this ID number are not a real date.', "
                    "'import');"
                )
            elif (isinstance(encoded_dob, datetime.date) and supplied_dob
                  and encoded_dob != supplied_dob):
                flag_sql.append(
                    "insert into data_quality_flags (tenant_id, person_id, issue_code, "
                    "severity, field, raw_value, detail, source) values ("
                    f"{q(TENANT)}, {q(person_id)}, 'dob_id_mismatch', 'medium', 'DOB', "
                    f"{q(raw_id)}, "
                    f"{q(f'Date of birth column says {supplied_dob.isoformat()}, ID number says {encoded_dob.isoformat()}.')}, "
                    "'import');"
                )

    return people_sql, policy_sql, member_sql, flag_sql, capture


def write_phone_sheet(path: str, capture: list[tuple[str, ...]]) -> None:
    """The sheet the office fills in by hand.

    Every person, with an empty Cell column and enough identifying detail to
    find them in the paper file. person_id is the join key on the way back, so
    two people with the same name cannot be confused with one another.

    The ids are generated per run, so this sheet is only valid alongside the
    SQL from the SAME invocation. To produce a sheet against a database that
    has already been loaded, use db/seed/export_phone_capture_sheet.sql.
    """
    import csv

    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([
            "person_id", "policy_number", "role", "surname", "first_names",
            "initials", "id_number", "date_of_birth", "cell",
        ])
        w.writerows(capture)


def main() -> int:
    if len(sys.argv) < 2:
        return print(__doc__) or 1

    rows = load_workbook(sys.argv[1])
    people_sql, policy_sql, member_sql, flag_sql, capture = build(rows)

    # --phone-sheet <path>: also write the blank capture sheet.
    if "--phone-sheet" in sys.argv:
        target = sys.argv[sys.argv.index("--phone-sheet") + 1]
        write_phone_sheet(target, capture)
        print(f"-- phone capture sheet: {len(capture)} rows -> {target}", file=sys.stderr)

    out = sys.stdout
    out.write("-- Generated by db/seed/import_policy_template.py. Do not edit by hand.\n")
    out.write(f"-- Source: {sys.argv[1]}\n")
    out.write(f"-- {len(policy_sql)} policies, {len(people_sql)} people, "
              f"{len(flag_sql)} data quality flags.\n")
    out.write("--\n-- One transaction: a half-loaded book of business is worse than none.\n")
    out.write("begin;\n\n")
    for title, block in (
        ("people", people_sql),
        ("policies", policy_sql),
        ("policy_members", member_sql),
        ("data_quality_flags", flag_sql),
    ):
        out.write(f"-- ---------- {title} ({len(block)}) ----------\n")
        out.write("\n".join(block))
        out.write("\n\n")
    out.write("commit;\n")

    print(f"\n-- people {len(people_sql)}, policies {len(policy_sql)}, "
          f"members {len(member_sql)}, flags {len(flag_sql)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
