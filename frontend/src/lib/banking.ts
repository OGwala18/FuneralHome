/**
 * Induduzo's OWN bank account, which families pay their premiums into.
 *
 * This is the business's published receiving account (the "Paying Your
 * Policy?" flyer), not anyone's personal banking details. CLAUDE.md's rule
 * "no bank or card details, ever" is about CUSTOMERS' details, which this site
 * still never asks for.
 *
 * ONE PLACE, ON PURPOSE. A changed account number is how payment fraud works:
 * a scammer sends families "new" banking details. Every surface reads these
 * values from here, so a review of this one file is a review of all of them.
 * Treat any pull request that touches this file as a payments change: check the
 * numbers against the bank's own confirmation letter before merging.
 */

export const BANK_DETAILS = {
  bank: "ABSA Bank",
  accountName: "Induduzo Funeral Home",
  accountType: "Current",
  branchCode: "632005",
  /** As printed on the flyer, grouped for reading aloud. */
  accountNumber: "4127 601 408",
} as const;

/** Where families send proof of payment: the business WhatsApp line. */
export const PROOF_OF_PAYMENT_WHATSAPP = {
  display: "073 731 0521",
  link: "https://wa.me/27737310521",
} as const;
