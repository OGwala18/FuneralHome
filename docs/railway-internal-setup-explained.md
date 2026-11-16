# The internal environment on Railway: what was built, and why

Written 15 October 2026 for Onke. It explains the decisions, not only the clicks.
It contains no passwords or keys.

## What exists now

There is one Railway project, **induduzo**, on the Pro plan. It has an
environment called **`internal`**, where everything below lives. The
`production` environment is empty and kept for later.

| Service | What it is | Address | State |
|---|---|---|---|
| **Postgres** | The internal database, holding **test data only** | None. It's private and never on the internet | Online |
| **api** | The FastAPI backend | https://api-internal-8e41.up.railway.app | Online, health check passing |
| **migrator** | Runs once per deploy: builds the database, then sets up the API's login | None | Completed |
| **portal** | The staff portal | https://portal-internal.up.railway.app | Online |
| **site** | The public website copy | https://site-internal.up.railway.app | Online |

It all runs in **EU West (Amsterdam)**, the closest Railway region to South
Africa. It runs on its own: your laptop can be off.

## The decisions, and why

**One project, two environments.** `internal` deploys from the `internal`
branch, so your promotion path `feature → Dev → internal → main` now matches
what's running. `production` will later follow `main`.

**Test data only.** The internal database is new and empty. The 61 real
members are not in it, so testers can't email or message a real family.

**The database has no public address.** Only the API and the migrator can
reach it, over Railway's private network. "Add public access" was deliberately
left off.

**The API logs in as a restricted user, not the owner.** The migrator holds the
owner login, builds the tables, and sets a password on `induduzo_api`, a user
that can only read and write the rows the app needs and is bound by the
row-level security rules. The API gets only that restricted login. This is
rule 4 of SECURITY.md. The migrator's log shows "Connected as induduzo_api …
Done".

**Secrets never typed by me.** You pasted `API_DB_PASSWORD` and the Supabase
key yourself. I promoted both to **shared variables**, so the other services
use them by reference (`${{shared.API_DB_PASSWORD}}`) and the value lives in one
place. One caveat: Railway's change-review panel showed the password in plain
text, so I saw it once. The database isn't reachable from the internet, so the
risk is small, but rotating it is on the list below.

**Every deployed environment is locked down.** Before this, only
`ENVIRONMENT=production` hid the API's `/docs` page and turned on HTTPS-only
(HSTS). Without the private network, the internal copy is reachable from the
internet, so the code now locks down anything that isn't your own machine or
the test suite. Live check: `/docs` returns 404, and HSTS is on.

**The API listens on IPv4 and IPv6.** Railway's private network is IPv6.
`0.0.0.0` is IPv4 only, and Python makes an explicit `::` IPv6 only, so the
API now starts with an empty host, which opens both. This was tested in the
built image before shipping.

**`/health` decides whether a deploy goes live.** It returns 503 if the
database is down, and Railway waits for a 200 before switching traffic. The
first API deploy waited until the migrator had created its login, then passed.

**Restart policies.** The API is set to **Always**, so it restarts if it ever
stops. The migrator is set to **On failure**: a successful run stays stopped,
and a failed run (for example, the database still starting) is retried.

**Wait for CI is on for the API.** Railway only deploys a commit after the
GitHub checks pass: tests, audits and the image build.

**Watch paths.** The API rebuilds only when `backend/`, `db/` or its
Dockerfile change. The portal rebuilds only when `portal/` changes.

**Tailscale is benched**, as you asked. For now the protection is the portal
sign-in: only `admin@induduzo.co.za` is on the staff list, and the API checks
that list on every request. Anyone with the link sees a sign-in page and
nothing else. "Laptops only" comes back with Tailscale later.

**Email on, WhatsApp off.** The API sends from and to `admin@induduzo.co.za`
through `mail.induduzo.co.za` on port 465 (SSL; its certificate was checked).
It **can't actually send until you add `SMTP_PASSWORD`** (see below). The
system only ever emails the office, never families. WhatsApp is not
configured.

## Live checks run against the API

| Check | Result |
|---|---|
| `/health` | 200: environment internal, database up, email and staff portal configured, WhatsApp off |
| Security headers | HSTS, CSP, no framing, nosniff |
| `/docs` | 404 (hidden) |
| Staff route without signing in | 401 |
| `http://` | 301 to `https://` |

**CORS: only the portal and the site may call the API.** `CORS_ORIGINS`
refers to Railway's own address variables for those two services, so it stays
right if an address changes. Checked live: both origins are accepted, and any
other site's origin is refused.

## Things that went wrong on the way

- **The Railway Agent** connected the repo as a service called `FuneralHome`,
  set to the `main` branch. Its first build from `main` failed, as expected,
  because `main` doesn't have the API's Dockerfile yet. I renamed it `api` and
  pointed it at `internal`.
- **The site's first build failed.** `frontend/` still had a `bun.lockb` from
  the original template, which made Railway's builder use bun instead of npm,
  and the stale file failed. It was removed through the normal path: PR #7
  into `Dev`, then PR #8 into `internal`. Everything builds with npm now, as
  CI and Netlify already did.
- **Two empty "function" services** were created by accident. Railway's canvas
  read some of my typing as keyboard shortcuts. Both were discarded before
  anything deployed, and I switched to setting values directly.

## End-to-end check

A test registration sent through the live API returned 201 and was saved as
reference **IND-2026-001000**: "Railway Smoketest", placeholder number
082 000 0001. It is the first record in the internal database. Invalid input
was refused with 422.

## What's left

1. **Sign in to the portal** at https://portal-internal.up.railway.app with
   admin@induduzo.co.za. Your first sign-in makes you the owner of the internal
   staff list, and from there you can invite the other four people.
2. **Email:** add `SMTP_PASSWORD` (the admin mailbox password) to the **api**
   service yourself, then deploy. Until then, the office email for a new
   enquiry fails quietly and the enquiry is still saved.
3. **Rotate and seal `API_DB_PASSWORD`.** Generate a new value, paste it into
   the shared variable, choose **Seal**, then redeploy **migrator** first and
   **api** second.
4. **Check the data is still clean**, your next step: Supabase still holds
   the real book, untouched. The internal database holds only what testers
   create.
