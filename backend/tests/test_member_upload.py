"""Settings > User upload: the office's spreadsheet into the member book.

Every person here is made up; every ID number is built in the test with a
correct check digit (or deliberately a wrong one).
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from xml.sax.saxutils import escape

import pytest

from app.services import member_upload

CHECK = "/api/admin/member-upload/check"
IMPORT = "/api/admin/member-upload/import"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

HEADERS = ["Policynumber *", "Policy Status", "EntryDate *", "Type *", "Surname *",
           "FirstNames *", "Initials", "IdentityNumber", "DOB *", "EntryAge", "Product *",
           "UnderwritersPremium", "Premium *", "Cover *", "Branch", "Comments", "Address",
           "Cell", "Email", "DebitOrder", "DebitDay"]


def sa_id(yymmdd: str, serial: str = "5009", wrong: bool = False) -> str:
    """A South African ID number with a correct (or wrong) check digit."""
    body = yymmdd + serial + "08"
    total = 0
    for i, ch in enumerate(reversed(body)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - total % 10) % 10
    return body + str((check + 1) % 10 if wrong else check)


def _col(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def workbook(rows: list[dict], headers: list[str] = HEADERS, sheet: str = "MembersProduct",
             example: bool = True) -> bytes:
    """An .xlsx shaped like the office's template: banner, headings, EXAMPLE row,
    then data. Cells hold strings, except values given as numbers."""
    lines = [["", "Funeral Policy & Claims import template"], [""] + headers]
    if example:
        lines.append(["EXAMPLE ", "001542451", "Active", "2016-04-01", "Main Member", "Example",
                      "Person"])
    for row in rows:
        lines.append([""] + [row.get(h.rstrip(" *"), "") for h in headers])

    xml_rows = []
    for r, values in enumerate(lines, start=1):
        cells = []
        for c, value in enumerate(values):
            if value in ("", None):
                continue
            ref = f"{_col(c)}{r}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml",
                   f'<workbook {ns} {rel}><sheets><sheet name="{sheet}" sheetId="1" r:id="rId1"/>'
                   f"</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
                   f"<worksheet {ns}><sheetData>{''.join(xml_rows)}</sheetData></worksheet>")
    return buf.getvalue()


def number() -> str:
    return f"ZZ{uuid.uuid4().int % 10**7:07d}"


def family(policy: str, **main_overrides) -> list[dict]:
    """A main member, a spouse and a child; the policy number on the first row only."""
    main = {"Policynumber": policy, "EntryDate": "2019-03-01", "Type": "Main Member",
            "Surname": "Testmaker", "FirstNames": "Ayanda", "IdentityNumber": sa_id("800101"),
            "DOB": "1980-01-01", "Product": "Plan B", "Premium": "250", "Cover": "15000",
            "Branch": "Edendale", "Cell": 829990001, "DebitOrder": "Yes", "DebitDay": "25"}
    main.update(main_overrides)
    return [
        main,
        {"Type": "Spouse", "Surname": "Testmaker", "FirstNames": "Lindiwe",
         "IdentityNumber": sa_id("820202", "0011"), "DOB": "1982-02-02"},
        {"Type": "Child", "Surname": "Testmaker", "FirstNames": "Sipho", "DOB": "2012-06-15"},
    ]


def post(client, path: str, data: bytes, **params):
    return client.post(path, content=data, params=params, headers={"Content-Type": XLSX})


# --- who may -----------------------------------------------------------------------

def test_only_admins_and_owners_upload(client, staff_as):
    data = workbook(family(number()))
    assert post(client, CHECK, data).status_code == 401
    staff_as("viewer")
    assert post(client, CHECK, data).status_code == 403
    staff_as("admin")
    assert post(client, CHECK, data).status_code == 200


# --- the check ---------------------------------------------------------------------

def test_a_clean_family_is_ready_and_rows_group_under_the_policy_above(client, staff_as):
    staff_as("admin")
    policy = number()
    out = post(client, CHECK, workbook(family(policy))).json()
    assert out["ready"] == 1 and out["to_fix"] == 0
    p = out["policies"][0]
    assert p["policy_number"] == policy and p["state"] == "ready"
    assert (p["first_row"], p["last_row"]) == (4, 6)     # the EXAMPLE row is skipped
    assert [life["member_type"] for life in p["lives"]] == ["main_member", "spouse", "child"]
    assert p["main_member"] == "Ayanda Testmaker"
    assert (p["premium_cents"], p["cover_cents"], p["product"]) == (25000, 1500000, "Plan B")


@pytest.mark.parametrize("change, column, words", [
    ({"IdentityNumber": sa_id("800101", wrong=True)}, "IdentityNumber", "check digit"),
    ({"IdentityNumber": "80010150090"}, "IdentityNumber", "11 digits"),
    ({"IdentityNumber": sa_id("800101"), "DOB": "1981-01-01"}, "DOB", "does not match"),
    ({"DOB": "", "IdentityNumber": ""}, "DOB", "required"),
    ({"DOB": "31/02/1980"}, "DOB", "not a date"),
    ({"Type": "Ayanda"}, "Type", "not a type"),
    ({"Product": "Gold"}, "Product", "not a plan"),
    ({"Product": ""}, "Product", "no Product"),
    ({"Premium": "two hundred"}, "Premium", "not an amount"),
    ({"Premium": ""}, "Premium", "no premium"),
    ({"Cover": ""}, "Cover", "no cover"),
    ({"EntryDate": "2099-01-01"}, "EntryDate", "future"),
    ({"Cell": "12345"}, "Cell", "not a South African cell"),
    ({"Branch": "Durban"}, "Branch", "not one of the branches"),
    ({"Surname": "=HYPERLINK(1)"}, "Surname", "="),
    ({"DOB": "2010-01-01", "IdentityNumber": ""}, "DOB", "18 or older"),
])
def test_each_failing_row_says_where_and_why(client, staff_as, change, column, words):
    staff_as("admin")
    out = post(client, CHECK, workbook(family(number(), **change))).json()
    p = out["policies"][0]
    assert p["state"] == "fix"
    hits = [x for x in p["problems"] if x["column"] == column]
    assert hits, p["problems"]
    assert words.lower() in hits[0]["message"].lower()
    assert hits[0]["row"] == 4


def test_a_blank_type_on_a_dependant_fails_that_row(client, staff_as):
    staff_as("admin")
    rows = family(number())
    rows[2]["Type"] = ""
    p = post(client, CHECK, workbook(rows)).json()["policies"][0]
    assert [(x["row"], x["column"]) for x in p["problems"]] == [(6, "Type")]


def test_bank_details_fail_the_row_and_are_never_echoed(client, staff_as):
    staff_as("admin")
    headers = HEADERS + ["AccountNumber", "Bank"]
    rows = family(number())
    rows[0]["AccountNumber"] = "62123456789"
    rows[0]["Bank"] = "Some Bank"
    response = post(client, CHECK, workbook(rows, headers=headers))
    p = response.json()["policies"][0]
    columns = {x["column"] for x in p["problems"]}
    assert {"AccountNumber", "Bank"} <= columns
    assert "62123456789" not in response.text and "Some Bank" not in response.text


def test_excel_numbers_and_dates_are_read_as_people_type_them(client, staff_as):
    staff_as("admin")
    rows = family(number(), IdentityNumber=float(sa_id("800101")),
                  DOB=29221, EntryDate=43525.0)         # Excel serials: 1980-01-01, 2019-03-01
    p = post(client, CHECK, workbook(rows)).json()["policies"][0]
    assert p["state"] == "ready", p["problems"]
    assert p["entry_date"] == "2019-03-01"
    assert p["lives"][0]["date_of_birth"] == "1980-01-01"


def test_a_child_id_excel_stored_as_a_number_gets_its_leading_zero_back(client, staff_as):
    staff_as("admin")
    rows = family(number())
    # Born 2005: the ID starts with 0, and Excel keeps 12 digits of the number.
    rows[2]["IdentityNumber"] = int(sa_id("050615", "0123"))
    rows[2]["DOB"] = "2005-06-15"
    p = post(client, CHECK, workbook(rows)).json()["policies"][0]
    assert p["state"] == "ready", p["problems"]
    assert p["lives"][2]["id_number_given"] is True


def test_two_main_members_or_none_fail(client, staff_as):
    staff_as("admin")
    rows = family(number())
    rows[1]["Type"] = "Main Member"
    assert any("second" in x["message"] for x in
               post(client, CHECK, workbook(rows)).json()["policies"][0]["problems"])
    rows[0]["Type"] = rows[1]["Type"] = "Spouse"
    assert any(x["message"] == "The policy has no Main Member." for x in
               post(client, CHECK, workbook(rows)).json()["policies"][0]["problems"])


def test_a_policy_split_in_two_places_fails(client, staff_as):
    staff_as("admin")
    first = number()
    rows = family(first) + family(number()) + [dict(family(first)[1], Policynumber=first)]
    out = post(client, CHECK, workbook(rows)).json()
    assert out["policies"][0]["state"] == "fix"
    assert any("appears again" in x["message"] for x in out["policies"][0]["problems"])


@pytest.mark.parametrize("data, words", [
    (b"not a zip at all", "not an Excel workbook"),
    (workbook([], headers=["Name", "Number"]), "Policynumber"),
])
def test_a_file_that_is_not_the_template_is_refused(client, staff_as, data, words):
    staff_as("admin")
    response = post(client, CHECK, data)
    assert response.status_code == 422
    assert words in response.json()["detail"]


def test_a_workbook_with_an_xml_entity_trick_is_refused(client, staff_as):
    staff_as("admin")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
                                      '<workbook>&a;</workbook>')
    assert post(client, CHECK, buf.getvalue()).status_code == 422


def test_missing_mandatory_columns_are_named(client, staff_as):
    staff_as("admin")
    headers = [h for h in HEADERS if not h.startswith(("Premium", "Cover"))]
    out = post(client, CHECK, workbook(family(number()), headers=headers)).json()
    assert {x["column"] for x in out["file_problems"]} == {"Premium", "Cover"}
    assert out["policies"] == []


# --- the import --------------------------------------------------------------------

def test_good_policies_are_added_and_failing_ones_are_left(client, staff_as, db):
    staff_as("owner")
    good, bad = number(), number()
    rows = family(good) + family(bad, IdentityNumber=sa_id("750505", wrong=True), DOB="1975-05-05",
                                 Surname="Problemcase")
    data = workbook(rows)
    check = post(client, CHECK, data).json()
    assert (check["ready"], check["to_fix"]) == (1, 1)

    result = post(client, IMPORT, data, checksum=check["checksum"])
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["added"] == [good] and body["failed"] == {}
    states = {p["policy_number"]: p["state"] for p in body["check"]["policies"]}
    assert states == {good: "exists", bad: "fix"}

    policy = db.execute(
        "select id, status_code, plan_code, branch_code, entry_date, premium_cents, "
        "cover_cents, source from policies where policy_number = %s", (good,)).fetchone()
    assert policy[1:] == ("active", "plan_b", "edendale", date(2019, 3, 1), 25000, 1500000,
                          "import:portal_upload")
    lives = db.execute(
        "select pm.member_type, p.first_names, p.id_number_status, p.date_of_birth "
        "from policy_members pm join people p on p.id = pm.person_id "
        "where pm.policy_id = %s order by pm.member_type", (policy[0],)).fetchall()
    assert [(m, n) for m, n, *_ in lives] == [("child", "Sipho"), ("main_member", "Ayanda"),
                                              ("spouse", "Lindiwe")]
    assert lives[0][2] == "missing" and lives[1][2] == "valid"
    payment = db.execute("select method, debit_day, frequency::text from policy_payments "
                         "where policy_id = %s", (policy[0],)).fetchone()
    assert payment == ("debit_order", 25, "monthly")
    phone = db.execute("select ph.number from person_phones ph join policy_members pm "
                       "on pm.person_id = ph.person_id where pm.policy_id = %s "
                       "and pm.member_type = 'main_member'", (policy[0],)).fetchone()
    assert phone == ("+27829990001",)                # the leading 0 Excel dropped is back
    assert db.execute("select count(*) from people where surname = 'Problemcase'").fetchone()[0] == 0
    # Schedules only ever start from today: no years of back-dated premiums.
    first_due = db.execute("select min(due_date) from premium_instalments where policy_id = %s",
                           (policy[0],)).fetchone()[0]
    assert first_due >= date.today().replace(day=1)


def test_uploading_the_corrected_sheet_again_adds_only_what_was_missing(client, staff_as):
    staff_as("admin")
    first, second = number(), number()
    data = workbook(family(first))
    post(client, IMPORT, data, checksum=post(client, CHECK, data).json()["checksum"])

    again = workbook(family(first) + family(second, IdentityNumber=sa_id("900303"),
                                            DOB="1990-03-03"))
    check = post(client, CHECK, again).json()
    assert {p["policy_number"]: p["state"] for p in check["policies"]} == {
        first: "exists", second: "ready"}
    body = post(client, IMPORT, again, checksum=check["checksum"]).json()
    assert body["added"] == [second]


def test_a_person_already_in_the_book_is_linked_not_copied(client, staff_as, db):
    staff_as("admin")
    shared_id = sa_id("700707", "0044")
    one, two = number(), number()
    for policy in (one, two):
        data = workbook(family(policy, IdentityNumber=shared_id, DOB="1970-07-07"))
        post(client, IMPORT, data, checksum=post(client, CHECK, data).json()["checksum"])
    assert db.execute("select count(*) from people where id_number = %s",
                      (shared_id,)).fetchone()[0] == 1


def test_the_import_refuses_a_file_other_than_the_one_checked(client, staff_as):
    staff_as("admin")
    checked = post(client, CHECK, workbook(family(number()))).json()["checksum"]
    other = workbook(family(number()))
    response = post(client, IMPORT, other, checksum=checked)
    assert response.status_code == 409


def test_a_beneficiary_row_is_named_on_the_policy_not_covered(client, staff_as, db):
    staff_as("admin")
    policy = number()
    rows = family(policy) + [{"Type": "Beneficiary", "Surname": "Testmaker", "FirstNames": "Zodwa",
                              "IdentityNumber": sa_id("600606", "0022"), "DOB": "1960-06-06"}]
    data = workbook(rows)
    body = post(client, IMPORT, data, checksum=post(client, CHECK, data).json()["checksum"]).json()
    assert body["added"] == [policy]
    names = db.execute(
        "select p.first_names from policy_beneficiaries b join people p on p.id = b.person_id "
        "join policies pol on pol.id = b.policy_id where pol.policy_number = %s",
        (policy,)).fetchall()
    assert names == [("Zodwa",)]
    covered = db.execute(
        "select count(*) from policy_members pm join policies pol on pol.id = pm.policy_id "
        "where pol.policy_number = %s", (policy,)).fetchone()[0]
    assert covered == 3


def test_no_name_or_id_number_reaches_the_log(client, staff_as, caplog):
    staff_as("admin")
    data = workbook(family(number()))
    with caplog.at_level("INFO"):
        post(client, IMPORT, data, checksum=post(client, CHECK, data).json()["checksum"])
    assert "Member upload imported: 1 policies added" in caplog.text
    assert "Ayanda" not in caplog.text and sa_id("800101") not in caplog.text


# --- reading values -----------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("2024-11-29", date(2024, 11, 29)),
    ("2024 /11 29", date(2024, 11, 29)),
    ("2012/ 03 10", date(2012, 3, 10)),
    ("29/11/2024", date(2024, 11, 29)),
    ("45625", date(2024, 11, 29)),
    ("1980-01-01 00:00:00", date(1980, 1, 1)),
    ("2024-02-30", None),
    ("soon", None),
])
def test_dates_in_the_ways_the_office_types_them(raw, expected):
    assert member_upload.parse_date(raw) == expected


@pytest.mark.parametrize("raw, cents", [
    ("250", 25000), ("250.00", 25000), ("R 1 250,50", 125050), ("99.9", 9990), ("abc", None),
])
def test_money_is_whole_cents_never_a_float(raw, cents):
    assert member_upload.money_cents(raw) == cents
