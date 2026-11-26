"""Adding policies to the member book from the office's spreadsheet.

Settings > User upload in the portal (owner, 26 Nov 2026):

    download the template -> fill in members and policies -> upload it
    -> every row is checked -> staff verify -> the good policies are added

The template is the office's own "Funeral Policy & Claims import template"
(the one db/seed/import_policy_template.py loaded on 11 Nov), minus its bank
account columns. Columns are found by their header, so the office's older
copies of the template work too.

THE RULES (owner's choices, 26 Nov 2026)
- A blank Policynumber means the same policy as the row above, which is how
  the office fills the sheet in. The check shows which policy each row joined.
- Premium and cover come from the sheet, not the price list: these are
  existing policies, and they keep what they actually pay and are covered for.
- A policy is added only when every one of its rows passes. Policies that pass
  are added; the rest are listed, row by row, with the reason, to be fixed and
  uploaded again. A policy already in the book is skipped, so uploading the
  corrected sheet again adds only what was missing.

WHAT IS NEVER ACCEPTED
Bank details. The office's template has AccountNumber, AccountName, Bank,
BranchCode and Account Type columns; a value in any of them fails the row
(ARCHITECTURE.md §7.2). Nothing from those columns is read into memory beyond
"is it empty".

READING THE FILE
An .xlsx is a zip of XML, read here with the standard library (the seed
importer's choice too): no new dependency for one file format. Because the
file comes from a browser, the zip is opened with limits (size, member count,
no DOCTYPE in the XML, so no entity expansion), and a file that breaks them
is refused whole.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

from psycopg import errors as pg_errors

from ..schemas import clean_line, clean_name
from . import enrolment, instalments
from .staff import log_staff_event

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

EXCEL_EPOCH = datetime.date(1899, 12, 30)
SOURCE = "import:portal_upload"

# Limits on what a browser may hand the API as a "spreadsheet".
MAX_UNZIPPED_BYTES = 20_000_000
MAX_ZIP_MEMBERS = 200
MAX_DATA_ROWS = 5000
EARLIEST_ENTRY = datetime.date(1990, 1, 1)


class UnreadableFile(ValueError):
    """The upload is not a workbook this module can read. The message is for staff."""


# --------------------------------------------------------------- columns ---

def _key(header: str) -> str:
    """'Policynumber *' -> 'policynumber'; 'Account Type' -> 'accounttype'."""
    return re.sub(r"[^a-z0-9]", "", (header or "").lower())


# Our field name -> the header keys it may appear under.
COLUMNS: dict[str, tuple[str, ...]] = {
    "policy_number": ("policynumber",),
    "policy_status": ("policystatus",),
    "entry_date": ("entrydate",),
    "type": ("type",),
    "surname": ("surname",),
    "first_names": ("firstnames", "firstname"),
    "initials": ("initials",),
    "id_number": ("identitynumber", "idnumber"),
    "dob": ("dob", "dateofbirth"),
    "product": ("product",),
    "premium": ("premium",),
    "cover": ("cover",),
    "branch": ("branch",),
    "comments": ("comments",),
    "address": ("address",),
    "cell": ("cell", "mobile"),
    "email": ("email",),
    "debit_order": ("debitorder",),
    "debit_day": ("debitday",),
    "stop_order": ("stoporder",),
    "easypay": ("easypaynumber",),
    "payat": ("payatnumber",),
}

# Never stored. A value here fails the row.
BANK_COLUMNS = {"accountnumber": "AccountNumber", "accountname": "AccountName",
                "bank": "Bank", "branchcode": "BranchCode", "accounttype": "Account Type"}

# Their headers, for messages that point at the right column.
LABEL = {
    "policy_number": "Policynumber", "policy_status": "Policy Status", "entry_date": "EntryDate",
    "type": "Type", "surname": "Surname", "first_names": "FirstNames", "initials": "Initials",
    "id_number": "IdentityNumber", "dob": "DOB", "product": "Product", "premium": "Premium",
    "cover": "Cover", "branch": "Branch", "comments": "Comments", "address": "Address",
    "cell": "Cell", "email": "Email", "debit_day": "DebitDay",
}

MEMBER_TYPES = {
    "mainmember": "main_member", "main": "main_member", "principalmember": "main_member",
    "spouse": "spouse", "husband": "spouse", "wife": "spouse",
    "child": "child", "children": "child",
    "extended": "extended", "extendedfamily": "extended", "extendedmember": "extended",
    "beneficiary": "beneficiary",
}
PRODUCTS = {"plana": "plan_a", "planb": "plan_b", "planc": "plan_c",
            "domeplan": "dome_plan", "dome": "dome_plan"}
PRODUCT_LABEL = {"plan_a": "Plan A", "plan_b": "Plan B", "plan_c": "Plan C",
                 "dome_plan": "Dome Plan"}
STATUSES = {"active": "active", "pending": "pending", "lapsed": "lapsed",
            "cancelled": "cancelled", "canceled": "cancelled", "claimed": "claimed"}
BRANCHES = {"pmburg": "pmburg", "pietermaritzburg": "pmburg", "edendale": "edendale",
            "edendalemainroad": "edendale", "headoffice": "edendale", "boshoff": "boshoff",
            "161boshoffstreet": "boshoff", "boshoffstreet": "boshoff",
            "langalibalele": "langalibalele", "171langalibalelestreet": "langalibalele",
            "langalibalelestreet": "langalibalele"}
YES = {"yes", "y", "true", "1", "x"}

_MOBILE_RE = re.compile(r"^\+27[6-8][0-9]{8}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------ the workbook ---

@dataclass
class Sheet:
    headers: dict[str, int]          # our field -> column index
    bank: dict[int, str]             # column index -> its header, for bank columns
    rows: list[tuple[int, dict[int, str]]]   # (Excel row number, column -> text)
    header_row: int
    ignored: list[str]


def _safe_xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    data = zf.read(name)
    if b"<!DOCTYPE" in data[:2048].upper() or b"<!ENTITY" in data.upper():
        raise UnreadableFile("This file contains something a spreadsheet should not.")
    return ET.fromstring(data)


def _col_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref or "")
    if not letters:
        return -1
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _sheet_path(zf: zipfile.ZipFile) -> str:
    """The MembersProduct sheet, else the first sheet in the workbook."""
    names = set(zf.namelist())
    if "xl/workbook.xml" not in names:
        raise UnreadableFile("This is not an Excel workbook (.xlsx).")
    book = _safe_xml(zf, "xl/workbook.xml")
    sheets = [(s.get("name") or "", s.get(f"{REL_NS}id")) for s in book.iter(f"{NS}sheet")]
    if not sheets:
        raise UnreadableFile("The workbook has no sheets.")
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in _safe_xml(zf, "xl/_rels/workbook.xml.rels").iter(f"{PKG_REL_NS}Relationship"):
            rels[rel.get("Id")] = rel.get("Target") or ""
    chosen = next((s for s in sheets if _key(s[0]) == "membersproduct"), sheets[0])
    target = rels.get(chosen[1], "worksheets/sheet1.xml").lstrip("/")
    path = target if target.startswith("xl/") else f"xl/{target}"
    if path not in names:
        raise UnreadableFile("The workbook's member sheet could not be found.")
    return path


def read_sheet(data: bytes) -> Sheet:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError):
        raise UnreadableFile("This is not an Excel workbook (.xlsx). Save it as .xlsx and try again.") from None
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_MEMBERS or sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
        raise UnreadableFile("This workbook is too large. Upload at most 5,000 rows at a time.")

    shared: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for si in _safe_xml(zf, "xl/sharedStrings.xml").findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

    raw_rows: list[tuple[int, dict[int, str]]] = []
    for row in _safe_xml(zf, _sheet_path(zf)).iter(f"{NS}row"):
        number = int(row.get("r") or len(raw_rows) + 1)
        cells: dict[int, str] = {}
        for c in row.findall(f"{NS}c"):
            kind, v, inline = c.get("t"), c.find(f"{NS}v"), c.find(f"{NS}is")
            if kind == "s" and v is not None and v.text is not None:
                index = int(v.text)
                val = shared[index] if 0 <= index < len(shared) else ""
            elif kind == "inlineStr" and inline is not None:
                val = "".join(t.text or "" for t in inline.iter(f"{NS}t"))
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            col = _col_index(c.get("r") or "")
            if col >= 0 and val.strip():
                cells[col] = val.strip()
        if cells:
            raw_rows.append((number, cells))

    # The header row is the one that names Policynumber.
    header_at = next((i for i, (_, cells) in enumerate(raw_rows)
                      if any(_key(v) == "policynumber" for v in cells.values())), None)
    if header_at is None:
        raise UnreadableFile("The sheet has no 'Policynumber' heading. Start from the template and "
                             "keep its headings as they are.")
    header_number, header_cells = raw_rows[header_at]
    by_key = {_key(v): col for col, v in header_cells.items()}
    headers = {name: by_key[k] for name, keys in COLUMNS.items() for k in keys if k in by_key}
    bank = {by_key[k]: label for k, label in BANK_COLUMNS.items() if k in by_key}
    used = set(headers.values()) | set(bank)
    ignored = sorted(header_cells[c].rstrip(" *") for c in header_cells if c not in used)

    rows = []
    for number, cells in raw_rows[header_at + 1:]:
        # The template's own example row, marked EXAMPLE in column A.
        if _key(cells.get(0, "")) == "example":
            continue
        rows.append((number, cells))
    if len(rows) > MAX_DATA_ROWS:
        raise UnreadableFile("This sheet has more than 5,000 rows. Split it and upload each part.")
    return Sheet(headers=headers, bank=bank, rows=rows, header_row=header_number, ignored=ignored)


# --------------------------------------------------------------- values ---

def parse_date(raw: str) -> datetime.date | None:
    """An Excel date number (45630 or 45630.5), or typed text: 2024-11-29,
    '2024 /11 29', 29/11/2024. Day before month when the year comes last."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4,6}(\.\d+)?", raw):
        try:
            return EXCEL_EPOCH + datetime.timedelta(days=int(float(raw)))
        except (ValueError, OverflowError):
            return None
    parts = re.findall(r"\d+", raw.split("T")[0].split(" 00:")[0])
    if len(parts) < 3:
        return None
    a, b, c = parts[:3]
    try:
        if len(a) == 4:
            return datetime.date(int(a), int(b), int(c))
        if len(c) == 4:
            return datetime.date(int(c), int(b), int(a))
    except ValueError:
        return None
    return None


