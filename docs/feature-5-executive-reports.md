# Feature 5 — Reports: how the business is doing

**Working brief for whoever builds this, including an agent picking it up cold.**
Read `ARCHITECTURE.md`, `CLAUDE.md` and `docs/feature-4-payment-capture.md`
first. Nothing here is built yet.

| | |
|---|---|
| Status | **Plan, waiting on the owner's decisions** (§2). Written 15 Nov 2026 |
| Who it is for | The owner and the executives: people granted `finance.read` (Feature 4, §5) |
| Depends on | Feature 4 for every money figure. The member book holding the whole business for every policy figure (§3) |
| Schema | Reporting views in a migration after Feature 4's. No new tables of record |

---

## 1. What the owner asked for

"Who's late, who isn't paying, money out, money in, etc. All sorts of reports a
company like this would want." Below is that list, made precise enough that two
people reading the same report reach the same number.

## 2. Decisions the owner needs to make

| # | Decision | Recommendation |
|---|---|---|
| R1 | **Who sees reports** | `finance.read` holders only. Branch supervisors see their own branch's collections and cash-up, not the company totals |
| R2 | **Definitions** (§4): late, not paying, lapsed, active, new | As in §4. Once agreed they live in one place, the SQL views, so every screen and export agrees |
| R3 | **Where reports appear** | A **Reports** area on the portal, plus a short monthly summary emailed on the 1st with totals only. Names and phone numbers stay on the portal, never in an email |
| R4 | **Exports** | CSV for the accountant, behind `finance.read`. Each export writes a `staff_events` row (who, which report, which period) |
| R5 | **Targets** | Optional. If the owner sets monthly targets per branch (new policies, collections), reports show progress against them |

## 3. The gap that matters most

**Reports can only count what the system holds.** On 15 Nov 2026 the member book
holds 20 policies. The office's receipts name at least 446 policy numbers, and
the cash books are still on paper. A report built today would say the business
is a fraction of its real size, with no money coming in. So:

- money figures need Feature 4 live at a branch, and they are true for that
  branch from its go-live date onwards, plus whatever paper is imported;
- policy figures need the rest of the book captured from the application forms;
- every report shows **"data from …"**: the date each branch went live, and how
  many policies are captured. Nobody should mistake a partial figure for a total.

## 4. Definitions

| Term | Means | Source |
|---|---|---|
| **Due** | An instalment whose due date has arrived | `premium_instalments` |
| **Late** | Due, not fully paid, past its due date. Days late = today − due date | as now: `instalments_outstanding.days_overdue` |
| **In grace** | Late, but within the grace period (Feature 4, D7) | rule + instalments |
| **Not paying** | A live policy with no money allocated to it for 60 days or more (adjustable) | allocations |
| **Lapsed** | Status `lapsed`, set when a supervisor confirms a lapse the system proposed under the rule (Feature 4, D7) | `policies.status_code` + a status history |
| **Active** | Status `active`: in force and paying | `policies` |
| **New** | A policy whose first premium was paid in the period (sales are counted when money arrives, not when a form is signed) | first allocation |
| **Collected** | Receipts in the period, net of reversals | `receipts` |
| **Expected** | Premiums due in the period on live policies | instalments |
| **Collection rate** | Collected for the period's premiums ÷ expected | both |
| **Money out** | Expenses, cash given out and banking, from the cash book | `cash_movements` |

Policies need a **status history** for lapses, reinstatements and month-end
counts: one row per status change (from, to, when, who, why). Today the status is
overwritten. This is the one new table this feature needs, and it belongs in the
same migration as the views.

## 5. The reports

Every report can be cut **by branch**, **by plan** (and series), and by period
(day, week, month, a chosen range), unless it says otherwise.

### A. Money in
1. **Collections**: receipts and amounts by day, week and month; by method
   (cash, card, EFT, later debit order); by cashier.
2. **Collected against expected**: the collection rate per month, per branch,
   per plan. The single most important number for a premium business.
3. **Ahead and behind**: how much of the month's money paid arrears, how much
   this month, how much in advance.
4. **Unmatched money**: receipts not yet tied to a policy (Feature 4, §8), and
   for how long. It should trend to zero.

### B. Money out
5. **Expenses** by category, branch and month (transport, flowers, tents and
   chairs, wages, electricity…), with the largest lines listed.
6. **Cash given out and reserved**: what is out, to whom, and what is still
   reserved and unspent.
7. **Banked and in the safe**: drops to the safe, banking, and the cash each
   branch should be holding now.

### C. Cash control
8. **Daily close**: per branch and cashier, expected against counted, the
   difference, and days not closed.
9. **Voids, reversals and reallocations**: how many, how much, by whom, with
   reasons. Patterns here are how cash going missing shows up.
