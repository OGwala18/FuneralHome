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
| 3 | Use public DB key | **N/A** | The browser never talks to the database. Only the API holds the connection string. |
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
| 14 | Validate all input | **Done** | Pydantic on every request: SA ID Luhn check, mobile format, lengths, enums. |
| 15 | Escape user content | **Done** | React escapes by default; the notification email HTML-escapes every field. Verified with an `<img onerror>` payload. |
| 16 | Restrict file uploads | **N/A** | No upload endpoint exists. |
| 17 | Trim API responses | **Done** | `EnquiryOut` returns six fields, never the full row. |
| 18 | Security headers | **Done** | `netlify.toml` for the site; middleware in `main.py` for the API (nosniff, DENY framing, no-referrer, CSP `default-src 'none'`, Permissions-Policy). |
| 19 | Force HTTPS | **Ready** | HSTS on the site, and the API sends HSTS when `ENVIRONMENT=production` (suppressed in dev so it cannot pin localhost). Still needs TLS termination at deploy time. |
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

## Still to do at deploy time

The code-side work is done. What remains is deployment configuration.

### Set `CORS_ORIGINS` to the production origin

It currently lists localhost. Set it to `https://induduzo.co.za`. It is already
an explicit allowlist rather than `*`, which was the important half; this is
just the deployment value.

### Set `ENVIRONMENT=production`

This is not cosmetic. It is what disables `/docs`, `/redoc` and
`/openapi.json`, and what turns on HSTS. Verified: with it set, all three doc
routes return `404` and `Strict-Transport-Security` appears; without it, `/docs`
returns `200`.

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

---

## Reporting a problem

Email **admin@induduzo.co.za**. Do not open a public issue for a security report.