def money_cents(raw: str) -> int | None:
    """'250', '250.00', 'R 1 250,50' -> integer cents. Never a float."""
    text = re.sub(r"[R\s]", "", (raw or "")).replace(",", ".")
    if not text:
        return None
    if text.count(".") > 1:
        head, _, tail = text.rpartition(".")
        text = head.replace(".", "") + "." + tail
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if value.is_nan() or value.is_infinite():
        return None
    return int((value * 100).to_integral_value())


def digits_of(raw: str) -> str:
    """An ID or phone number, as Excel may have stored it: text with spaces,
    or a number ('8001015009087.0', '8.001015009087E12')."""
    text = (raw or "").strip()
    if re.fullmatch(r"\d+(\.0+)?|\d(\.\d+)?[eE]\+?\d+", text):
        try:
            text = str(int(Decimal(text)))
        except InvalidOperation:
            pass
    return re.sub(r"\D", "", text)


def normalise_mobile(raw: str) -> str | None:
    digits = digits_of(raw)
    if len(digits) == 9 and digits[0] in "678":      # Excel dropped the leading 0
        digits = "0" + digits
    if re.fullmatch(r"0[6-8]\d{8}", digits):
        return "+27" + digits[1:]
    if re.fullmatch(r"27[6-8]\d{8}", digits):
        return "+" + digits
    return None