10. **Receipt series check**: gaps, receipts outside office hours.

### D. Who is late, and who isn't paying
11. **Arrears ageing**: amount and count late 1–30, 31–60, 61–90 and 90+ days,
    per branch and plan.
12. **Call list**: every late family with the main member, phone, amount owed,
    months behind, last payment and its date. This is the existing Payments
    screen, extended; admins keep seeing it to phone families (Feature 4, D2).
13. **Not paying**: live policies with no money for 60+ days, and policies still
    `pending` 30+ days after enrolment with no first premium.
14. **At risk**: in grace and close to the lapse rule; the list to phone first.

### E. The book: growth and lapses
15. **Policies in force** at each month end: active, pending, lapsed; lives
    covered.
16. **New business**: new policies per month by branch, plan and the staff
    member who enrolled them; enquiries on the website that became policies
    (the funnel, already measurable through `policies.enquiry_id`).
17. **Lapses, cancellations and reinstatements** per month, and the **net
    growth** (new − lapsed − cancelled + reinstated).
18. **Persistency**: of the policies that started in a month, how many are
    still paying 3, 6, 12 and 13 months later. The standard measure of a book's
    health in funeral insurance.
19. **Monthly premium on the book**: the total monthly premium of active
    policies, its change month on month, and the average premium by plan.
20. **Age profile** of the lives covered, by plan: how many lives sit in each
    age band, and how many are over the plan's maximum entry age.

### F. Claims and funerals (later)
21. **Claims**: deaths reported, paid, declined, and time to pay; claims within
    the waiting period.
22. **Cost per funeral against cover**: what each funeral cost in cash-book
    lines (tents, flowers, transport, graves) against the cover paid.
23. **Loss ratio**: claims paid ÷ premiums collected, per plan.

These need a claims record that does not exist yet. They are listed so the
cash book's "for a family" link (Feature 4, §9) is captured from day one.

### G. Data quality and the work queue
24. **Open data-quality flags** by kind and branch, and how fast they are
    cleared (194 open on 15 Nov 2026).
25. **Book completeness**: policies without a plan, premium, start date, main
    member ID or phone; people without a phone, so they can't be reminded.

## 6. How it is built

- **Views, not copies.** Each report is a `security_invoker` SQL view over the
  tables of record, read by an owner-and-finance API router (`routers/reports.py`,
  `require_permission("finance.read")`). No figure is stored twice, so there is
  no second number to drift. The data is small (hundreds to a few thousand
  policies), so plain views on Supabase's free tier are enough; if one gets slow,
  make it a materialised view refreshed by the `jobs` cron.
- **Month-end snapshots** are the exception: "policies in force at the end of
  October" must not change when a status is corrected in December. The `jobs`
  cron writes one summary row per branch per plan per month (counts and cents,
  no names). It is append-only, and any correction is a new row.
- **Every figure reconciles.** Collected in A1 equals the sum of the daily
  closes in C8, which equals the receipts. A test asserts it on seeded data.
- **Grants**: each new view and table gets its `induduzo_api` grant written
  out. Nothing to `anon` or `authenticated` (CLAUDE.md).
- **Privacy**: aggregate reports carry no names. Lists that need names (the
  call list, unmatched receipts) sit on the portal only. Each view of a list
  writes a `staff_events` row, as the Payments screen does today. Exports are
  audited (R4). The monthly email has totals only.
- **Portal**: a Reports page with the period and branch at the top, a few
  headline numbers (collected, collection rate, late amount, net growth), then
  each section. Charts only where a trend matters (collections by month,
  policies in force, persistency); everything else is a table.

## 7. Build order

| Bit | What | Needs |
|---|---|---|
| F5.1 | Status history table; reports router behind `finance.read`; book reports from today's data: **15, 16, 20, 24, 25**, and arrears **11–13** from the instalments | Feature 4's permissions (F4.1–F4.2) |
| F5.2 | Money reports **1–10, 14** | Feature 4 live at a branch |
| F5.3 | Lapse and persistency **17–19**, month-end snapshots | Status history running for some months |
| F5.4 | Monthly email summary and CSV export | F5.2 |
| F5.5 | Claims and funeral costs **21–23** | A claims feature (not planned yet) |

## 8. Questions for the owner

| # | Question |
|---|---|
| Q1 | Who are the executives who should get `finance.read`? |
| Q2 | Any monthly targets per branch? |
| Q3 | "Not paying" at 60 days: right, or a different number? |
| Q4 | Are sales credited to a staff member or agent (commission)? The audit trail knows who typed an enrolment in, but not who sold it. If they can differ, enrolment needs a "sold by" field. |
| Q5 | Should the monthly summary go to anyone outside the portal, such as an accountant or a partner? |
