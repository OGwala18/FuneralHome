# Induduzo Funeral Home

One repo: public website, API, and database migrations. The database runs as a
separate service (local Docker for now).

> File structure is deliberately provisional — a proper restructure is a later
> step. What matters now is that the layers are separated and the database
> decisions are right, because those are the expensive ones to change late.

## Layout

| Path | What it is |
|---|---|
| `induduzo-care-site-main/` | Public website — Vite + React + TypeScript + Tailwind |
| `backend/` | API — FastAPI (Python 3.12) |
| `db/migrations/` | Versioned SQL migrations. **The source of truth for the schema.** |
| `docs/` | Written deliverables |
| `docker-compose.yml` | Local Postgres + Adminer |

## Running it

Three services. Start them in this order.

**1. Database** (Docker Desktop must be running)

```bash
docker compose up -d db
```

Postgres on `localhost:5433` — port 5433, not 5432, because this machine
already runs an `aistack-postgres` on 5432. Migrations in `db/migrations/`
apply automatically on first run of an empty volume, in filename order.

Browse the tables at http://localhost:8081 (Adminer): system `PostgreSQL`,
server `db`, user `induduzo`, password `induduzo_local_dev`, database `induduzo`.

To rebuild the schema from scratch:

```bash
docker compose down -v && docker compose up -d db
```

**2. API**

```bash
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Health check at http://localhost:8000/health, interactive docs at
http://localhost:8000/docs.

Python 3.12 specifically — `pydantic-core` has no wheel for 3.14, which is this
machine's default. The venv is already built against 3.12.

**3. Website**

```bash
npm --prefix induduzo-care-site-main run dev
```

http://localhost:8080

## The registration flow

`/join` → **Register** → `/register` (stage 1) → `/register/details` (stage 2)

Stage 1 commits a row to `plan_enquiries` the moment it is submitted. That is
the whole point of the split: if someone abandons stage 2, the lead is still
captured and followable-up. Stage 2 patches the same row and promotes it to
`stage = 'application'`.

## Things that are true on purpose

- **No bank or card details are stored anywhere.** Not in the forms, not in the
  database. Payment collection is delegated to a provider — see
  `docs/Induduzo - Taking Payments Online.docx`.
- **`enquiry_events` is append-only**, enforced by Postgres rules. UPDATE and
  DELETE against it are silently no-ops.
- **RLS is on.** The public role can INSERT and nothing else; a leaked public
  key cannot read anyone's details back out.
- **Money is integer cents** with an explicit currency column, never a float.
- **Consent is explicit.** `contact_consent` is a database-level requirement for
  an application to exist, and marketing consent is a separate opt-in.

Schema conventions follow `AIA/foundations/03-database-foundations.md`; the
column set maps onto `data-to-knowledge/domains/funeral_policy.yaml` so these
rows can fan out into the policy/member warehouse tables later.

## WhatsApp confirmations

Off by default. With no Twilio credentials the API logs what it *would* send and
the registration still succeeds — a messaging outage must never cost a lead.

To enable, fill `backend/.env`. Note that a registration confirmation is
*business-initiated*, so production requires an approved WhatsApp Content
template (`TWILIO_CONTENT_SID`); free-text bodies only work in the Twilio sandbox.
