# Feature 1 — The review and insight loop

**Working brief for an agent picking this up cold.**
Read `ARCHITECTURE.md` first. It says where everything lives and which rules must not be
broken. This file says what to add, in what order, and what not to rebuild.

| | |
|---|---|
| Status | Not started |
| Priority | Launch feature. Nothing ships without it |
| Repo state at time of writing | `0cbafb6` |
| Touches | `backend/`, `db/migrations/`, `portal/`, `frontend/` |

---

## 1. What this feature is

Today the system stops listening the moment a person joins. A lead is captured, the row
lands, the office gets an email and the applicant gets a WhatsApp confirmation. After that
nothing asks them anything and nothing comes back.

Feature 1 closes that circle. It asks the member how their cover is doing, listens for what
they say publicly, stores it, and puts it in front of both staff and prospects.

Four phases: **capture, ask, listen, show.** Capture already works. The other three are the
build.

---

## 2. The system this plugs into

```
                 CLIENTS
   ┌────────────────────┐              ┌────────────────────┐
   │   Public Website   │              │    Staff Portal    │
   │   frontend/        │              │    portal/         │
   │   induduzo.co.za   │              │    portal.induduzo │
   └─────────┬──────────┘              └─────────┬──────────┘
             │ POST /api/enquiries                │ GET /api/admin/*
             │ PATCH /{id}/application            │ token verified per request
             └──────────────┬─────────────────────┘
                            ▼
                 SERVICE LAYER
 ┌──────────────┐  ┌──────────────────────────┐  ┌──────────────┐
 │ THIRD PARTY  │  │      Backend API         │  │ Supabase Auth│
 │ Meta Graph   │─▶│      backend/app         │◀─│ identity only│
 │ Google GBP   │─▶│  the only thing that     │  │ no client data│
 │ Twilio WA    │◀─│  holds a secret, calls   │  └──────────────┘
 │ SMTP         │◀─│  out, or touches the DB  │
 └──────────────┘  └────────────┬─────────────┘
                                │ writes / reads
                                ▼
                 DATA
                   ┌──────────────────────────┐
                   │        Postgres          │
                   │  plan_enquiries          │
                   │  enquiry_events          │
                   │  staff_users             │
                   │  staff_events            │
                   └──────────────────────────┘
```

Two things about this drawing matter for Feature 1:

1. **Social and review APIs terminate at the backend.** They never touch the staff portal.
   The portal holds no credentials for anything except signing a person in, and a browser
   must never hold a Google or Meta token. The portal reads numbers the API has already
   decided to keep.
2. **The backend is the only writer.** Page views, review text, ratings: all of it arrives
   through the API and is written by the API. There is no path from a browser to the
   database.

---

## 3. The loop, step by step

`[built]` already runs in production. `[new]` is this feature.

```
  MEMBER      WEBSITE        API          POSTGRES      WA / GOOGLE     PORTAL

CAPTURE
  1 ─────────▶                                                              [built]
     completes the join form
  2            ─────────────▶                                               [built]
                POST /api/enquiries, PATCH /{id}/application
  3                         ────────────▶                                   [built]
                             INSERT plan_enquiries + enquiry_events

ASK
  4                         ───────────────────────────▶                    [new]
                             scheduled job sends an approved template:
                             "how did we do, and is your cover still right?"
  5 ◀────────────────────────────────────────────────                       [new]
     member receives the message, with a review link

LISTEN
  6 ─────────────────────────────────────────────────▶                      [new]
     leaves a Google review, or browses the site
  7                         ◀╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌                       [new]
                             scheduled pull every few hours:
                             rating, review text, views, sentiment
  8                         ────────────▶                                   [new]
                             INSERT feedback_responses + insight_snapshots

SHOW
  9                         ◀────────────                                   [new]
                             SELECT daily rollups: signups, active, rating
 10                         ──────────────────────────────────────────▶     [new]
                             GET /api/admin/analytics
 11            ◀────────────                                                [new]
                rating badge and approved testimonials, from the database
```

Steps 4 and 7 are not triggered by anyone clicking anything. That is why the first build
item is a scheduler, not an integration.

---

## 4. What already exists — do not rebuild it

| Piece | Where |
|---|---|
| Two-stage funnel, stage 1 commits and notifies immediately | `frontend/src/pages/Register.tsx`, `RegisterDetails.tsx` |
| `POST /api/enquiries`, `PATCH /api/enquiries/{id}/application` | `backend/app/routers/enquiries.py` |
| `plan_enquiries`, `enquiry_events` (append-only, enforced by DB rule) | `db/migrations/0003`, `0004` |
| Twilio WhatsApp send path, failures swallowed after commit | `backend/app/services/whatsapp.py` |
| SMTP office notification on both stages | `backend/app/services/email.py` |
| Staff sign-in: Supabase token verified against JWKS, then `staff_users` | `backend/app/auth.py`, `routers/admin.py` |
| Enquiry list, searchable, sortable, paginated | `GET /api/admin/enquiries`, `portal/src/pages/Enquiries.tsx` |
| Staff and role management with last-owner guard | `GET·POST·PATCH /api/admin/staff`, `portal/src/pages/Staff.tsx` |

**"Who is still a member"** is already modelled. `enquiry_status` has an `active` value.
Analytics should count that enum, not invent a parallel notion of membership.

---

## 5. What Feature 1 adds

