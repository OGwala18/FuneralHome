# Induduzo Funeral Home

Public website and plan-registration system for Induduzo Funeral Home — a
family-run funeral parlour serving Pietermaritzburg and the KwaZulu-Natal
Midlands since the 1980s.

**Live site:** https://induduzo.co.za

---

## What it does

Two things:

1. **Markets the funeral plans.** Four plans (A, B, C and the Dome Plan) with
   transparent pricing, full inclusions, and guaranteed payouts, in English and
   isiZulu.
2. **Captures prospective policyholders** through a deliberately two-stage form.
   Stage 1 asks only for contact details and commits immediately, so a person
   who abandons the longer stage 2 is still a lead the office can phone. Every
   submission emails the office and is stored in Postgres.

There is **no customer portal, no login and no payment processing** yet. See
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

Either starts all three services, waits for each to report healthy, and prints
the URLs. Add `-Stop` to shut everything down; your data survives.

> cmd cannot execute a `.ps1` — typing `.\start.ps1` there opens it in Notepad,
> which is why the wrapper exists. It is named `induduzo.cmd` rather than
> `start.cmd` or `run.cmd` because `start` collides with a cmd built-in and nvm
> already puts a `run.cmd` on the PATH.

| | URL |
|---|---|
| Website | http://localhost:8080 |
| Registration | http://localhost:8080/register |
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

# 2. Frontend dependencies
npm --prefix frontend ci

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
Visitor ─▶ Website (React)  ─HTTP─▶  API (FastAPI)  ─SQL─▶  Postgres
                                          ├──▶ Email  (office notification)
                                          └──▶ WhatsApp (applicant confirmation)
```

| Path | What it is |
|---|---|
| `frontend/` | Vite + React + TypeScript + Tailwind |
| `backend/` | FastAPI, Python 3.12 |
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

**Email → the office.** Set `SMTP_*` and `MAIL_TO` in `backend/.env`. Sent on
both stages. The mailbox has to exist first — see
[docs/email-setup-plan.md](docs/email-setup-plan.md).

**WhatsApp → the applicant.** Set `TWILIO_*` in `backend/.env`. Production needs
an approved Content template, because a registration confirmation is
business-initiated; free-text bodies only work in the Twilio sandbox.

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

All three must exit `0`. CI runs the same plus `npm audit`. If you changed the
schema, verify `docker compose down -v && docker compose up -d` rebuilds cleanly
and re-run the registration flow end to end.

---

## Deployment

Production is Netlify, building `frontend/` and publishing `dist/`. Security
headers (CSP, HSTS, anti-framing, MIME-sniffing, referrer, permissions) are set
in `netlify.toml`. The full runbook is
[docs/deployment-runbook.md](docs/deployment-runbook.md).

> The **API and database are not yet deployed.** Only the static site is live.
> The registration form needs a hosted API before it works in production.
