# Feature 4 — Taking a payment on the portal instead of a paper receipt

**Working brief for whoever builds this, including an agent picking it up cold.**
Read `ARCHITECTURE.md` and `CLAUDE.md` first. Nothing here is built yet.

| | |
|---|---|
| Status | **Plan, waiting on the owner's decisions** (§2). Written 15 Nov 2026 |
| Why | Branches write every premium on a paper receipt and keep a handwritten cash book. The owner wants staff to do all of it on the portal, with only chosen staff allowed to touch money |
| Source | The office's receipt books and cash books, typed up as a workbook (Nov 2026). The workbook holds personal data and stays out of the repo |
| Schema | Migration **0029** (or the next free number when built): permissions, receipts, allocations, reversals, cash-ups, cash movements |
| Builds on | `premium_instalments` (0013), `policy_payments` (0010, 0013, 0023), `staff_users` / `staff_events` (0007), `services/instalments.py`, `routers/payments.py`, `portal/src/components/PaymentForm.tsx` |

---

## 1. What the paper does today

The paper has three parts, and the portal has to replace all three, or the
office will keep the paper "just in case" and the two will drift apart.

**The receipt book.** These are pre-printed, numbered receipts in books of about
150, one book per run of numbers. Each receipt says:

| On the receipt | Example of what is written | Notes |
|---|---|---|
| Receipt number | Six digits, e.g. 123456 | Printed. Gaps mean a page is missing |
| Date | 02/07/26 | Sometimes day and month swapped, sometimes overwritten |
| Received from | Surname, first name | The person handing over the cash, **often not the policyholder** |
| Amount, in words and in figures | "Two hundred and fifty Rand", R250 | They disagree on about 1 receipt in 40 |
| Policy number(s) | One to four, e.g. "AO 1001, AO 1002, AO 1003" (illustrative) | Several series: AA, AB, AC, AO, BB, CC, a few others |
| Month(s) paid | "July" or "September, October" | Up to eight months on one receipt; often blank |
| Marks | "2 months", "paid up", "Special case", "Client forgot the book at home", a running figure pencilled in the margin | Free text, but they carry meaning (see §4) |
| Cancelled | Crossed through, or "void" | The number is not reused |

Two numbers are not on the receipt at all, but they matter. The printed business
name is not "Induduzo Funeral Home" (open question Q2). There is no record of
which staff member wrote the receipt, beyond handwriting.

