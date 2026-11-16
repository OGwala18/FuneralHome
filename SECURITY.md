# Security

Status of this system against the pre-launch checklist, what is already done,
and what is not. Written honestly — the gaps are listed as plainly as the wins,
because a checklist that only records successes is worse than none.

**Context:** no real users yet. The static site is live; the API and database
are **not deployed**. That makes now the cheap moment to fix things.

---

## Checklist status

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Hide API keys | **Done** | All settings read from environment in `backend/app/config.py`. No credential in source. |
| 2 | Purge Git secrets | **Verified** | History scanned — no live secret found. A committed virtualenv (4,617 files) was untracked. |
| 3 | Use public DB key | **Done** | The browser never talks to the database. Only the API holds the connection string. Supabase's publishable key (public, in the portal) reaches no table, view, sequence or function: migration 0026 (13 Nov 2026) removed the insert grant 0004 had left open, and stops new tables inheriting Supabase's default grants. |
| 4 | Row-level security | **Done** | The API connects as `induduzo_api`, a non-owner role scoped by RLS policy. Verified: `rolbypassrls = false`, and DROP / DELETE / TRUNCATE / CREATE are all denied to it. |
| 5 | Encrypt sensitive data | **Partial** | Encrypted at rest by the volume. ID numbers sit in plaintext columns. |
| 6 | Server-side auth | **N/A** | No accounts exist. Nothing to authenticate yet. |
| 7 | Lock record access | **Done** | **The API has no GET or DELETE route for enquiries.** Data cannot be read back out through it. |
| 8 | Block field tampering | **Done** | Pydantic `extra="forbid"` rejects unknown fields; every column is set explicitly. |
| 9 | Secure session cookies | **N/A** | No sessions or cookies. |
| 10 | Hash passwords | **N/A** | No passwords stored. |
| 11 | Rate limit | **Done** | 6 enquiries/hour per IP on stage 1, 20 on stage 2. Returns `429` with `Retry-After`. |
| 12 | Bot protection | **Basic** | Honeypot field. Stops naive form-fillers, not a determined attacker. |
| 13 | Parameterise queries | **Verified** | Every query uses bound parameters. No string interpolation into SQL. |
| 14 | Validate all input | **Done** | Pydantic on every request: SA ID Luhn check, mobile format, lengths, enums. Since 13 Nov 2026 the public form also refuses control and invisible characters, a leading `=` `+` `@` (spreadsheet formulas), names without letters or with markup, and an email field naming more than one mailbox. A value Postgres cannot store is a `422` on every route, never a `500`. |
| 15 | Escape user content | **Done** | React escapes by default; the notification email HTML-escapes every field. Verified with an `<img onerror>` payload. |
| 16 | Restrict file uploads | **N/A** | No upload endpoint exists. |
| 17 | Trim API responses | **Done** | `EnquiryOut` returns six fields, never the full row. |
| 18 | Security headers | **Done** | `netlify.toml` for the site; `app/request_context.py` for the API on every response, errors included (nosniff, DENY framing, no-referrer, CSP `default-src 'none'`, Permissions-Policy, `Cache-Control: no-store`), plus a 256 KB request-body limit (`413`) and an `X-Request-ID`. |
| 19 | Force HTTPS | **Done** | HSTS on the site, and the API sends HSTS when deployed (suppressed in dev so it cannot pin localhost). Railway and Netlify terminate TLS. A deployed API also requires TLS to its database when the database is outside a private network (`app/db.py`, 13 Nov 2026). |
| 20 | Scan dependencies | **Done** | CI runs `npm audit` **and** `pip-audit`. Both trees clean — see below for what the first scan found. |

---

## What the first dependency scan found

Python dependencies had never been scanned. Adding `pip-audit` immediately
surfaced **10 known vulnerabilities across 2 packages**:

| Package | Was | Now | Advisories cleared |
|---|---|---|---|
| `starlette` (via FastAPI) | 0.41.3 | 1.6.0 | 9 |
| `python-dotenv` | 1.0.1 | 1.2.3 | 1 |

`npm audit` also found a high-severity issue in `nanoid`
(`GHSA-2v37-7h3g-55p8`), now fixed. Both trees report zero vulnerabilities and
the full end-to-end suite passes on the upgraded dependencies.

The lesson is the scan itself, not these particular CVEs: the frontend was
scanned and clean, the backend was never scanned and had ten. Both now run in
CI, so this cannot silently regress.

---

## Review, 13 Nov 2026

API, email, input and database checks, with production inspected read-only
(Supabase advisors and catalogue queries; no personal data read). The tests
that hold each fix in place are in `backend/tests/`.