def id_problem(digits: str) -> str | None:
    """Why this is not a valid South African ID number, or None."""
    if len(digits) != 13:
        return f"has {len(digits)} digits; an ID number has 13"
    if not (1 <= int(digits[2:4]) <= 12 and 1 <= int(digits[4:6]) <= 31):
        return "does not start with a real date of birth (YYMMDD)"
    if enrolment.decode_id(digits)[0] is None:
        return "does not start with a real date of birth (YYMMDD)"
    total = 0
    for i, ch in enumerate(reversed(digits[:12])):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    if (10 - total % 10) % 10 != int(digits[12]):
        return "fails its check digit, so one of the digits is wrong"
    return None


# ------------------------------------------------------------ the check ---

@dataclass
class Problem:
    row: int
    column: str
    message: str


@dataclass
class Life:
    row: int
    member_type: str | None
    surname: str
    first_names: str
    initials: str | None
    id_number: str | None
    date_of_birth: datetime.date | None
    mobile: str | None
    email: str | None
    address: str | None


@dataclass
class Policy:
    policy_number: str
    raw_number: str
    first_row: int
    rows: list[int] = field(default_factory=list)
    lives: list[Life] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    entry_date: datetime.date | None = None
    plan_code: str | None = None
    premium_cents: int | None = None
    cover_cents: int | None = None
    status_code: str = "active"
    branch_code: str | None = None
    payment_method: str = "undecided"
    debit_day: int | None = None
    notes: str | None = None
    exists: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems and not self.exists

    @property
    def main_member(self) -> Life | None:
        return next((life for life in self.lives if life.member_type == "main_member"), None)


