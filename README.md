# Induduzo Funeral Home

Public website, staff portal and API for Induduzo Funeral Home — a family-run
funeral parlour serving Pietermaritzburg and the KwaZulu-Natal Midlands since
1998.

| | Live at |
|---|---|
| Public site | https://induduzo.co.za (Netlify) |
| Staff portal | https://induduzohome.co.za (Netlify) |
| API | https://api.induduzo.co.za (Railway; production data in Supabase) |

---

## What it does

1. **Markets the funeral plans.** Four plans (A, B, C and the Dome Plan) with
   transparent pricing, full inclusions, and guaranteed payouts, in English and
   isiZulu.
2. **Captures prospective policyholders** through a deliberately two-stage form.
   Stage 1 asks only for contact details and commits immediately, so a person
   who abandons the longer stage 2 is still a lead the office can phone. Every
   submission emails the office and is stored in Postgres.
3. **Runs the book of business** in a separate staff portal: enquiries,
   enrolment, members and dependants, the premium schedule, payments and who is
   overdue. Staff sign in with a password and a second step (an emailed code or
   a trusted computer); roles are `viewer`, `admin` and `owner`.
4. **Answers the WhatsApp line**: a menu that replies at any hour, hands a family
   to a person when they ask, and sends registration confirmations and payment
   reminders from approved templates.

There is **no customer login and no payment processing**. See
[docs/Induduzo - Taking Payments Online.docx](docs/) for what taking payments
would require — the blocker is FSCA licensing, not technology.

---

## Quick start

Docker Desktop must be running. From the repo root:

**PowerShell**
```powershell
.\start.ps1
```

**Command Prompt**
```bash
induduzo.cmd
```

Either starts the database, API, website and staff portal, waits for each to report healthy, and prints
the URLs. Add `-Stop` to shut everything down; your data survives.

> cmd cannot execute a `.ps1` — typing `.\start.ps1` there opens it in Notepad,
> which is why the wrapper exists. It is named `induduzo.cmd` rather than
> `start.cmd` or `run.cmd` because `start` collides with a cmd built-in and nvm
> already puts a `run.cmd` on the PATH.

| | URL |
|---|---|
| Website | http://localhost:8080 |
| Registration | http://localhost:8080/register |
| Staff portal | http://localhost:8090 |
| API docs | http://localhost:8000/docs |
| API health | http://localhost:8000/health |
| pgAdmin (ERD, queries) | http://localhost:8082 |
| Adminer (quick look) | http://localhost:8081 |

---

## First-time setup

```powershell
# 1. Configuration
cp .env.example .env
cp backend/.env.example backend/.env

# 2. Frontend and portal dependencies
npm --prefix frontend ci
npm --prefix portal ci

# 3. Backend virtualenv — Python 3.12 specifically.
#    pydantic-core has no wheel for 3.14, which may be your default.
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt

# 4. Start
.\start.ps1
```

Neither `.env` is committed. The defaults in the examples are throwaway local
values — nothing in them is a production secret.

---

## Architecture

```
Visitor ─▶ Website (React) ──┐
Staff   ─▶ Portal  (React) ──┼─HTTP─▶  API (FastAPI)  ─SQL─▶  Postgres
Family  ─▶ WhatsApp (Twilio)─┘             ├──▶ Email    (office, staff codes)
                                           ├──▶ WhatsApp (confirmations, menu, reminders)
                                           └──▶ Supabase Auth (staff identity only)
```

| Path | What it is |
|---|---|
| `frontend/` | Public site: Vite + React + TypeScript + Tailwind |
| `portal/` | Staff portal: a separate Vite + React app, separate deploy |
| `backend/` | FastAPI, Python 3.12; scheduled jobs in `backend/app/jobs/` |
| `db/migrations/` | Versioned SQL. The schema source of truth. |
| `docs/` | Business and operational documents |

