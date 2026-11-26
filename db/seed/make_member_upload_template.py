"""Build the blank template for Settings > User upload in the portal.

    pip install openpyxl          # a developer tool only; the API never needs it
    python db/seed/make_member_upload_template.py

Writes portal/public/templates/induduzo-member-upload-template.xlsx, which the
portal offers as "Download the template". Re-run it when the rules in
backend/app/services/member_upload.py change, and commit the new file.

It is the office's own "Funeral Policy & Claims import template" with the
same headings, so the office's older copies still upload, but:
- no bank account columns (AccountNumber, AccountName, Bank, BranchCode,
  Account Type): the system never stores bank details;
- drop-down lists for Type, Product, Policy Status, Branch and DebitOrder;
- IdentityNumber and Cell formatted as text, so Excel keeps the leading 0 and
  does not turn an ID number into 8.00101E+12;
- EntryDate and DOB formatted as dates, YYYY-MM-DD;
- a "How to fill it in" tab with the rules the upload checks.

The example row is made up and has no ID number or phone number, on purpose:
the office's original template carried a real-looking ID number in its example.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

OUT = Path(__file__).resolve().parents[2] / "portal" / "public" / "templates" / \
    "induduzo-member-upload-template.xlsx"
LAST_ROW = 2000

# (heading, width, kind). Mandatory headings end in " *", as in the office's file.
COLUMNS = [
    ("Policynumber *", 15, "text"),
    ("Policy Status", 13, "status"),
    ("EntryDate *", 13, "date"),
    ("Type *", 15, "type"),
    ("Surname *", 18, "text"),
    ("FirstNames *", 20, "text"),
    ("Initials", 9, "text"),
    ("IdentityNumber", 17, "text"),
    ("DOB *", 13, "date"),
    ("Product *", 12, "product"),
    ("Premium *", 11, "money"),
    ("Cover *", 12, "money"),
    ("Branch", 22, "branch"),
    ("Comments", 30, "text"),
    ("Address", 34, "text"),
    ("Cell", 14, "text"),
    ("Email", 26, "text"),
    ("DebitOrder", 11, "yesno"),
    ("DebitDay", 9, "day"),
    ("StopOrder", 10, "yesno"),
    ("EasyPayNumber", 15, "text"),
    ("PayAtNumber", 14, "text"),
]

LISTS = {
    "type": '"Main Member,Spouse,Child,Extended,Beneficiary"',
    "product": '"Plan A,Plan B,Plan C,Dome Plan"',
    "status": '"Active,Pending,Lapsed,Cancelled,Claimed"',
    "branch": '"Edendale,Boshoff Street,Langalibalele Street,Pietermaritzburg"',
    "yesno": '"Yes,No"',
}

EXAMPLE = {
    "Policynumber *": "AA0000", "Policy Status": "Active", "EntryDate *": "2024-01-31",
    "Type *": "Main Member", "Surname *": "Example", "FirstNames *": "Person",
    "DOB *": "1980-01-01", "Product *": "Plan B", "Premium *": 250, "Cover *": 15000,
    "Branch": "Edendale", "DebitOrder": "Yes", "DebitDay": 25,
}

GUIDE = [
    ("How to fill in the member upload", ""),
    ("", ""),
    ("One row per person", "The main member first, then the spouse, children, extended family "
                           "and beneficiaries on that policy, each on their own row."),
    ("Policynumber", "On the main member's row. Leave it blank on the rows under it: a blank "
                     "means 'the same policy as the row above'. Keep each policy's rows together."),
    ("EntryDate, Product, Premium, Cover", "Once per policy, on the main member's row. Premium "
                                           "and cover are what this family actually pays and is "
                                           "covered for, in rand (250 or 250.00)."),
    ("Type", "Main Member, Spouse, Child, Extended or Beneficiary. Every row needs one. A policy "
             "has exactly one Main Member."),
    ("IdentityNumber", "13 digits, checked: the date at the start must be real and the last "
                       "digit must match. If it is given, DOB must agree with it."),
    ("DOB", "YYYY-MM-DD. May be left blank only when a valid ID number is given."),
    ("Ages", "The main member and any beneficiary must be 18 or older on the entry date."),
    ("Cell", "A South African cell number, e.g. 082 123 4567."),
    ("Bank details", "Never. The system does not store account numbers, banks or branch codes."),
    ("", ""),
    ("What happens when you upload", "Every row is checked. Policies whose rows all pass are "
                                     "added to the member book once you confirm. Any that fail "
                                     "are listed by row number with the reason: fix them here and "
                                     "upload the whole sheet again. Policies already added are "
                                     "skipped, so nothing is added twice."),
    ("The example row", "Row 3, marked EXAMPLE, is ignored. Type over it or leave it."),
]


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "MembersProduct"

    gold = PatternFill("solid", fgColor="F4E7C5")
    ws["B1"] = ("Induduzo member upload  •  Fields marked * are mandatory  •  keep the headings "
                "as they are  •  see the 'How to fill it in' tab")
    ws["B1"].font = Font(bold=True)
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=len(COLUMNS) + 1)

    for i, (heading, width, kind) in enumerate(COLUMNS, start=2):
        cell = ws.cell(row=2, column=i, value=heading)
        cell.font = Font(bold=True)
        cell.fill = gold
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        letter = cell.column_letter
        ws.column_dimensions[letter].width = width
        fmt = {"date": "yyyy-mm-dd", "money": "0.00", "text": "@"}.get(kind)
        if fmt:
            for row in range(3, LAST_ROW + 1):
                ws.cell(row=row, column=i).number_format = fmt
        if kind in LISTS:
            dv = DataValidation(type="list", formula1=LISTS[kind], allow_blank=True,
                                showErrorMessage=True, errorTitle=heading.rstrip(" *"),
                                error="Choose from the list.")
            dv.add(f"{letter}4:{letter}{LAST_ROW}")
            ws.add_data_validation(dv)
        if kind == "day":
            dv = DataValidation(type="whole", operator="between", formula1="1", formula2="31",
                                allow_blank=True, showErrorMessage=True,
                                error="A day of the month, 1 to 31.")
            dv.add(f"{letter}4:{letter}{LAST_ROW}")
            ws.add_data_validation(dv)

    ws.cell(row=3, column=1, value="EXAMPLE").font = Font(italic=True, color="888888")
    for i, (heading, _, kind) in enumerate(COLUMNS, start=2):
        if heading in EXAMPLE:
            value = EXAMPLE[heading]
            cell = ws.cell(row=3, column=i, value=value)
            cell.font = Font(italic=True, color="888888")
    ws.column_dimensions["A"].width = 10
    ws.freeze_panes = "C3"

    guide = wb.create_sheet("How to fill it in")
    guide.column_dimensions["A"].width = 34
    guide.column_dimensions["B"].width = 110
    for r, (what, how) in enumerate(GUIDE, start=1):
        guide.cell(row=r, column=1, value=what).font = Font(bold=True, size=14 if r == 1 else 11)
        guide.cell(row=r, column=2, value=how).alignment = Alignment(wrap_text=True, vertical="top")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