@dataclass
class CheckResult:
    checksum: str
    policies: list[Policy]
    file_problems: list[Problem]
    ignored_columns: list[str]
    rows: int


def _text(cells: dict[int, str], sheet: Sheet, name: str) -> str:
    col = sheet.headers.get(name)
    return cells.get(col, "").strip() if col is not None else ""


def _policy_fact(policy: Policy, row: int, name: str, value: Any, current: Any) -> Any:
    """Policy facts may sit on any row of the block, but only one value each."""
    if value is None:
        return current
    if current is not None and current != value:
        policy.problems.append(Problem(row, LABEL.get(name, name),
                                       f"{LABEL.get(name, name)} differs from an earlier row of "
                                       f"this policy. Give it once, on the main member's row."))
        return current
    return value


def check(conn: Any, data: bytes, today: datetime.date | None = None) -> CheckResult:
    today = today or datetime.date.today()
    checksum = hashlib.sha256(data).hexdigest()
    sheet = read_sheet(data)

    file_problems: list[Problem] = []
    for name in ("policy_number", "entry_date", "type", "surname", "first_names", "dob",
                 "product", "premium", "cover"):
        if name not in sheet.headers:
            file_problems.append(Problem(sheet.header_row, LABEL[name],
                                         f"The '{LABEL[name]}' column is missing. Use the template's "
                                         f"headings as they are."))
    if file_problems:
        return CheckResult(checksum, [], file_problems, sheet.ignored, len(sheet.rows))
    if not sheet.rows:
        return CheckResult(checksum, [], [Problem(sheet.header_row, "", "The sheet has no rows "
                                                  "under the headings.")], sheet.ignored, 0)

    # Group rows into policies. A blank policy number continues the one above.
    policies: list[Policy] = []
    by_number: dict[str, Policy] = {}
    current: Policy | None = None
    for row, cells in sheet.rows:
        raw = _text(cells, sheet, "policy_number")
        if raw:
            number = re.sub(r"\s+", "", raw).upper()
            if number in by_number:
                by_number[number].problems.append(Problem(
                    row, "Policynumber", f"{number} appears again lower down, separated from its "
                                         f"first rows. Keep each policy's rows together."))
                current = by_number[number]
            else:
                current = Policy(policy_number=number, raw_number=raw, first_row=row)
                policies.append(current)
                by_number[number] = current
                if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,29}", number):
                    current.problems.append(Problem(row, "Policynumber",
                                                    "Use letters and digits only, e.g. AA1332."))
        elif current is None:
            file_problems.append(Problem(row, "Policynumber", "The first row has no policy "
                                         "number, so it belongs to no policy."))
            continue
        current.rows.append(row)
        _check_row(current, row, cells, sheet, today)

    for policy in policies:
        _check_policy(policy, today)

    # Already in the book: skipped, not failed, so the corrected sheet can be
    # uploaded again in full.
    numbers = [p.policy_number for p in policies]
    if numbers:
        existing = {r["policy_number"] for r in conn.execute(
            "select policy_number from policies where policy_number = any(%s) "
            "and archived_at is null", (numbers,)).fetchall()}
        for policy in policies:
            policy.exists = policy.policy_number in existing

    return CheckResult(checksum, policies, file_problems, sheet.ignored, len(sheet.rows))