| Found | Risk | Status |
|---|---|---|
| Production: Supabase's public key could INSERT into `plan_enquiries` and `enquiry_events` (0004's policies, never removed) | Anyone reading the public repo could write leads into the portal and forge audit events, around all of the API's checks. No such row existed | Fixed by **0026**, run on production by hand 13 Nov 2026 after a dry run. Verified there: 0 grants and 0 policies left for the public roles, and an insert as `anon` is refused ("permission denied"); the API's access and the member book unchanged |
| Production: `anon` held every privilege, TRUNCATE included, on the `ref_*` tables and `policy_overview`; Supabase's defaults grant `anon` and `authenticated` everything on each new table | TRUNCATE ignores row-level security; the next migration to add a table would have reopened the Data API | Fixed by **0026** (`test_database_security.py`) |
| A NUL byte in any form field | `500` on every attempt | `422` on the field; a database-level net on every route |
| `a,b@x.com` accepted as one email | The applicant confirmation addressed to two mailboxes | Refused |
| A name or town starting `=`, `+`, `@`; right-to-left overrides; zero-width characters | Formulas run when the office opens an export; names that display differently from what is stored | Refused |
| A refused applicant address was logged and stored as the raw SMTP error | Personal data in Railway's logs (rule 9) | Email failures are recorded as codes (`email_recipient_refused`) only |
| Staff searches (names, ID numbers) travel in the query string, which Uvicorn's access log printed | ID numbers in Railway's logs | Values redacted from the access log and Sentry, and the portal now searches with `POST .../search`, so the text is in the body, which no proxy logs. The GET `search` stays only for tabs opened before the release |
| Production: `business_phone_numbers` had row-level security, no policy and no grant for the API (0015 ran on Supabase before the API's role existed) | The first feature to read it would fail with "permission denied", in production only | Fixed by **0027**; checked with a test that the API reaches every table |
| No request-body limit | One multi-megabyte POST read into memory | `413` above 256 KB (`MAX_REQUEST_BYTES`) |
| psycopg's default `sslmode=prefer` to Supabase | A man in the middle can refuse TLS and read rows in transit | `require` when deployed and the host is not private |
| Database down: bare `500 text/plain` | Nothing for the form or a ticket to act on | `503 database_unavailable`, `Retry-After: 30` |
| Supabase's signing keys unreachable: staff told "sign in again" | A sign-in loop with no visible cause | `503 upstream_failed` |
| Supabase Auth: leaked-password protection is off (Supabase advisor) | Staff can choose a password already in a breach | **Owner action**: needs the Pro plan. On Free, set a 12-character minimum and required character types under Authentication > Sign In / Providers > Email |
| `db/backup.py` and `db/migrate.py` connect with the default `prefer` | The nightly backup crosses the internet | **Follow-up**: add `?sslmode=require` to the owner URLs on Railway |

What the browser can see: both production bundles were scanned. They hold
the API address, the Supabase project URL and its publishable key (public by
design, and now able to reach nothing), Plausible and Google Maps; no secret.
Every API call a browser makes will always show in its network tab, which is
why nothing secret or personal may be in one: responses stay narrow
(`EnquiryOut`), staff calls need a token checked on every request, and errors
carry a code and a request id rather than internals.

---

## Still to do at deploy time

The code-side work is done. What remains is deployment configuration.

### Set `CORS_ORIGINS` to the production origin

It currently lists localhost. Set it to `https://induduzo.co.za`. It is already
an explicit allowlist rather than `*`, which was the important half; this is
just the deployment value.

### Set `ENVIRONMENT` on every deployment

Any value other than `development` or `test` (so `internal` or `production`)
disables `/docs`, `/redoc` and `/openapi.json` and turns on HSTS. An internal
copy on a public Railway address is still public, so it is locked down too.
Leaving `ENVIRONMENT` unset falls back to `development` and exposes the docs.

### Set a real `API_DB_PASSWORD`

The committed default is a throwaway local value. Generate a strong one for
production and supply it through the environment, never a file in the repo.

### Terminate TLS in front of the API

HSTS is sent but means nothing without HTTPS actually being served.

---

## Worth doing, not blocking

- **Encrypt ID numbers at column level.** They are POPIA-protected identifiers
  sitting in plaintext. Consider `pgcrypto` or application-side encryption when
  the volume justifies the key-management burden.
- **Stronger bot protection.** The honeypot stops naive bots. If spam appears,
  add Cloudflare Turnstile or hCaptcha — both have free tiers.
- **Move rate limiting to Redis.** The current limiter is in-process: two API
  instances would each get their own allowance, and a restart resets the window.
  Fine for one instance, wrong the moment you scale.
- **Rotate the local dev password** if it is ever reused anywhere real. It sits
  in `.env.example` as a throwaway default and must never appear in production.

---

## Standing rules

These are enforced in code and must stay true.

1. **No secrets in the repo.** Environment only. `.env` is gitignored;
   `.env.example` is a template and must never hold a real credential.
2. **No bank or card data, anywhere.** Not in forms, schema, or logs. Payment
   collection is delegated to a provider.
3. **The browser is hostile.** `backend/app/schemas.py` revalidates everything.
   Client-side checks are a courtesy for the user, never a control.
4. **`enquiry_events` is append-only**, enforced by Postgres rules.
5. **Consent is required** at the database level before a row can exist.
6. **No personal data in logs.** Log references (`IND-2026-001234`), never names,
   numbers or ID numbers. The notification mailer deliberately logs only the
   subject on failure.
7. **`VITE_*` variables are public** — they are compiled into browser
   JavaScript. Never put a secret in one.
8. **Supabase's Data API serves nothing.** No table or view grants anything to
   Supabase's `authenticated` role (migration 0014), and public sign-up is off.
   The publishable key in the portal bundle is public, so any grant to a
   signed-in role is a way around the API's staff, role and 2FA checks.

---

## Reporting a problem

Email **admin@induduzo.co.za**. Do not open a public issue for a security report.