**→ [ARCHITECTURE.md](ARCHITECTURE.md) is the file-by-file map**: where every
feature lives, what happens when things fail, and the rules that must not be
broken. Read it before changing anything.

**→ [SECURITY.md](SECURITY.md)** is the security posture and pre-launch checklist.

---

## The registration flow

`/join` → **Register** → `/register` (stage 1) → `/register/details` (stage 2)

Stage 1 commits a row to `plan_enquiries` and emails the office the moment it is
submitted — before the person has decided whether to continue. Stage 2 patches
the same row and promotes it to `stage = 'application'`, then emails the full
application and sends the applicant a WhatsApp confirmation.

A notification failure never blocks a registration. Both mailers run after the
row is committed; if email or WhatsApp is unconfigured or down, the outcome is
logged to `enquiry_events` and the enquiry still succeeds.

---

## Notifications

Both are **off by default** and degrade to logging, so local development works
with no credentials and an outage never costs a lead.

**Email → the office.** Set `SMTP_*` and `MAIL_TO` in `backend/.env` locally,
or as Railway variables when deployed. Sent on both stages. The mailbox has to exist first — see
[docs/email-setup-plan.md](docs/email-setup-plan.md).

**WhatsApp → the applicant.** Set `TWILIO_*` and choose `WHATSAPP_OUTBOUND`
(`off` by default, `allowlist`, `known` or `on`). Production needs an approved
Content template, because a registration confirmation is business-initiated;
free-text bodies only work in the Twilio sandbox. See
[docs/twilio-setup.md](docs/twilio-setup.md).

Check what is live at any time:

```bash
curl http://localhost:8000/health
```

---

## Working with the data

**pgAdmin — http://localhost:8082.** No login; the *Induduzo (local)* server
connects on its own.

- **Schema diagram:** right-click the `induduzo` database → **ERD For Database**
- **Watch data arrive:** `induduzo` → Schemas → public → Tables →
  right-click `plan_enquiries` → View/Edit Data → All Rows, then submit the form
  in another tab and refresh
- **Query:** Tools → Query Tool

**Adminer — http://localhost:8081.** One page, faster for a quick look. Server
`db`, user `induduzo`, database `induduzo`, password from your `.env`.

Rebuild the schema from scratch (destroys local data):

```bash
docker compose down -v && docker compose up -d
```

---

## Running services individually

```powershell
docker compose up -d                                    # database + admin tools
cd backend; ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
npm --prefix frontend run dev                           # website on 8080
```

Postgres is on **5433**, not 5432 — this machine already runs another Postgres.
Inside the compose network it is still 5432.

---

## Before opening a PR

```powershell
cd frontend
npm run lint
npm run typecheck
npm run build
```

All three must exit `0`, and the same in `portal/`. CI also runs `npm audit`,
`pip-audit`, the API behaviour checks against a throwaway Postgres, and a build
of `Dockerfile.backend`. If you changed the
schema, verify `docker compose down -v && docker compose up -d` rebuilds cleanly
and re-run the registration flow end to end.

---

## Deployment

Everything is live since 12 Nov 2026. Branches promote
`feature -> Dev -> internal -> main`; `internal` deploys the test environment on
Railway, `main` deploys production.

| Part | Where | Config |
|---|---|---|
| Public site | Netlify, from `frontend/` | `netlify.toml` (security headers, CSP) |
| Staff portal | Netlify, from `portal/` | `portal/netlify.toml` |
| API, migrator, daily `jobs` cron | Railway, `live` environment | `Dockerfile.backend`, Railway variables |
| Database and staff sign-in | Supabase (Free plan) | `db/migrations/`, applied by the migrator |

Runbooks: [docs/deployment-runbook.md](docs/deployment-runbook.md) for the site,
[docs/railway-backend-deployment.md](docs/railway-backend-deployment.md) for the
API, and [docs/railway-internal-setup-explained.md](docs/railway-internal-setup-explained.md)
for the internal environment.