def _check_row(policy: Policy, row: int, cells: dict[int, str], sheet: Sheet,
               today: datetime.date) -> None:
    problems = policy.problems

    def fail(column: str, message: str) -> None:
        problems.append(Problem(row, column, message))

    for col, label in sheet.bank.items():
        if cells.get(col, "").strip():
            fail(label, f"Bank details are never stored. Clear the {label} column.")

    # Policy facts.
    raw_entry = _text(cells, sheet, "entry_date")
    if raw_entry:
        entry = parse_date(raw_entry)
        if entry is None:
            fail("EntryDate", f"'{raw_entry}' is not a date. Use YYYY-MM-DD, e.g. 2024-11-29.")
        elif entry > today:
            fail("EntryDate", "The entry date is in the future.")
        elif entry < EARLIEST_ENTRY:
            fail("EntryDate", f"An entry date before {EARLIEST_ENTRY.year} is not possible.")
        else:
            policy.entry_date = _policy_fact(policy, row, "entry_date", entry, policy.entry_date)

    raw_product = _text(cells, sheet, "product")
    if raw_product:
        plan = PRODUCTS.get(_key(raw_product))
        if plan is None:
            fail("Product", f"'{raw_product}' is not a plan. Use Plan A, Plan B, Plan C or Dome Plan.")
        else:
            policy.plan_code = _policy_fact(policy, row, "product", plan, policy.plan_code)

    for name, limit, label in (("premium", 10_000_000, "R100,000"),
                               ("cover", 1_000_000_000, "R10,000,000")):
        raw = _text(cells, sheet, name)
        if raw:
            cents = money_cents(raw)
            if cents is None or cents <= 0:
                fail(LABEL[name], f"'{raw}' is not an amount in rand, e.g. 250 or 250.00.")
            elif cents > limit:
                fail(LABEL[name], f"{LABEL[name]} over {label} cannot be right.")
            else:
                setattr(policy, f"{name}_cents",
                        _policy_fact(policy, row, name, cents, getattr(policy, f"{name}_cents")))

    raw_status = _text(cells, sheet, "policy_status")
    if raw_status:
        status = STATUSES.get(_key(raw_status))
        if status is None:
            fail("Policy Status", f"'{raw_status}' is not a status. Use Active, Pending, Lapsed, "
                                  f"Cancelled or Claimed, or leave it blank for Active.")
        else:
            policy.status_code = status

    raw_branch = _text(cells, sheet, "branch")
    if raw_branch:
        branch = BRANCHES.get(_key(raw_branch))
        if branch is None:
            fail("Branch", f"'{raw_branch}' is not one of the branches: Edendale, Boshoff Street, "
                           f"Langalibalele Street or Pietermaritzburg.")
        else:
            policy.branch_code = _policy_fact(policy, row, "branch", branch, policy.branch_code)

    if _key(_text(cells, sheet, "debit_order")) in YES:
        policy.payment_method = "debit_order"
    elif _key(_text(cells, sheet, "stop_order")) in YES:
        policy.payment_method = "stop_order"
    elif _text(cells, sheet, "easypay"):
        policy.payment_method = "easypay"
    elif _text(cells, sheet, "payat"):
        policy.payment_method = "payat"
    raw_day = _text(cells, sheet, "debit_day")
    if raw_day:
        day = digits_of(raw_day)
        if not day or not 1 <= int(day) <= 31:
            fail("DebitDay", f"'{raw_day}' is not a day of the month (1 to 31).")
        else:
            policy.debit_day = int(day)

    comments = _text(cells, sheet, "comments")
    if comments:
        try:
            clean_line(comments.replace("\n", " "))
            policy.notes = ((policy.notes + " ") if policy.notes else "") + comments[:1000]
        except ValueError as exc:
            fail("Comments", str(exc))

    # The life on this row.
    raw_type = _text(cells, sheet, "type")
    member_type = MEMBER_TYPES.get(_key(raw_type)) if raw_type else None
    if not raw_type:
        fail("Type", "Type is required: Main Member, Spouse, Child, Extended or Beneficiary.")
    elif member_type is None:
        fail("Type", f"'{raw_type}' is not a type. Use Main Member, Spouse, Child, Extended or "
                     f"Beneficiary.")

    names = {}
    for name, label in (("surname", "Surname"), ("first_names", "FirstNames")):
        raw = _text(cells, sheet, name)
        if not raw:
            fail(label, f"{label} is required.")
            names[name] = ""
            continue
        try:
            names[name] = clean_name(raw[:100]) or ""
        except ValueError as exc:
            fail(label, str(exc))
            names[name] = raw
    initials = _text(cells, sheet, "initials") or None
    if initials and len(initials) > 10:
        fail("Initials", "Initials are at most 10 letters.")
        initials = None

    id_number = None
    born_from_id = None
    raw_id = _text(cells, sheet, "id_number")
    if raw_id:
        digits = digits_of(raw_id)
        # Someone born in 2000-2009 has an ID starting with 0, which Excel drops
        # when the cell holds a number. The check digit still has to pass.
        if len(digits) == 12 and re.fullmatch(r"[\d.eE+]+", raw_id):
            digits = "0" + digits
        why = id_problem(digits)
        if why:
            fail("IdentityNumber", f"The ID number {why}. Check it against the ID document.")
        else:
            id_number = digits
            born_from_id = enrolment.decode_id(digits, today)[0]

    raw_dob = _text(cells, sheet, "dob")
    born = None
    if raw_dob:
        born = parse_date(raw_dob)
        if born is None:
            fail("DOB", f"'{raw_dob}' is not a date. Use YYYY-MM-DD, e.g. 1980-01-01.")
        elif born > today or born.year < 1900:
            fail("DOB", "The date of birth is not possible.")
            born = None
        elif born_from_id and born != born_from_id:
            fail("DOB", f"The date of birth ({born.isoformat()}) does not match the ID number "
                        f"({born_from_id.isoformat()}). One of them is wrong.")
    elif born_from_id:
        born = born_from_id
    else:
        fail("DOB", "DOB is required (or a valid ID number, which carries it).")

    mobile = None
    raw_cell = _text(cells, sheet, "cell")
    if raw_cell:
        mobile = normalise_mobile(raw_cell)
        if mobile is None or not _MOBILE_RE.fullmatch(mobile):
            fail("Cell", f"'{raw_cell}' is not a South African cell number, e.g. 082 123 4567.")
            mobile = None

    email = (_text(cells, sheet, "email") or "").lower() or None
    if email and (not _EMAIL_RE.fullmatch(email) or email.startswith(("=", "+", "@"))):
        fail("Email", f"'{email}' is not an email address.")
        email = None

    address = _text(cells, sheet, "address") or None
    if address:
        try:
            clean_line(address.replace("\n", ", "))
            address = address.replace("\n", ", ")[:200]
        except ValueError as exc:
            fail("Address", str(exc))
            address = None

    policy.lives.append(Life(row=row, member_type=member_type, surname=names["surname"],
                             first_names=names["first_names"], initials=initials,
                             id_number=id_number, date_of_birth=born, mobile=mobile,
                             email=email, address=address))


