# CLAUDE.md — Induduzo Funeral Home

Read `ARCHITECTURE.md` before changing anything. It is the file map and the rule
book. This file is the short version plus the decisions that are not obvious
from the code.

## What this is

A funeral policy business in Pietermaritzburg. Two separate front ends and one
API:

| | |
|---|---|
| `frontend/` | Public site, `induduzo.co.za`. Captures enquiries. **Live on Netlify.** |
| `portal/` | Staff portal, `portal.induduzo.co.za`. Separate app, separate deploy. **Never bundled with the public site.** |
| `backend/` | FastAPI. The only thing that holds a secret, calls out, or touches the database. |
| `db/` | Migrations (the schema source of truth), the migration runner, and import tooling. |

**The API and the database are not deployed anywhere.** Only the static site is
live. The registration form cannot work in production until the API is hosted.

## Hard rules

All ten in `ARCHITECTURE.md` §7 apply. The ones most often broken in practice:

- **No personal data in logs.** Log the reference (`IND-2026-001234`), never a
  name, mobile number or ID number. Note that the office email's *subject line*
  contains the applicant's name — log `X-Induduzo-Reference` instead.
- **No bank or card details, ever.** Not in forms, schema, or logs.
- **Money is integer cents** with an explicit currency. Never a float.
- **Migrations are forward-only.** Add a file; never edit an applied one.
- **`VITE_*` is public.** It compiles into browser JavaScript. No secret goes near it.
- **A notification failure must never cost a lead.** Mail and WhatsApp sends run
  after commit, in a background task, and swallow their own failures.

## Decisions already taken — do not reopen

| Decision | Choice | When |
|---|---|---|
| Hosting | Netlify (web) + Railway (API, EU West) + Supabase (data/auth) + Cloudflare | see `docs/hosting-decision.md` |
| Supabase plan | **Free**, not Pro. Pausing mitigated by `db/keepalive.py` | 14 Sep 2026 |
| Consent gating a review request | **`contact_consent`** | 14 Sep 2026 |
| Scheduler | None yet. Jobs are built as idempotent commands; a clock gets wired at deploy | 14 Sep 2026 |
| Payments | Delegated to a provider. Never collected or stored here | — |

## Things that will bite you

**Migration numbering.** `0001`–`0012` exist. `docs/feature-1-review-loop.md`
says its new tables go in "migration 0008" — that number is taken. It must be
**0013**.

**Supabase tracks migrations separately.** `0008`–`0012` were applied through
Supabase's own migration system, so `public.schema_migrations` (what
`db/migrate.py` reads) does not know about them there. Before running the runner
against Supabase:

```bash
python db/migrate.py --baseline 0012_foreign_key_indexes.sql
```

`0005` and `0007` are **not** applied to Supabase — there is no `induduzo_api`
role and no `staff_users` table there. Every migration from `0008` guards its
grants with a `pg_roles` check for exactly this reason.

**`config.py` is a stdlib dataclass, not pydantic-settings.** Its fields resolve
`os.getenv(...)` **once, at import time**. Any new entrypoint must call
`load_dotenv()` *before* importing `app.config`, or it silently reads `None` for
every credential. `main.py` does this deliberately (`# noqa: E402`). `db/migrate.py`
and `db/keepalive.py` sidestep it by reading `DATABASE_URL` directly.

**`whatsapp_enabled` excludes `TWILIO_CONTENT_SID`.** `/health` will report
WhatsApp as configured while sends are still falling back to the sandbox path. A
green health check is not proof that the approved-template path is live.

**The free Supabase tier has no automated backups.** There are 61 real members
with ID numbers in that database. See the revision note in
`docs/hosting-decision.md` — this is an accepted temporary risk, not a solved
problem.

**Someone must run the keep-alive weekly** until a scheduler exists, or the free
project pauses and staff cannot sign in:

```bash
python db/keepalive.py
```

**The repo is public.** Check for secrets and personal data before every push.
`db/seed/` scripts are tracked; the CSV/XLSX/SQL data they read and write is
gitignored, and must stay that way.

## Commands

```bash
cd frontend && npm run lint && npm run typecheck && npm run build
```

CI runs those plus `npm audit --audit-level=high`, and `pip-audit --requirement
requirements.txt --strict` in `backend/`. All must pass. **There are no tests in
this repo** — CI is the only safety net.

Branch promotion is always `feature -> Dev -> internal -> main`. `main` deploys
the live public site.

Commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.
