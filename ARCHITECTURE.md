# Architecture & File Map

**Read this before changing anything.** It says where every feature lives, what
each file is responsible for, and which rules must not be broken. It is written
for a developer or an AI agent arriving with no prior context.

If you only read one thing, read [Rules that must not be broken](#rules-that-must-not-be-broken).

---

## 1. What this system is

A public marketing website for a South African funeral home, plus a two-stage
registration funnel that captures prospective policyholders into a Postgres
database and notifies the office by email.

There is **no customer portal, no login, and no payment processing**. Those are
future work. Anything that looks like auth or payments does not exist yet — do
not assume it does.

```
Visitor ─▶ Website (React)  ─HTTP─▶  API (FastAPI)  ─SQL─▶  Postgres
                                          │
                                          ├──▶ Email  (office notification)
                                          └──▶ WhatsApp (applicant confirmation)
```

Three processes, one repo. The database is a separate service reached only by a
connection string.

---

## 2. Top-level layout

```
FuneralHome/
├── README.md                  Start here: what it is, how to run it
├── ARCHITECTURE.md            This file: where things live, what the rules are
├── SECURITY.md                Security posture and pre-launch checklist
│
├── frontend/                  Public website — Vite + React + TypeScript + Tailwind
├── portal/                    Staff portal — separate app, never deployed with the site
├── backend/                   API — FastAPI (Python 3.12)
├── db/                        Database migrations and admin tooling
├── docs/                      Business and operational documents
│
├── docker-compose.yml         Local Postgres + Adminer + pgAdmin
├── start.ps1 / induduzo.cmd   One-command start/stop for the whole stack
├── netlify.toml               Production hosting config + security headers
├── .env.example               Infrastructure settings template
└── .github/workflows/         CI: lint, typecheck, build, audit
```

**Rule:** the repo root holds only entry points and configuration. Business
documents go in `docs/`. Nothing generated (`node_modules`, `.venv`, `dist`,
`logs`) is ever committed — see `.gitignore`.

---

## 3. Frontend — `frontend/`

```
frontend/
├── index.html                 HTML shell. Sets the light-only colour scheme.
├── netlify-adjacent config    vite.config.ts, tailwind.config.ts, tsconfig*.json
├── public/                    Static assets copied verbatim into dist/
└── src/
    ├── App.tsx                ROUTER. Every page URL is registered here.
    ├── main.tsx               React entry point
    ├── index.css              DESIGN TOKENS. All colours live here, nowhere else.
    │
    ├── pages/                 One file per route
    │   ├── Home.tsx           /
    │   ├── About.tsx          /about
    │   ├── Services.tsx       /services
    │   ├── Join.tsx           /join          ← plan comparison + Register button
    │   ├── Register.tsx       /register      ← STAGE 1 of the funnel
    │   ├── RegisterDetails.tsx /register/details ← STAGE 2 of the funnel
    │   ├── Contact.tsx        /contact
    │   ├── Gallery.tsx        /gallery
    │   ├── Testimonials.tsx   /testimonials
    │   ├── Founder.tsx        /founder
    │   └── NotFound.tsx       fallback
    │
    ├── components/
    │   ├── Header.tsx         Nav, language switch, call + social icons
    │   ├── Footer.tsx         Contact details, quick links, map
    │   ├── OfficeMap.tsx      Address link + embedded Google map
    │   ├── WhatsAppButton.tsx Floating action button
    │   ├── form/Field.tsx     Accessible field wrapper + step indicator
    │   ├── layout/            Page shell
    │   └── ui/                shadcn/ui primitives — VENDORED, avoid editing
    │
    ├── data/
    │   ├── plans.ts           ★ SINGLE SOURCE OF TRUTH for plans and prices
    │   ├── founder.json       Founder page content
    │   ├── gallery.json       Gallery items
    │   └── testimonials.json  Testimonials
    │
    └── lib/
        ├── contact.ts         ★ Phone numbers, email, socials. Change them ONLY here.
        ├── i18n.ts            English / isiZulu strings
        ├── location.ts        ★ Office address, map link and embed URL
        ├── navigation.ts      Tiny custom router (NavLink, usePathname)
        └── registration.ts    API client + SA ID / mobile validation
```

### Where do I change…?

| I want to change | Edit this |
|---|---|
| A plan's price, name, or inclusions | `src/data/plans.ts` — nothing else |
| A phone number, the public email, or a social link | `src/lib/contact.ts` — nothing else |
| The office address or where the map points | `src/lib/location.ts` — nothing else |
| Any colour | `src/index.css` tokens — never hard-code a hex in a component |
| Page text / translations | `src/lib/i18n.ts` |
| Add a page | Create in `src/pages/`, then register the route in `src/App.tsx` |
| Registration form fields | `src/pages/Register.tsx` (stage 1) or `RegisterDetails.tsx` (stage 2) — **and** the API schema and a DB migration |

---

## 4. Backend — `backend/`

```
backend/
├── requirements.txt           Pinned dependencies
├── .env.example               Settings template (copy to .env)
└── app/
    ├── main.py                App setup, CORS, /health, error shaping
    ├── config.py              ★ ALL settings read from environment. No secrets in code.
    ├── db.py                  Connection pool + append-only event logging
    ├── schemas.py             ★ Request validation. The security boundary.
    ├── routers/
    │   └── enquiries.py       The two funnel endpoints
    └── services/
        ├── email.py           Office notification (both stages)
        └── whatsapp.py        Applicant confirmation (Twilio)
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + a real database round-trip |
| `POST` | `/api/enquiries` | **Stage 1.** Creates the lead, emails the office |
| `PATCH` | `/api/enquiries/{id}/application` | **Stage 2.** Promotes to full application |

Interactive docs run at `/docs` in development.

---

## 4a. Staff portal — `portal/`

An internal tool for employees to view client enquiries. **A separate Vite app
on purpose**: the public website must never ship admin code, so a bug in the
marketing site cannot expose client records. Different build, different deploy,
different domain (`portal.induduzo.co.za`).

```
portal/
├── .env.example               VITE_* only. Everything here is PUBLIC.
└── src/
    ├── App.tsx                Sign-in gate, then the portal shell and routes.
    ├── index.css              Plain CSS; no Tailwind toolchain to maintain.
    │                          Holds the design tokens. See docs/DESIGN.md.
    ├── components/
    │   ├── PortalNav.tsx      The one navigation. Five destinations.
    │   └── ui.tsx             Button, Badge, Field, Notice, Fact, Skeleton, Empty.
    ├── lib/
    │   ├── supabase.ts        Auth client. AUTHENTICATION ONLY, no data.
    │   ├── api.ts             Calls our API with the staff token attached.
    │   ├── router.ts          ~40 lines of history API. Real URLs, no dependency.
    │   ├── useEnquiries.ts    One race-guarded fetch, shared by four pages.
    │   └── derive.ts          Queue grouping and growth tallies. Invents nothing.
    └── pages/
        ├── Login.tsx          Email + password. No sign-up link, deliberately.
        ├── Today.tsx          Call desk: prioritised queue and the next person.
        ├── People.tsx         Searchable, sortable, paginated directory.
        ├── Person.tsx         One family's record.
        ├── Applications.tsx   Enquiries that reached stage 'application'.
        ├── Growth.tsx         Counts derived from the loaded enquiries.
        ├── Settings.tsx       Your account, plus team and access for owners.
        └── Staff.tsx          Staff table and invite form. Owners only.
```

### What the portal deliberately does not do

The Figma design covers 39 screens; the portal builds the ones the API can
actually serve. These are **not** built, because there is no endpoint behind
them and a control that silently does nothing is worse than no control:

| Missing | Needs |
|---|---|
| Recording a call outcome | `POST /api/admin/enquiries/{id}/outcome` |
| Editing an enquiry | An update route on the admin router |
| Call history on a record | `enquiry_events` exposed through the admin API |
| Fetching one person directly | `GET /api/admin/enquiries/{id}`. Person.tsx currently finds its row inside a page of the list endpoint. |
| Office details, integrations | Nothing in the schema or API supports them |

Growth counts what it loaded and says so on screen, rather than presenting a
figure that looks like an all-time total.

### Deploying the portal, now that it has routes

The portal uses the history API, so `/people/<id>` is a real URL that can be
bookmarked and shared. Vite's dev server already falls back to `index.html`;
**a static host will 404 on those paths unless it is told to do the same.** On
Netlify that is a redirect rule for the portal site:

```
/*  /index.html  200
```

Without it, only the root path loads and every deep link breaks.

### How sign-in works, and where the boundary actually is

```
Employee ─▶ Portal ─▶ Supabase Auth        (issues a signed ES256 token)
                 │
                 └─▶ Our API  ── verifies the signature against Supabase's
                                  PUBLIC key, then checks the email against
                                  STAFF_EMAILS ──▶ Postgres
```

Supabase stores no client data. It only proves who someone is. Client records
stay in our own Postgres.

**Two gates, because one is not enough.** A valid Supabase token only proves
somebody signed up somewhere; it does not prove they work here. So the API
additionally looks the person up in `staff_users` and requires an active row.
Public sign-up should also be turned off in the Supabase dashboard.

### Roles

| Role | May do |
|---|---|
| `viewer` | View enquiries |
| `admin` | View and edit enquiries |
| `owner` | Everything, plus add staff and change roles |

Roles live in **our** `staff_users` table, not in Supabase user metadata, so a
role change is an ordinary row we can audit, back up and restore — and a
compromised Supabase project cannot grant itself privileges here.

Enforced with `Depends(require_role("owner"))` on the route, so the privilege a
route needs is visible in its signature. Two safeguards worth knowing:

* **You cannot remove the last owner.** Demoting or deactivating the final
  active owner is refused, because it would leave nobody able to manage staff.
* **You cannot deactivate yourself**, which would lock you out mid-session.

**Bootstrap:** if `staff_users` is empty, the addresses in `STAFF_EMAILS` become
owners on first sign-in. Without that a fresh deployment would have a staff
table nobody could add themselves to — a locked door with the key inside. Once
any staff row exists the env list is ignored entirely.

Staff changes are written to `staff_events`, which is append-only at the
database level, separate from the enquiry log because they are security events.

The sign-in screen in `App.tsx` is a **convenience, not a security boundary**.
Hiding a screen protects nothing: the API re-verifies the token and the
allowlist on every single request. Auth is declared on the router
(`dependencies=[Depends(require_staff)]`) so a newly added admin route cannot
accidentally ship unprotected.

There is no shared secret anywhere in this flow. Supabase signs with a private
key we never hold; we verify with the public key from its JWKS endpoint.

---

## 5. Database — `db/`

```
db/
├── migrations/                ★ THE SCHEMA SOURCE OF TRUTH. Applied in filename order.
│   ├── 0001_extensions_and_roles.sql
│   ├── 0002_enums.sql
│   ├── 0003_plan_enquiries.sql
│   ├── 0004_rls_and_audit.sql
│   ├── 0005_api_role.sql
│   ├── 0006_local_api_password.sh   (local Docker only; the runner skips .sh)
│   ├── 0007_staff_users.sql
│   ├── 0008_reference_tables.sql
│   ├── 0009_people_and_contacts.sql
│   ├── 0010_policies.sql
│   ├── 0011_data_quality_and_enquiry_link.sql
│   └── 0012_foreign_key_indexes.sql
├── seed/                      Import tooling. Scripts tracked, their data is NOT.
│   ├── import_policy_template.py       spreadsheet  → SQL
│   ├── export_phone_capture_sheet.sql  database     → blank capture sheet
│   └── load_phone_numbers.py           filled sheet → SQL
└── pgadmin/servers.json       Pre-configured pgAdmin connection (no credentials)
```

### The two halves, and why they are separate

The website and the book of business are different shapes, and the schema says
so rather than forcing one into the other.

**Capture (0003–0004, 0007).** One wide row per form submission.

- **`plan_enquiries`** — one row per person who filled in the form. Stage 1
  fills the contact columns; stage 2 fills the rest. `stage` (`lead` /
  `application`) and `status` are deliberately separate axes: a record can be a
  `lead` that has been `contacted` without ever becoming an application. It is
  wide on purpose — a submission log should record what was typed and not be
  rewritten afterwards.
- **`enquiry_events`** — append-only audit trail. UPDATE and DELETE are blocked
  by Postgres rules, not by convention.
- **`staff_users` / `staff_events`** — who may use the portal, and an
  append-only log of changes to that.

**Book of business (0008–0012).** Normalised, because the same human being
appears on several policies and a premium is not a property of whichever
relative was typed first.

*Reference tables* — small, slow-changing, primary key is a readable text code
so that an export says `main_member` rather than a uuid, and so moving data
between environments needs no id remapping: `ref_member_types`,
`ref_policy_statuses`, `ref_plans`, `ref_branches`, `ref_benefit_types`.

*Core tables* —

- **`people`** — one row per human being. The single identity everything else
  points at. `id_number_status` records how far a supplied ID number can be
  trusted instead of pretending they are all clean.
- **`person_phones`** — E.164, many per person, indexed on the number itself
  because the office's real query is the reverse one: an unknown number rings,
  who is this?
- **`addresses`** — residential and postal, many per person.
- **`policies`** — number, dates, money in integer cents, product, branch.
  Carries `enquiry_id`, so a policy that began as a website lead stays linked
  to it and the funnel can be measured end to end.
- **`policy_members`** — the junction. Which people are covered by which
  policy and in what role. A partial unique index enforces one main member per
  policy, a rule the spreadsheet could not express at all.
- **`policy_benefits`**, **`policy_links`** — supplementary cover, and the
  master/child hierarchy for group schemes.
- **`policy_payments`** — how a policy is collected. **No account number, bank,
  branch code or card data**, by design. See SECURITY.md.
- **`data_quality_flags`** — a work queue, not an error log. Imported data
  arrives imperfect; each known problem becomes a task the office clears
  against the paper application, rather than being silently "fixed".
- **`policy_overview`** — a `security_invoker` view with the main member and
  their primary phone already joined, so screens do not each rewrite that join.

`plan_enquiries.person_id` is the seam between the two halves: null until a
lead has been matched to a person.

**Migrations are forward-only and immutable once run.** To change the schema,
add `0013_*.sql`; never edit an applied file. They auto-apply on the first run
of an empty volume — `docker compose down -v && docker compose up -d` rebuilds
from scratch.

> **Supabase is tracked separately.** 0008–0012 were applied to Supabase through
> its own migration system, so `public.schema_migrations` (what `db/migrate.py`
> reads) does not know about them there. Before running `db/migrate.py` against
> Supabase, baseline it — `python db/migrate.py --baseline 0012_foreign_key_indexes.sql`
> — or it will try to re-run everything and fail on the first `create type`.
> Note that 0005 and 0007 have **not** been applied to Supabase: there is no
> `induduzo_api` role and no `staff_users` table there yet. Every migration from
> 0008 on guards its grants with a `pg_roles` check for exactly this reason.

---

## 6. The registration funnel (the core feature)

```
/join  ──Register──▶  /register            ──▶  /register/details      ──▶  success
                      STAGE 1                    STAGE 2
                      POST /api/enquiries        PATCH .../application
                      │                          │
                      ├─ row committed           ├─ same row promoted
                      ├─ event: lead_captured    ├─ event: application_submitted
                      └─ EMAIL to office         ├─ EMAIL to office
                                                 └─ WhatsApp to applicant
```

**Why it is split, and why this must not be "simplified":** stage 1 commits and
notifies immediately, so a person who abandons stage 2 is still a captured,
contactable lead. Merging the two forms would silently lose every incomplete
enquiry — the exact people most worth phoning.

The stage-1 row id is held in `sessionStorage` so a refresh between steps does
not lose the thread, and is cleared once stage 2 succeeds.

### What happens when things fail

| Situation | Behaviour |
|---|---|
| API unreachable from the browser | Form shows a message with call/WhatsApp fallbacks. Nothing is lost silently. |
| Email not configured or failing | Logged, event recorded, **enquiry still succeeds** |
| WhatsApp not configured or failing | Logged, event recorded, **enquiry still succeeds** |
| Duplicate SA ID on stage 2 | `409` with a "phone us" message — the unique index caught it |
| Invalid input | `422` with `field_errors` keyed by field, so the form highlights the right input |

The principle: **a notification failure must never cost a lead.** Both mailers
run as background tasks *after* the row is committed, never before.

---

## 7. Rules that must not be broken

1. **No secrets in code or in the repo.** Everything sensitive comes from the
   environment via `backend/app/config.py`. `.env` is gitignored; `.env.example`
   is the committed template and must never hold a real credential.
2. **No bank or card details, ever.** Not in the forms, not in the schema, not
   in logs. Payment collection is delegated to a provider.
3. **The browser is hostile.** `schemas.py` revalidates everything. Client-side
   validation in `registration.ts` is a courtesy for the user, never a control.
4. **`enquiry_events` is append-only.** Enforced by database rules.
5. **Consent is required.** `contact_consent` gates row creation at the database
   level. Marketing consent is separate and must never be implied by it.
6. **Money is integer cents** with an explicit currency. Never a float.
7. **Migrations are forward-only.** Add a new file; never edit an applied one.
8. **Colours come from tokens** in `index.css`. The site is light-only — there
   is no dark mode and no theme switching.
9. **Personal data never goes into logs.** Log references (`IND-2026-001234`),
   not names, numbers or ID numbers.
10. **`VITE_*` variables are public.** They are compiled into browser JavaScript.
    Never put a secret in one.

---

## 8. Conventions

- **Frontend:** TypeScript throughout. Tailwind utilities, no bespoke CSS files.
  Functional components. Semantic tokens (`bg-card`, `text-muted-foreground`)
  rather than raw colours.
- **Backend:** Pydantic models for every request. Type hints throughout.
  Services return result objects rather than raising, so a failed notification
  cannot break a request.
- **Database:** `snake_case`, plural table names, `timestamptz` (never naive),
  real Postgres enums, foreign keys always declared and indexed.
- **Commits:** conventional prefixes (`feat:`, `fix:`, `docs:`, `chore:`).

---

## 9. Before you open a PR

```powershell
cd frontend
npm run lint
npm run typecheck
npm run build
```

All three must exit `0`. CI (`.github/workflows/quality-checks.yml`) runs the
same, plus `npm audit`.

If you touched the schema, also confirm a clean rebuild works:

```powershell
docker compose down -v
docker compose up -d
```

Then re-run the registration flow end to end and confirm the row lands.