def _check_policy(policy: Policy, today: datetime.date) -> None:
    first = policy.first_row
    fail = lambda column, message, row=first: policy.problems.append(Problem(row, column, message))  # noqa: E731

    if policy.entry_date is None and not any(p.column == "EntryDate" for p in policy.problems):
        fail("EntryDate", "The policy has no entry date. Put it on the main member's row.")
    if policy.plan_code is None and not any(p.column == "Product" for p in policy.problems):
        fail("Product", "The policy has no Product (Plan A, Plan B, Plan C or Dome Plan).")
    if policy.premium_cents is None and not any(p.column == "Premium" for p in policy.problems):
        fail("Premium", "The policy has no premium. Put it on the main member's row.")
    if policy.cover_cents is None and not any(p.column == "Cover" for p in policy.problems):
        fail("Cover", "The policy has no cover amount. Put it on the main member's row.")

    mains = [life for life in policy.lives if life.member_type == "main_member"]
    if not mains and not any(p.column == "Type" for p in policy.problems):
        fail("Type", "The policy has no Main Member.")
    for extra in mains[1:]:
        fail("Type", "A policy has one Main Member; this is a second.", extra.row)

    on = policy.entry_date or today
    for life in policy.lives:
        age = enrolment.age_on(life.date_of_birth, on)
        if age is None:
            continue
        if life.member_type == "main_member" and age < 18:
            fail("DOB", f"The main member was {age} on the entry date; they must be 18 or older.",
                 life.row)
        if life.member_type == "beneficiary" and age < 18:
            fail("DOB", f"A beneficiary must be 18 or older; this one was {age}.", life.row)
        if life.date_of_birth and policy.entry_date and life.date_of_birth > policy.entry_date:
            fail("DOB", "Born after the policy's entry date.", life.row)

    seen: dict[str, int] = {}
    for life in policy.lives:
        if life.id_number:
            if life.id_number in seen:
                fail("IdentityNumber", f"The same ID number as row {seen[life.id_number]}.", life.row)
            else:
                seen[life.id_number] = life.row

    policy.problems.sort(key=lambda p: (p.row, p.column))