**The cash book.** One line per movement of cash: a cash-on-hand count, cash
"dropped" to the safe, an expense paid out (transport, flowers, tents and chairs,
airtime, electricity, food, wages, graves…), cash given out to a person, or cash
reserved for something (a family's funeral, the electricity bill). Each line has
a date, an amount, who handled it and where it went. Branches keep their own.

**The member's payment book.** Families carry a card that the office writes in
("Client forgot the book at home" is written on one receipt). The portal's
receipt has to be something a family can keep in place of it.

## 2. Decisions the owner needs to make

Each one has a recommendation. Nothing in §3–§9 should be built until these are
answered; most of the design follows from them.

| # | Decision | Recommendation |
|---|---|---|
| D1 | **Who may take payments.** Today `admin` and `owner` may record a payment (CLAUDE.md, 14 Oct 2026). The owner wants only certain staff | A **permission granted per person**, separate from the role (§5). The owner grants it; an `admin` without it can no longer record or waive. This replaces the CLAUDE.md decision |
| D2 | **Who may see money.** Receipts, cash-ups and totals | Only staff with a money permission. The overdue call list (who to phone) stays visible to all admins, because phoning families is their job, but it shows the amount owed, never the receipts |
| D3 | **Reversals need a second person?** | Yes. A cashier asks; a supervisor approves (§7). Nobody reverses their own receipt alone |
| D4 | **Receipt numbering.** | System numbers, one gapless series per branch, e.g. `E-000123` Edendale, `B-` Boshoff, `L-` Langalibalele (§6). Paper books are retired at a branch the day it goes live, not run alongside |
| D5 | **How a family gets the receipt.** | WhatsApp, from the 073 line, with a new Utility template. A printed slip as well, if branches get a small printer (Q5) |
| D6 | **Which policies are in scope.** Receipts show at least 446 policy numbers across several series; the member book holds 20 | All series that are Induduzo policies (Q2), and every one must be captured in the book before staff can take money for it on the portal. Until then a payment for an unknown policy goes to "unmatched" (§8) instead of being refused |
| D7 | **Grace period and lapse rule.** When is a family "late", and when does a policy lapse? | The underwriter's policy wording decides this. The Policyholder Protection Rules require a grace period; 30 days is usual for monthly premiums. Suggest: late = 1 day past due; lapse = still unpaid after the grace period on 2 consecutive premiums, confirmed by a supervisor, not automatic |
| D8 | **Cash books on the portal too?** | Yes, in the same feature (§9), or "money out" has no source for the reports (Feature 5) |

## 3. Pricing: what the paper shows, and what the schema cannot say yet

The price list in `ref_plan_prices` (0020, 0021, 0024) is the flyer: Plan A,
Plan B, Plan C by coffin, single or couple and age band, and the Dome options.
A policy copies its premium and cover from a line at enrolment and keeps its own
copy. That is right and stays. The receipts show six things it cannot express:

| # | What the receipts show | Why the schema can't hold it | Proposal |
|---|---|---|---|
| P1 | **Premiums not on the flyer.** The usual amounts match the flyer (R250, R350, R200), but there is a long tail of small amounts per policy per month, mostly on the AO/AB/AC series, and some book policies pay R300 or R450 | `plan_option` must name a price-list line, and enrolment only accepts a listed price | Add the **legacy products** to `ref_plans` / `ref_plan_prices` once the owner lists them (Q3). Until then, allow `plan_code = 'legacy'` with the premium set by a supervisor, a written reason, and a `staff_events` row. Never a free-typed premium at enrolment |
| P2 | **One receipt, several policies.** A parent pays for three or four policies at once, with one amount and no split written down | `premium_instalments` is one row per policy per due date; a payment is a column on it | A **receipt** row plus **allocations** (§8): the money is split across policies and months, and the split is recorded, not guessed |
| P3 | **Several months on one receipt**, paid behind or ahead. Arrears of 1–6 months are common, and so is paying 1–4 months ahead | Possible today only by marking instalments one at a time; no row exists for a month before the schedule began | Allocations across instalments, oldest unpaid first by default (§8). A payment **may create the past instalment it pays**, never an unpaid one |
| P4 | **Part payments** (R100 against R250) | Status is `due` or `paid`; nothing in between | An instalment is paid when its allocations reach its amount; until then it is **part paid**, with the balance shown |
| P5 | **The joining fee** (R400 on dome and casket plans, per the flyer) | It is not a premium and has no row | An instalment `kind`: `premium` (default) or `joining_fee`, created at enrolment when the plan line has one |
| P6 | **Price changes.** A policy's premium can go up | Instalments keep the amount they were generated with (correct), but nothing records the change | `policy_premium_changes` (policy, from date, old, new, reason, who); future `due` rows are regenerated from that date. Past rows never change |

A seventh comes up in conversation rather than on the receipts: **do extra lives
cost extra?** (extended family, or a 16th person on a Dome family plan). The
schema prices a policy, not a life. If they do, it needs a per-life premium
component; if not, nothing changes (Q4).

Money stays integer cents with a currency, everywhere (CLAUDE.md).

## 4. What staff do on the portal

**Take a payment** (cashier):

1. Find the family by policy number, name, ID number or phone. The search runs
   in the request body, never the URL, as on Members today.
2. The screen lists what is owed on every policy that person pays for: arrears
   first, then this month, then the months ahead. It shows amounts and months,
   never anything typed by hand.
3. Type the amount handed over and the method (cash, card on the branch
   machine, EFT seen in the bank). The portal suggests the split, oldest unpaid
   first; the cashier can move it. A part payment is fine.
4. Optional fields: who paid (if not the main member, "received from" as on
   paper), and a note for the marks the paper carries ("special case").
5. **Issue receipt.** The receipt number comes back. The receipt goes to the
   main member's WhatsApp and can be printed or shown on screen.

Nothing on this path asks for a bank account, card number or branch code. For a
card payment the cashier may type the card machine's transaction reference, and
no more (CLAUDE.md, "No bank or card details, ever").

**Close the day** (supervisor), per branch, per cashier: the portal shows the
cash the day's receipts say should be there; the supervisor types what was
counted; a difference needs an explanation. Once closed, that day's receipts
can no longer be voided, only reversed (§7). This replaces the "C.O.H" lines.

**Money out** (supervisor): an expense, a drop to the safe, cash given to
someone, cash reserved, as one form with a type. This replaces the cash book.

## 5. Who may see and use it

Today the role ladder is `viewer` < `admin` < `owner`, and production has two
owners and nine admins (15 Nov 2026). "Some staff, not all" cannot be a rung on that ladder.
Making one admin into "admin who handles money" would also give them everything
else an admin can do. So money handling becomes **permissions granted to a
person**, beside their role:

| Permission | May | Typical holder |
|---|---|---|
| `payments.take` | Take a payment and issue a receipt at their branch; see their own receipts today; request a void or reversal | Branch cashier |
| `payments.supervise` | All of the above at their branch, plus: approve voids, reversals and reallocations; close the day; record money out; waive an instalment; set a legacy premium | Branch supervisor |
| `finance.read` | Read every branch's receipts, cash-ups and the reports (Feature 5). Cannot take or change anything | Owner, executives |

- Granted and revoked by the **owner only**, on the Staff screen. Each grant and
  revocation is a `staff_events` row (`permission_granted`, `permission_revoked`)
  saying who, to whom, what, and when.
- Stored in a `staff_permissions` table (staff, permission, branch, granted by,
  granted at, revoked at), never in Supabase metadata, for the reason
  ARCHITECTURE.md gives for roles.
- A cashier works at a **branch**. Staff accounts have no branch today, so a
  permission carries one. A supervisor for all three branches holds three grants.
- The API checks with `Depends(require_permission("payments.take"))`, the same
  shape as `require_role`. The portal hides what someone cannot do, but that is
  a convenience: the API decides.
- Money permissions need **two-step sign-in** set up. It is already enforced in
  production; the grant refuses an account without a second factor.
- The owner has every permission without a grant, and the last owner cannot be
  removed (as today).

**What changes in CLAUDE.md** once the owner agrees: the row "Who can enrol,
add dependants, record payments: `admin` and `owner`" becomes "Enrol and add
dependants: `admin` and `owner`. Take payments, waive and reverse: staff granted
`payments.take` / `payments.supervise` by the owner." The existing record and
waive endpoints move behind the new permissions in the same release, so there is
never a moment when an admin without the grant can still record a payment.

## 6. Receipts and numbering

- **One series per branch, gapless.** A number is taken from a per-branch
  counter row, locked for the length of the transaction
  (`select … for update`), not from a Postgres sequence, because a sequence
  skips numbers when a transaction rolls back and a gap looks like a missing
  receipt. Format `E-000123`; the letter is the branch.
- **A number is never reused.** A voided receipt keeps its number and shows as
  VOID.
- **The receipt states** the business name and branch, receipt number, date and
  time, amount in figures and words, method, the policies and months it paid,
  any balance still owed, and who took it (first name only). Whatever the
  underwriter requires on a premium receipt (its name, the FSP number) is added
  once Q2 is answered.
- **WhatsApp receipt**: a new Utility template, `induduzo_payment_received`
  (receipt number, amount, policy numbers, months). Like every template, it
  needs Twilio and Meta approval before it can be sent, and it is sent after
  commit, in a background task, so a failed send never loses a receipt.
- **Paper receipts written before go-live** keep their printed number in
  `paper_receipt_number` (unique), so the 397 typed-up receipts and any later
  books can be imported and found by the number on the paper.
- **The day a branch goes live**, its unused paper books are collected and
  marked cancelled. Two numbering systems running at once is how receipts go
  missing.

## 7. Audit trail and reversing a mistake

**Nothing about money is ever edited or deleted.** Receipts, allocations,
reversals and cash-ups are append-only at the database level, with
`do instead nothing` rules as on `enquiry_events` and `staff_events`. A correction
is a new row that points at the old one.

| Mistake | Before the day is closed | After the day is closed |
|---|---|---|
| Wrong amount, or a receipt that should not exist | **Void**: the cashier asks, giving a reason; a supervisor approves; allocations are undone; the receipt shows VOID | **Reversal**: a new, negative receipt dated today points at the original; the original day's cash-up stays as it was; today's shows the correction |
| Right money, wrong policy or month | **Reallocate**: move the allocations; the receipt itself does not change. Supervisor approves | Same |
| Money handed back to a family | A reversal with method `cash`, out | Same |

Every one of these needs a reason and two people: the one asking and the one
approving. Both are recorded, with times. The same person cannot be both, not
even the owner (the owner may approve another person's request).

Every capture, void, reversal, reallocation, cash-up and money-out line also
writes a `staff_events` row, as payments do today. Logs carry the receipt and
policy numbers only, never a name or phone number (CLAUDE.md).

What this makes visible, and Feature 5 reports: voids and reversals per cashier,
cash-up differences per cashier, receipts taken outside office hours, and gaps
in a series (there should be none).

## 8. How it ties to `premium_instalments`

The schedule stays what 0013 made it: **one row per expected payment, generated
forward only; overdue is derived, never stored.** Receipts sit beside it:

```
receipts ──< receipt_allocations >── premium_instalments ──> policies
   │              (amount each)            (due date, amount, status)
   └── receipt_reversals (one per reversed receipt)
```

- An **allocation** is part of a receipt applied to one instalment. The
  allocations of a receipt always add up to its amount; the API checks this in
  the same transaction, and a nightly check in the `jobs` cron compares them.
- An instalment's status is set by the allocation service, in the same
  transaction: `paid` when its allocations reach its amount, `due` (part paid,
  with the balance) when they don't, back to `due` when a reversal takes the
  money away. The Payments screen and reminders keep reading `status`, so they
  work unchanged.
- **Default split**: oldest unpaid first, across all policies on the screen,
  then this month, then ahead. Paying ahead allocates to future rows, which
  exist 12 months out.
- **A payment for a month before the schedule began** creates that month's
  instalment as it is paid, at the policy's premium. It never creates an unpaid
  row in the past. This keeps 0013's rule (no invented arrears) and lets the
  receipts be loaded.
- **Overpayment** beyond the schedule, or a payment for a **policy not yet in
  the book**: an allocation with no instalment, held as **unmatched** with the
  policy number as written. Unmatched money sits in a queue for the supervisor
  until the policy is captured, then it is allocated. It is never refused,
  because the family has paid.
- **The first payment activates a pending policy**, as `record_payment` does
  today, including the enquiry's status and its `policy_activated` event.
- `POST /instalments/{id}/payment` stays and becomes a receipt with one
  allocation, so existing portal screens keep working through the change.
  `premium_instalments.paid_*` stay filled for those reads.
- **Waive** stays, behind `payments.supervise`.
- **Payment reminders** need no change: a paid instalment is not reminded.

## 9. Money out: the cash book

A `cash_movements` table, one row per line of the paper cash book:

| Field | |
|---|---|
| Branch, date, amount (cents), currency | |
| Type | `count` (cash on hand), `drop_to_safe`, `expense`, `given_out`, `reserved`, `released` (a reservation spent or returned), `banked` |
| Category, for expenses | From a short list the owner approves (Q6), e.g. transport, flowers, tents and chairs, airtime and data, electricity, food and refreshments, wages, graves, stationery and copies, other |
| Paid to / handled by | Free text (a supplier, a person) |
| For a family | Optional link to a policy, so funeral costs can later be set against cover paid out (Feature 5) |
| Slip | Optional photo of the till slip, stored privately |
| Recorded by, approved by | Staff; append-only like receipts |

**Wages** are a cash-book line today. Recording that wages were paid in cash is
fine; payroll detail (per-person pay) is not this feature and should not be
typed into it.

The **daily close** (§4) uses both tables: cash expected = yesterday's count +
cash receipts − cash out; the supervisor types what was counted.

## 10. Loading what is already on paper

- The **397 typed-up receipts** go into `receipts` with `paper_receipt_number`,
  the payer as written, the amount, and their Verify or Cancelled status. A
  receipt with one readable policy that is in the book, and a month, is
  allocated; everything else is unmatched, for the office to clear against the
  receipt book. No split across policies is guessed.
- The **cash books** go into `cash_movements`, with lines marked Verify kept as
  `needs_check`.
- On 15 Nov 2026 only 4 of the 397 receipts could be recorded with certainty in
  today's schema (separate note, outside the repo). Everything else waits for
  this.
- **The real prerequisite is the book itself.** Receipts name at least 446
  policies; the member book holds 20. Each policy should be captured from its
  application form (as the 9 forms were on 11 Nov 2026), not invented from a
  receipt, or the payer would become the "main member" of policies they only
  pay for.

## 11. Build order

| Bit | What | Done when |
|---|---|---|
| F4.0 | The owner's decisions (§2) and answers (§12) | This table has answers |
| F4.1 | Migration: `staff_permissions`, `receipts`, `receipt_counters`, `receipt_allocations`, `receipt_reversals`, instalment `kind`, `policy_premium_changes`, `cash_movements`, `cash_ups`. Append-only rules; `induduzo_api` grants written out; nothing to `anon` or `authenticated` | Clean rebuild; tests prove the rules refuse update and delete |
| F4.2 | API: `require_permission`; take a payment; the split; void, reverse, reallocate with approval; the old endpoints behind the permissions. Tests: gapless numbering under concurrency, allocations sum, reversal undoes status, permission refusals | CI green |
| F4.3 | Portal: Take a payment, the receipt, my receipts today, approvals queue, Staff screen grants | Clicked through on internal |
| F4.4 | Daily close and money out | One branch runs a week on internal alongside paper |
| F4.5 | WhatsApp receipt template (approval takes days, so submit it at F4.1) | Approved and sending on internal |
| F4.6 | Import the paper receipts and cash books (§10) | Counts match the workbook |
| F4.7 | Go live one branch at a time; retire its paper books | A full week with no paper at that branch |

Later, and not part of this feature: EFT statement import, debit orders through
a provider (`docs/Induduzo - Taking Payments Online.docx`), card-machine
integration.

**Before any of it goes live:** that document's first point still stands.
Collecting premiums needs the policies to be underwritten by a licensed insurer,
and the business to be a licensed FSP or a representative of one. A portal that
issues premium receipts makes that question sharper, not smaller (Q2).

## 12. Questions for the owner

| # | Question |
|---|---|
| Q1 | Which staff get `payments.take`, which get `payments.supervise`, at which branch, and who gets `finance.read`? |
| Q2 | The receipt books are printed with another business name and a different phone number, and two receipts carry a "UFC" prefix. Who is that, and which policy series (AA, AB, AC, AO, BB, CC, others) are Induduzo's? Who underwrites them, and under whose FSP licence? What must a premium receipt show? |
| Q3 | What are the legacy products and their prices (the series and amounts that are not on the flyer)? |
| Q4 | Do extra lives cost extra on any plan? |
| Q5 | Will branches have a printer for receipts, or is WhatsApp plus the screen enough? |
| Q6 | The list of expense categories. |
| Q7 | Are there field collectors who take cash outside a branch? They would need their own series and a hand-in step at the daily close. |
| Q8 | The grace period and lapse rule (D7), from the underwriter's wording. |