| Piece | Today | Feature 1 |
|---|---|---|
| Scheduler | Nothing in the repo runs on a clock | Runs the review sends and the Google pull |
| Review request | One approved WhatsApp template, registration confirmation only | A second approved template asking for a review |
| Google Business Profile | None | Read rating, review text, view counts |
| Site analytics | None | Page views captured through the API |
| Feedback store | None | `feedback_responses`, `insight_snapshots` |
| Portal analytics | None | `GET /api/admin/analytics`: signups, active members, rating trend |
| Public testimonials | Static file, `frontend/src/data/testimonials.json` | Approved reviews served from Postgres |
| Meta Graph API | None | Post and page insights. Can slip to phase 2, see §10 |

---

## 6. Build order

Each step unblocks the next. Do not start at the integrations.

### 1. Schema first — migration `0013`

> Corrected 14 September 2026: this said `0008`, which was free when the brief
> was written. `0008`–`0012` now exist (reference tables, people, policies, data
> quality flags, FK indexes). Migrations are forward-only, so the next free
> number is **`0013`**.

Add `feedback_responses` and `insight_snapshots`. Both carry the standard skeleton from
foundation 03 §5.1: `id`, `tenant_id`, `created_at`, `updated_at`, `archived_at`. Both get
row level security and an `api_rw_*` policy matching `0005`. `feedback_responses` references
`plan_enquiries(id)` where the feedback came from a known member, and allows NULL where it
came from an anonymous public review.

Migrations are forward-only. Add the file, never edit an applied one.

**Done when:** `docker compose down -v && docker compose up -d` rebuilds clean and the new
tables exist with policies attached.

### 2. The scheduler

The only new infrastructure. Two jobs:

- `send_due_review_requests()` — find members eligible for a review ask, send, record.
- `pull_external_insights()` — fetch Google readings, write snapshots.

Both must be idempotent. A job that runs twice must not send two messages or write two
snapshots for the same window. Use a claim column or a unique index on
`(enquiry_id, template, sent_date)`, not an in-memory flag.

**Done when:** a job can be triggered manually in dev, runs, writes an event, and running it
again immediately is a no-op.

### 3. The second WhatsApp template

A business-initiated message outside the 24 hour window must be a pre-approved Content
template. The existing `TWILIO_CONTENT_SID` is the registration confirmation and cannot be
reused for this. Register a second template and add a second content SID to `config.py`.

**Start the Meta approval before writing any code. It is the long pole.**

The send path is a small addition to `services/whatsapp.py`, which already returns a result
object rather than raising, so a messaging failure degrades to a logged event.

**Done when:** the template is approved, the SID is in the environment, and a send writes a
`review_requested` row to `enquiry_events`.

### 4. The Google reader

A new module beside the other services, `services/insights.py`. Called only by the
scheduler, never by a request handler. It writes snapshots and serves nothing, so a Google
outage degrades a chart rather than breaking the portal.

**Done when:** a scheduled run writes a snapshot row, and a forced failure leaves the portal
fully usable.

### 5. The two read paths

- `GET /api/admin/analytics` on the existing admin router, so it inherits
  `Depends(require_staff)` automatically. Returns rollups: signups over time, active member
  count, rating trend, review volume. Never raw rows.
- A small public endpoint for the rating badge and approved testimonials. Public, cached,
  and it must only ever return reviews explicitly marked approved.

Then swap `frontend/src/data/testimonials.json` for the API, and add the analytics view to
the portal.

**Done when:** the portal dashboard renders from real rollups and the public site shows a
live rating rather than a static file.

---

## 7. Rules that must not be broken

Everything in `ARCHITECTURE.md` §7 still applies. These are the ones this feature is most
likely to trip over:

1. **Personal data never goes into logs.** Review text is personal data. Log the reference,
   `IND-2026-001234`, never what somebody wrote about their mother's funeral.
2. **Consent is not transitive.** `contact_consent` and `marketing_consent` are separate
   columns for a reason and marketing consent must never be implied by the first. See §10:
   which one gates a review request is an open decision, not an assumption to make quietly.
3. **Notification failure must never cost a lead.** Same rule as the existing mailers. The
   review job runs after commit and swallows its own failures.
4. **`VITE_*` is public.** No Google or Meta credential goes anywhere near either front end.
5. **Append-only means append-only.** If feedback gets an event trail, it gets the same
   `do instead nothing` rules as `enquiry_events`.
6. **Read rollups, not rows.** The dashboard must stay fast as the feedback table grows.

---

## 8. Open decisions

These need Onke before or during the build. Do not guess.

1. **Which consent gates a review request?** A review ask is arguably marketing. If it needs
   `marketing_consent`, the eligible population is smaller and the join form may need to
   make that opt-in clearer.
2. **When is the ask sent?** Days after `application_submitted`, or after a service is
   actually delivered? The schema has no notion of a delivered service yet, so the second
   option needs more modelling.
3. **Where does the review land?** A Google review link, an on-site form, or a WhatsApp
   reply captured by webhook. Each has a different build cost and a different data path.
4. **Who approves a review before it appears publicly?** Suggest an `approved_by` column and
   a portal action, since unmoderated review text on a funeral home's own site is a risk.
5. **Where does the scheduler run?** Railway cron, an in-process scheduler in the API, or
   Supabase `pg_cron`. Affects deployment and the runbook.
6. **Is Meta in scope for launch?** Google Business Profile carries the rating and the
   reviews. Meta carries post reach. If launch only needs the rating trend, Meta can slip to
   phase 2 and cut a whole OAuth integration out of the critical path.

---

## 9. First commands

```powershell
cd frontend
npm run lint
npm run typecheck
npm run build
```

All three must exit 0 before a PR. CI runs the same, plus `npm audit`. If the schema was
touched, also confirm a clean rebuild and re-run the registration flow end to end.

Commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.