# ------------------------------------------------------------- the import ---

class _Person:
    """What enrolment's helpers read from a person (getattr-based)."""

    def __init__(self, life: Life) -> None:
        self.surname = life.surname
        self.first_names = life.first_names
        self.initials = life.initials
        self.id_number = life.id_number
        self.date_of_birth = life.date_of_birth
        self.gender = None
        self.mobile = life.mobile
        self.email = life.email
        self.language_preference = "zu"
        self.address_line1 = life.address
        self.relationship = None
        self.share_percent = None


def _person_id(conn: Any, life: Life, today: datetime.date) -> str:
    """An existing person (same ID number) is linked, never created twice."""
    if life.id_number:
        found = conn.execute(
            "select id from people where id_number = %s and archived_at is null",
            (life.id_number,),
        ).fetchone()
        if found:
            return str(found["id"])
    person = _Person(life)
    identity = enrolment._identity(person, today)
    person_id = enrolment._insert_person(conn, person, identity, email=life.email,
                                         language="zu", source=SOURCE)
    if life.mobile:
        enrolment._add_phone(conn, person_id, life.mobile)
    enrolment._add_address(conn, person_id, person)
    return person_id


def import_policy(conn: Any, policy: Policy, *, staff_email: str,
                  today: datetime.date | None = None) -> str:
    """Write one checked policy. The caller holds the savepoint."""
    today = today or datetime.date.today()
    main = policy.main_member
    assert main is not None and policy.ok
    main_id = _person_id(conn, main, today)

    policy_id = str(conn.execute(
        """
        insert into policies (policy_number, policy_number_raw, status_code, plan_code,
                              branch_code, entry_date, premium_cents, cover_cents,
                              notes, source)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (policy.policy_number, policy.raw_number, policy.status_code, policy.plan_code,
         policy.branch_code, policy.entry_date, policy.premium_cents, policy.cover_cents,
         policy.notes, SOURCE),
    ).fetchone()["id"])

    for life in policy.lives:
        if life.member_type == "beneficiary":
            continue
        person_id = main_id if life is main else _person_id(conn, life, today)
        conn.execute(
            """
            insert into policy_members (policy_id, person_id, member_type, entry_age, joined_at)
            values (%s, %s, %s, %s, %s)
            """,
            (policy_id, person_id, life.member_type,
             enrolment.age_on(life.date_of_birth, policy.entry_date), policy.entry_date),
        )

    conn.execute(
        """
        insert into policy_payments (policy_id, method, debit_day, frequency)
        values (%s, %s, %s, 'monthly')
        """,
        (policy_id, policy.payment_method, policy.debit_day),
    )

    for life in policy.lives:
        if life.member_type == "beneficiary":
            # Not a covered life: named as who the policy pays out to. Linked
            # to an existing person by ID number, or created.
            enrolment.add_beneficiary(conn, policy_id, staff_email=staff_email,
                                      person=_Person(life), today=today)

    instalments.generate(conn, policy_id, today=today)
    log_staff_event(conn, staff_email, "member_imported", main_id,
                    {"policy_number": policy.policy_number, "lives": len(policy.lives),
                     "source": SOURCE})
    return policy_id


def import_all(conn: Any, result: CheckResult, *, staff_email: str,
               today: datetime.date | None = None) -> tuple[list[str], dict[str, str]]:
    """Each ready policy in its own savepoint: one that fails on the way in
    (someone enrolled the same number a minute ago) leaves the rest added."""
    added: list[str] = []
    failed: dict[str, str] = {}
    for policy in result.policies:
        if not policy.ok:
            continue
        try:
            with conn.transaction():
                import_policy(conn, policy, staff_email=staff_email, today=today)
            added.append(policy.policy_number)
        except pg_errors.UniqueViolation:
            failed[policy.policy_number] = ("Someone added this policy number, or one of its ID "
                                            "numbers, while you were checking. Look it up in Members.")
        except (enrolment.Invalid, enrolment.Conflict, enrolment.NotFound) as exc:
            failed[policy.policy_number] = str(exc.args[-1] if exc.args else exc)
    return added, failed
