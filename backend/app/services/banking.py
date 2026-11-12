"""Induduzo's OWN bank account: where families pay their premiums.

The office's published receiving account (the "Paying Your Policy?" flyer), sent
on WhatsApp when a family asks to pay and in the payment-day reminders. It is
the business's account, not a customer's: CLAUDE.md's "no bank or card details,
ever" is about customers' details, which this system still never asks for.

ONE PLACE, ON PURPOSE. A changed account number is how payment fraud works: a
scammer sends families "new" banking details. Every message reads these values
from here, so a review of this file is a review of all of them. Treat a change
here as a payments change and check it against the bank's own confirmation
letter before it merges. tests/test_whatsapp_pay.py pins the values.
"""

from __future__ import annotations

BANK = "ABSA Bank"
ACCOUNT_NAME = "Induduzo Funeral Home"
ACCOUNT_TYPE = "Current"
BRANCH_CODE = "632005"
ACCOUNT_NUMBER = "4127 601 408"
PROOF_OF_PAYMENT_EMAIL = "info@induduzo.co.za"


def details_block(reference: str) -> str:
    """The account, as a WhatsApp message block, with the reference to use."""
    return (
        f"Bank: {BANK}\n"
        f"Account name: {ACCOUNT_NAME}\n"
        f"Account type: {ACCOUNT_TYPE}\n"
        f"Branch code: {BRANCH_CODE}\n"
        f"Account number: {ACCOUNT_NUMBER}\n"
        f"Reference: {reference}"
    )
