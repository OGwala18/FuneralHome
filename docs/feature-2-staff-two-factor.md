# Feature 2 — Two-step sign-in for the staff portal

**Working brief for whoever builds this, including an agent picking it up cold.**
Read `ARCHITECTURE.md` first; it says where everything lives and which rules
must not be broken. This file says what to build, in what order, and how to
prove it works.

| | |
|---|---|
| Status | Planned. Bit 0 in progress (see §12 tracker) |
| Priority | Required before the production portal launches |
| Repo state at time of writing | `fae330d` (Dev), 16 Oct 2026 |
| Touches | `backend/`, `db/migrations/`, `portal/`, `.github/workflows/`, docs |

---

## 1. What this feature is

Today a staff member signs in with an email and password, and that is all. Anyone
who learns a password (guessed, reused from another site, shared, or phished) gets
every member's name, phone and ID number.

After this feature, signing in takes two steps:

1. **Password**, checked by Supabase, as now.
2. **A second step that proves it is really you**, using one of:
   - a **passkey**: Windows Hello (fingerprint, face or PIN) on your work laptop;
   - an **authenticator app** (Google or Microsoft Authenticator) on your phone;
   - an **emailed code**: 6 digits, valid for 5 minutes, used once.

A computer you mark as **trusted** skips the second step for **30 days**. After
that it asks again.

**What it protects against:** a stolen, guessed or shared password.

**What it does not protect against:**
- someone sitting at an unlocked, trusted laptop. Windows sign-in still matters;
- malware on a staff computer;
- someone who has both the password and access to that person's mailbox, when
  the emailed code is the method used. This is why passkeys and the app are
  preferred, and why §3 asks whether email should stay available once a stronger
  method is set up.

---

## 2. Decisions taken

| Decision | Choice | Who, when |
|---|---|---|
| Methods offered | Passkey, authenticator app and emailed code | Owner, 16 Oct 2026 |
| Trusted computers | Yes, for 30 days | Owner, 16 Oct 2026 |
| When the second step is asked | On every sign-in from a computer that isn't trusted, not only the first-ever sign-in | Agreed 16 Oct 2026 |
| Where it is enforced | In our API, for every staff route, as one dependency | This plan; reasons in §4 |
| Where codes are sent | Only to the email address on the person's staff record, which the owner sets. Never to an address typed on the screen | This plan |
| Prerequisite: no way around the API | Public sign-up is off, and migration 0014 closed Supabase's Data API to signed-in accounts | Done 16 Oct 2026 |

---

## 3. Decisions still open (with recommendations)

Settle these before the phase that needs them. Each one is a setting, so changing
it later does not mean rebuilding.

| # | Question | Recommendation | Needed by |
|---|---|---|---|
| 1 | Once someone has set up a passkey or the app, can they still use the emailed code? | **Internal: yes. Production: no** for owners and admins. They use a recovery code or ask the owner. Otherwise the weakest method decides the real security. | Production launch |
| 2 | Must every staff member set up a passkey or the app? | **Owners and admins: required by launch.** Viewers are asked at every sign-in until they do. | Production launch |
| 3 | Is "Trust this computer" ticked by default? | **No.** It should be a deliberate choice, made only on your own work laptop. | Phase 2 |
| 4 | How long does an untrusted computer stay signed in before asking again? | **12 hours**, one working day. | Phase 2 |
| 5 | Production passkey domain (WebAuthn "relying party") | **`portal.induduzo.co.za`**, the narrowest choice. A passkey made for it can't be used by any other site, including our own public one. | Phase 4 |
| 6 | Laptop-only passkeys? Some passkeys sync to a phone through a password manager. | **Off for now.** It's available as a switch: reject passkeys that report they sync. This fits the earlier wish that phones can't get in. | Phase 4 |

---

## 4. Why we build it in our API instead of using Supabase's

Supabase has TOTP (authenticator app) MFA, free on all plans, and experimental
passkeys. Neither fits on its own:

- **Supabase has no emailed-code second step.** Its email codes are a *first*
  factor, a way to sign in without a password.
- **Supabase passkeys are experimental and passwordless-only**, and each project
  has **one** passkey domain. Our one Supabase project serves three portals:
  `localhost`, `portal-internal.up.railway.app` and later `portal.induduzo.co.za`.
  Passkeys can't span them.
- **Mixing two systems means two sources of truth.** Supabase would mark the app
  in its token, while our API would track the email code and passkeys. Every
  check would have to agree, and every test would need a real Supabase.

So **Supabase stays the password step**, and **our API does the second step for all
three methods** with one data model, one enforcement point, and tests that run in
CI without Supabase.

**The cost:** we store authenticator-app secrets, encrypted (§7), and own more
code. Both are kept small by using two well-known libraries:

| Library | Version (16 Oct 2026) | Licence | Use |
|---|---|---|---|
| `pyotp` | 2.10.0 | MIT | Authenticator-app codes |
| `webauthn` (py_webauthn, Duo Labs) | 3.0.1 | BSD-3 | Passkeys, server side |
| `cryptography` | 50.0.2 | Apache/BSD | Encrypting app secrets. Already installed through `pyjwt[crypto]`; pin it explicitly |
| `@simplewebauthn/browser` | 14.0.0 | MIT | Passkeys, browser side |
| `qrcode` (+ `@types/qrcode` 1.5.6, dev) | 1.5.4 | MIT | Drawing the authenticator-app QR code on a canvas |

Re-check each version and run `pip-audit` and `npm audit` when the work starts.
`webauthn` 3.x is a new major version: read its changelog before copying any 2.x
examples.

---

## 5. How it works

```
 Staff laptop                     Supabase Auth              Our API                 Postgres
 ────────────                     ─────────────              ───────                 ────────
 email + password ───────────────▶ checks password
                  ◀─────────────── session (token holds
                                   user id, email,
                                   session_id)
 any portal call ──── token + trusted-device header (if any) ─▶ 1. token valid?
                                                                2. active staff?
                                                                3. second step done
                                                                   for this session? ──▶ staff_session_verifications
                                                                   or trusted device? ──▶ staff_trusted_devices
                  ◀── 403 "second_step_required" ────────────── if neither
 "Confirm it's you" screen
 passkey / app code / email code ──────────────────────────────▶ verify ──────────────▶ record verification
                  ◀── ok (+ device token if "trust") ─────────── (session_id, method,
 portal opens                                                    expires_at)
```

**The session is the unit.** Every Supabase token carries a `session_id` that
stays the same across token refreshes until the person signs out. The API records
"this session passed the second step until <time>". A new sign-in is a new
session, so it is asked again unless the computer is trusted.

**Trusted computers.** On success with "Trust this computer for 30 days" ticked,
the API returns a random 32-byte token. The portal keeps it in browser storage
for that site and sends it as `X-Induduzo-Device` on every call. The API stores
only its SHA-256 hash, tied to that staff member, expiring 30 days after it was
issued. The 30 days don't extend with use.

- **Not a cookie, on purpose.** On Railway, the portal and API live on different
  sites (`up.railway.app` is a public suffix), so browsers block or partition
  cookies between them. A header works the same everywhere.
- **No new XSS risk.** Script running in the portal could already take the
  Supabase session from the same storage. The defence is the portal security
  headers in Phase 6.
- **Never enough on its own.** The token replaces only the second step, never the
  password, and it is useless with another person's password.

**The emailed code's life**, exactly as specified:

```
 requested ──▶ verified   (right code, within 5 min, same session)  ── can't be used again
     │
     ├──────▶ expired    (5 minutes passed)                         ── stays expired; NO automatic resend
     ├──────▶ used up    (5 wrong attempts)                         ── stays dead
     └──────▶ replaced   (person asked for a new one)               ── old code stops working
```

"Expired" is **worked out from the clock**, not stored as a 1/0 flag. The row
keeps `expires_at`, `used_at`, `replaced_at` and `attempts`. A code is dead if
any of these holds:

- the time is past `expires_at`;
- `used_at` is set;
- `replaced_at` is set;
- `attempts` has reached 5.

A flag can be left wrong if something fails to update it. The clock can't. This
is the same rule the payment schedule follows for "overdue". Nothing ever sends a
code unless the person presses **Send a new code**.

---

## 6. Data model

One migration, using the next free number when it's built (0015 today). Follow
the house style of 0007 and 0013:
- `tenant_id` on every table;
- RLS on, with policies for `induduzo_api` only, guarded by a `pg_roles` check;
- **nothing for `anon` or `authenticated`.** See SECURITY.md rule 8.

Sketch, not final SQL:

```sql
-- Random per-person handle WebAuthn uses instead of the email or our row id.
alter table staff_users add column webauthn_user_handle bytea unique;

-- Short-lived, single-use challenges: emailed codes and passkey ceremonies.
create table staff_mfa_challenges (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id      uuid not null references staff_users(id),
  session_id         uuid not null,          -- the Supabase session it belongs to
  kind               text not null check (kind in
                       ('email_code', 'passkey_sign_in', 'passkey_setup')),
  code_hash          bytea,                  -- HMAC of the code; never the code
  webauthn_challenge bytea,
  attempts           smallint not null default 0,
  created_at         timestamptz not null default now(),   -- "when it was requested"
  expires_at         timestamptz not null,
  used_at            timestamptz,            -- verified; can never be used again
  replaced_at        timestamptz,            -- a newer code was sent
  check ((kind = 'email_code') = (code_hash is not null)),
  check ((kind <> 'email_code') = (webauthn_challenge is not null))
);

create table staff_totp_factors (              -- authenticator apps
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id    uuid not null references staff_users(id),
  name             text not null default 'Authenticator app',
  secret_encrypted bytea,                      -- nulled the moment it is removed
  status           text not null check (status in ('pending', 'active', 'removed')),
  last_used_step   bigint,                     -- stops the same code working twice
  created_at       timestamptz not null default now(),
  confirmed_at     timestamptz,
  last_used_at     timestamptz,
  removed_at       timestamptz,
  removed_by       text
);

create table staff_passkeys (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id   uuid not null references staff_users(id),
  credential_id   bytea not null unique,
  public_key      bytea not null,
  sign_count      bigint not null default 0,
  transports      text[] not null default '{}',
  aaguid          uuid,
  backup_eligible boolean not null,           -- true = can sync to other devices
  backed_up       boolean not null,
  name            text not null,              -- "Front desk laptop"
  created_at      timestamptz not null default now(),
  last_used_at    timestamptz,
  removed_at      timestamptz,
  removed_by      text
);

create table staff_trusted_devices (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id uuid not null references staff_users(id),
  token_hash    bytea not null unique,         -- SHA-256 of the token; never the token
  label         text not null,                 -- "Chrome on Windows", for display only
  created_at    timestamptz not null default now(),
  expires_at    timestamptz not null,
  last_used_at  timestamptz,
  revoked_at    timestamptz,
  revoked_by    text,
  check (expires_at <= created_at + interval '30 days')
);

create table staff_session_verifications (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id uuid not null references staff_users(id),
  session_id    uuid not null,
  method        text not null check (method in
                  ('email_code', 'authenticator_app', 'passkey',
                   'recovery_code', 'trusted_device')),
  verified_at   timestamptz not null default now(),
  expires_at    timestamptz not null
);

create table staff_recovery_codes (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id uuid not null references staff_users(id),
  batch_id      uuid not null,                 -- regenerating replaces the whole batch
  code_hash     bytea not null,
  created_at    timestamptz not null default now(),
  used_at       timestamptz,
  replaced_at   timestamptz
);
```

Indexes:
- `(staff_user_id, created_at desc)` on challenges and verifications;
- `(session_id, staff_user_id, expires_at desc)` on verifications;
- partial indexes on active factors and passkeys (`where removed_at is null`) and
  on live devices (`where revoked_at is null`).

**Housekeeping.** Add an idempotent command, `backend/app/jobs/purge_two_step.py`,
in line with the decision that jobs are commands until a scheduler exists. It
deletes:
- challenges older than 7 days;
- verifications older than 60 days;
- devices expired or revoked more than 90 days ago.

`staff_events` keeps the permanent record.

---

## 7. Secrets and settings

All on the API. Nothing new in the portal is secret.

| Variable | What | Notes |
|---|---|---|
| `TWO_STEP_ENCRYPTION_KEYS` | Fernet keys, comma-separated; the first one encrypts | Encrypts authenticator-app secrets. A list, so a key can be rotated (MultiFernet). **Sealed** on Railway. **Different per environment.** |
| `TWO_STEP_CODE_PEPPER` | 32+ random bytes | HMAC key for emailed codes and recovery codes. Without it, a stolen database copy can't be used to guess codes offline. Sealed, and per environment. |
| `WEBAUTHN_RP_ID` | Passkey domain | `localhost`, `portal-internal.up.railway.app`, `portal.induduzo.co.za` |
| `WEBAUTHN_RP_NAME` | Shown in the passkey prompt | "Induduzo Staff Portal" |
| `WEBAUTHN_ORIGINS` | Exact portal origins accepted | e.g. `https://portal-internal.up.railway.app` |
| `TWO_STEP_ENFORCEMENT` | `on` / `off` | `off` only in `development` and `test`. **The API refuses to start with `off` when `ENVIRONMENT=production`**, so a mistake fails loudly rather than leaving the door open. |

**Fail closed:** if enforcement is on but a key is missing, staff routes return
503 "Two-step sign-in is not configured". They never quietly let people through.

**Constants, kept in code rather than env:**
- 6-digit codes, valid 5 minutes, at most 5 attempts;
- resend allowed after 60 seconds, at most 5 codes an hour;
- trust lasts 30 days, an untrusted session 12 hours;
- the lockout window is 15 minutes.

**CORS:** add `X-Induduzo-Device` to `allow_headers`. Either add `DELETE` to
`allow_methods`, or use `POST …/remove` endpoints as the rest of the API does.

---

## 8. API

**Two dependencies instead of one**, in `backend/app/auth.py`:

| Dependency | Checks | Used by |
|---|---|---|
| `require_staff_identity` | Valid Supabase token and an active staff record, as `require_staff` does today | **Only** the endpoints that complete the second step |
| `require_staff` | The above, **plus** a passed second step for this session or a trusted device | **Everything else.** It stays on the `/api/admin` router, so every existing and future route is protected without anyone remembering to add it |

`StaffUser` gains `session_id`, `verified_by`, and `verified_recently`, which is
true if a real method (not a trusted device) was used in the last 15 minutes.

**Error contract.** Keep `detail` as a readable sentence for the screen, and add
a machine `code` the portal can branch on:

| HTTP | `code` | When |
|---|---|---|
| 403 | `second_step_required` | Signed in, second step not done |
| 403 | `recent_check_required` | A sensitive action needs a fresh second step |
| 400 | `code_wrong` / `code_expired` / `code_used_up` | Emailed or app code problems |
| 429 | `too_many_attempts` / `resend_too_soon` | With `Retry-After` |
| 502 | `email_send_failed` | The code could not be emailed; offer another method |

**Endpoints**, under `/api/admin/2fa` on a separate router with
`require_staff_identity`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/status` | What this person has set up, whether this session has passed, and whether this computer is trusted |
| POST | `/email/send` | Create a code and email it. Returns `challenge_id`, `expires_at`, `resend_after` and a masked address (`t•••@induduzo.co.za`) |
| POST | `/email/verify` | `{challenge_id, code, trust_device}` |
| POST | `/app/verify` | `{code, trust_device}` |
| POST | `/passkey/start` | Passkey sign-in options, plus `challenge_id` |
| POST | `/passkey/verify` | `{challenge_id, credential, trust_device}` |
| POST | `/recovery/verify` | `{code, trust_device}` |

Under `/api/admin/2fa` with the strict `require_staff`, so the second step must
already be done:

| Method | Path | Purpose |
|---|---|---|
| POST | `/app/setup` | Start: returns the `otpauth://` link and the key for typing in by hand |
| POST | `/app/setup/confirm` | `{factor_id, code}` turns it on. Returns recovery codes the first time a strong method is added |
| POST | `/passkeys/setup/start` | Registration options |
| POST | `/passkeys/setup/finish` | `{challenge_id, credential, name}` |
| PATCH | `/passkeys/{id}` | Rename |
| POST | `/methods/{id}/remove` | **Needs a recent check.** Refused if it would leave an owner or admin with no strong method, once decision 2 applies |
| GET | `/devices` | Trusted computers, with this one marked |
| POST | `/devices/{id}/forget`, `/devices/forget-others` | Revoke trust |
| POST | `/recovery-codes` | **Needs a recent check.** A new set; the old set stops working |

Owner only:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/admin/staff/{id}/2fa/reset` | Removes the person's methods, trusted computers, recovery codes and verified sessions. Not allowed on yourself. Emails the person |
| — | `PATCH /api/admin/staff/{id}/active` (existing) | **Change:** deactivating also revokes trusted computers and verified sessions immediately |

**Rate limits live in the database, per person**, not in the existing in-process
per-IP limiter:
- per-IP limits are spoofable here, and reset on restart;
- 10 failed second-step attempts in 15 minutes, across all methods, locks that
  person out of the second step for 15 minutes;
- counted from `staff_events`, so there is no new table;
- the lockout is logged, and the owner is emailed.

**Audit (`staff_events`):**
- `2fa_code_sent`, `2fa_passed` (method), `2fa_failed` (method, reason), `2fa_locked`;
- `2fa_method_added` and `2fa_method_removed` (type, name);
- `2fa_device_trusted` and `2fa_device_revoked`;
- `2fa_recovery_used` and `2fa_recovery_regenerated`;
- `2fa_reset_by_owner` and `2fa_break_glass`.

**Payloads never contain** a code, a secret, a device token or an IP address
(ARCHITECTURE.md rule 9). Application logs follow the same rule, and tests prove
it (§11).

---

## 9. Method details

### Emailed code
- **Making the code:** `secrets.randbelow(1_000_000)`, zero-padded to 6 digits.
  Store `HMAC-SHA256(pepper, challenge_id + ":" + code)`; compare with
  `hmac.compare_digest`.
- **Limits:**
  - bound to the session that asked for it, so a code requested on one computer
    fails on another;
  - asking for a new code replaces the old one;
  - one send every 60 seconds, at most 5 an hour.
- **Sending:**
  - goes **inside the request**, not as a background task, because the person is
    waiting and must be told if it failed. (The lead email rule, "a notification
    failure must never cost a lead", is about notifications; this is a sign-in
    step.)
  - reuses the SMTP settings, but with its own message builder in
    `services/email.py`, not the lead template;
  - sent **to the address on the staff record** only.
- **The email itself:**
  - subject "Your Induduzo sign-in code", **without the code**, so it doesn't
    show on lock-screen previews;
  - the body shows the code, when it expires ("valid until 14:05"), and "If this
    wasn't you, someone may know your password. Tell the owner.";
  - no links in it.

### Authenticator app
- **The secret:** `pyotp.random_base32()` (160 bits), with 30-second steps,
  6 digits and SHA-1, which every authenticator app supports.
- **Naming:**
  - issuer "Induduzo" in production, "Induduzo (internal)" elsewhere, so the two
    entries in someone's app can't be confused;
  - account name: the staff email.
- **Setting up:**
  - the portal draws the QR code itself from the `otpauth://` link, with
    `qrcode` onto a canvas, and shows the key for typing in by hand;
  - it isn't switched on until a correct code is entered;
  - a pending setup expires after 10 minutes.
- **Checking a code:**
  - accepted one step either side of now (±30 s clock drift);
  - **the same step can't be used twice**, enforced with `last_used_step`.
- **Limits:** at most 2 apps per person (e.g. their phone plus a backup).
- **Storage:** the secret is encrypted with `TWO_STEP_ENCRYPTION_KEYS`. On
  removal, the encrypted secret is wiped, not just flagged.

### Passkeys
- **Library:** `webauthn` 3.x on the server, `@simplewebauthn/browser` in the
  portal.
- **Setting up:**
  - `userVerification: "required"`, so the laptop must check the fingerprint,
    face or PIN;
  - `residentKey: "preferred"`;
  - `attestation: "none"`;
  - algorithms ES256, RS256 (Windows Hello often uses it) and EdDSA;
  - the person's existing passkeys are excluded;
  - the user handle is the random `webauthn_user_handle`, never the email.
- **Signing in:**
  - only the person's own passkeys are offered (we know who they are from the
    password step);
  - the check covers the challenge (single use, 5 minutes, same session), the
    origin (in `WEBAUTHN_ORIGINS`), the RP ID and the user-verification flag.
- **Sign counter:**
  - if both the stored and new counts are non-zero and the new one isn't higher,
    refuse the sign-in and alert the owner, because the passkey may be cloned;
  - synced passkeys always report 0, so 0 is accepted.
- **Passkeys belong to one portal address.** One made on the internal portal
  won't work on production. Staff add a new one on launch day, which takes a
  minute.
- **Laptop-only switch** (decision 6): reject passkeys with
  `backup_eligible = true`.
- **Browser permissions:** the portal's `Permissions-Policy` must not disable
  `publickey-credentials-get` or `publickey-credentials-create`.
- **Later, not now:** sign in with the passkey alone, with no password.

### Trusted computers
- Explained in §5.
- **The list:** Settings shows each one as label, trusted until, last used, and
  Forget.
- **When trust is revoked:**
  - on owner reset and on deactivation;
  - when the person forgets the computer or chooses "Forget all others".
- **Sign out keeps it:** signing out does **not** forget the computer, because
  that's the point of trusting it. "Forget this computer" is a separate button.

### Recovery codes
- **Making them:**
  - 10 codes, made when the first passkey or app is added;
  - format `XXXX-XXXX`, from an alphabet without look-alike characters, giving
    40 bits each;
  - stored as HMACs;
  - **shown once**, with Print and Copy, and "Keep these somewhere safe, not on
    this computer".
- **Using one:**
  - each works once and passes the second step;
  - using one emails the person and shows "You have 9 left".
- **Replacing them:** a new set replaces the old one (needs a recent check).

### Owner reset and break-glass
- **Owner reset** (endpoint above), for when someone loses their phone or laptop.
  Their next sign-in uses the emailed code, then they set up again.
- **Break-glass**, for when the **only** owner is locked out:
  - for example, email is down and their phone is lost;
  - `python -m app.jobs.reset_two_step --email someone@induduzo.co.za`, run from
    the api service's console in Railway;
  - Railway project access already means full control, so this adds no new door;
  - it writes `2fa_break_glass` to `staff_events`.

### Emails to the staff member
These are notifications, so failures are logged and swallowed:
- a new passkey or app was added;
- a method was removed;
- a recovery code was used;
- the owner reset your two-step sign-in;
- you were locked out after too many attempts (the owner is told too).

---

## 10. Portal

**Gate (`App.tsx`).** Today, any error from `fetchMe()` shows "No access". Change:
- `second_step_required` shows the **Confirm it's you** screen;
- after success, it fetches `me` again.

**`lib/api.ts`:**
- send `X-Induduzo-Device` on every request when a token is stored;
- `ApiError` gains `code`;
- add the 2FA calls.

**New screens:**

1. **Confirm it's you**
   - Opens on the person's strongest method: passkey, then app, then email.
     "Use another way" switches.
   - **Passkey:** one button that opens Windows Hello. Only offered if the
     browser supports passkeys (`browserSupportsWebAuthn()`).
   - **App:** 6-digit input with `autocomplete="one-time-code"` and
     `inputmode="numeric"`; pasting a code works.
   - **Email:**
     - nothing is sent until the person presses **Email me a code**. Then:
       "We sent a code to t•••@induduzo.co.za. It expires at 14:05.";
     - a live countdown;
     - **Send a new code** is disabled for 60 seconds;
     - when expired: "This code has expired. Send a new one." and nothing else
       happens.
   - **Trust this computer for 30 days**: unticked, with the hint "Only on your
     own work laptop".
   - A **Recovery code** link.
2. **Make sign-in stronger**, shown once someone has passed with email and has no
   passkey or app:
   - Passkey (recommended on your laptop), Authenticator app, or Not now;
   - "Not now" disappears for owners and admins once decision 2 is on.
3. **Settings → Sign-in security:**
   - passkeys (rename, remove), apps (remove), trusted computers;
   - recovery codes (how many left, make new ones);
   - "Forget this computer".
4. **Team (owner)**: a 2FA column showing Passkey / App / Email only / Not set
   up, and **Reset two-step sign-in**.

**Routes:** add `verify`, which isn't a URL (it's a gate state, like the login
screen), and `security` under Settings.

**Copy:** plain words. "Authenticator app", never "TOTP". "Passkey (Windows
Hello)". Errors say what to do next.

**Portal security headers (Phase 6).** The portal sends no CSP today. A portal
that holds session and device tokens in browser storage needs:
- a strict CSP: `default-src 'self'`; `connect-src` for the API, Supabase and
  Sentry; Google Fonts; `frame-ancestors 'none'`;
- a `Permissions-Policy` that keeps passkeys allowed.

On Railway that means a Caddyfile for Railpack. Check that Railpack honours one;
if not, give the portal a small Caddy Dockerfile. In production, use whatever the
portal host uses. Test on the **deployed** portal: `vite dev` doesn't apply
headers, which is the CSP trap noted in this repo before.

---

## 11. Testing: proving it works and connects

Four layers. A and B run on every pull request; C runs on pull requests into
`internal` and `main`; D is done by people before production.

### A. Unit tests (no database)
- **Codes:** always 6 digits; zero-padded; HMAC matches; constant-time compare
  used.
- **Expiry rules:** a code is dead at exactly 5:00, after use, after
  replacement, and after 5 attempts.
- **Authenticator app at a frozen time:**
  - right code accepted; one step either side accepted; two steps refused;
  - the same step refused the second time.
- **Encryption:**
  - round-trip works;
  - the stored value isn't the base32 secret;
  - a wrong key fails;
  - rotation: the old key still decrypts, and the new key encrypts.
- **Device tokens:** 32 bytes; only the hash is stored; the hash lookup works.
- **Masking:** `thandi@…` becomes `t•••@…`.

### B. API behaviour tests (pytest, throwaway Postgres, as now)

New fixtures, all in `backend/tests/conftest.py`:
- **`signed_in(email, session_id)`** mints a **real ES256 token** with a test
  key, and stubs the JWKS client. So the **real** `require_staff` runs end to
  end: signature, staff lookup, then the second-step check. (Today's `staff_as`
  override stays for the existing role tests.)
- **`mailbox`** replaces the SMTP send with a list that records messages, so a
  test can read the code from the email.
- **`clock`**: the service takes `now` from one function the tests can move.
  Expiry, 30-day trust and 12-hour sessions are then tested without sleeping.
- **`software_passkey`**: a small helper of about 80 lines that acts as a
  passkey. It holds an EC P-256 key, builds `clientDataJSON` and
  `authenticatorData` with the right flags, and signs. No browser needed.

**The guard test (most important).** Read every `/api/admin` route from the
OpenAPI schema, as the existing 401 test does. For a session that has passed the
password but not the second step, **every route outside the 2FA allowlist must
return 403 `second_step_required`**. A route added later without protection fails
CI.

**Emailed code:**
- sending then verifying passes, and the email went to the staff record's
  address;
- a wrong code ×5 kills it, and even the right code is then refused;
- after 5 minutes it's refused **and no new email is sent** (the mailbox count is
  unchanged);
- a resend inside 60 s gets 429; the 6th code in an hour gets 429;
- after a new code, the old code is refused;
- a code from session A is refused in session B;
- **no code appears in logs** (`caplog`) or in any `staff_events` payload.

**Authenticator app:**
- setup only turns on after a correct code;
- a pending setup expires;
- verification works; a replayed code is refused;
- removing needs a recent check, and wipes the secret.

**Passkeys:**
- setup then sign-in passes;
- refused: wrong origin, wrong RP ID, wrong or reused challenge, missing
  user-verification flag, another person's passkey, unknown credential;
- a counter going backwards is refused and alerts the owner;
- the laptop-only switch rejects a passkey that reports it syncs.

**Trusted computers:**
- verifying with trust returns a token; a **new session** with that header passes
  without the second step;
- refused: on day 31, after Forget, with another person's token, and with a
  person's own token after the owner resets them or deactivates them;
- without the header, the second step is required again.

**Sessions:**
- a verified session expires after 12 hours;
- signing in again (a new `session_id`) asks again.

**Recovery codes:** each works once; the old set is dead after regeneration.

**Owner reset and break-glass:**
- an owner can reset an admin; an admin can't;
- an owner can't reset themselves through the API;
- the break-glass command works and is logged.

**Lockout:** 10 failures in 15 minutes gives 429 across all methods; the
lockout lifts after the window.

**Settings:**
- `TWO_STEP_ENFORCEMENT=off` with `ENVIRONMENT=production` refuses to start;
- missing keys give 503, not open access.

**Audit:** every action writes its event, with no secrets in it.

### C. Browser end-to-end tests (Playwright, new CI job)

**The stack in CI:**
- **real Supabase Auth running locally** (Supabase CLI), set to sign with an
  ES256 key so it matches production;
- Postgres with the migrations;
- the API;
- the built portal;
- **Mailpit**, which catches emails, with an HTTP API to read them.

Check early (start of Phase 6) that the local Supabase stack can sign ES256. If
it can't, use a small fake auth server that issues ES256 tokens and serves a JWKS.

**Passkeys** use Chrome's **virtual authenticator** (DevTools protocol `WebAuthn`
domain), which behaves like Windows Hello and needs no hardware. **App codes** are
worked out by the test from the key shown on the setup screen.

**Scenarios:**
1. First sign-in: password, then the emailed code (read from Mailpit), then
   "Make sign-in stronger", then Not now. The portal opens.
2. Trust this computer, sign out, sign in: no second step. A fresh browser
   profile is asked again.
3. Let a code expire: the screen offers "Send a new one", and **Mailpit receives
   nothing new** until it's pressed.
4. Five wrong codes: the code is dead and a new one must be requested.
5. Set up the authenticator app; the next sign-in uses it.
6. Add a passkey; the next sign-in uses it with one click.
7. Remove a method: it asks for a fresh check first.
8. The owner resets a colleague. The colleague's trusted computer stops working
   and they are back to the emailed code.
9. The owner deactivates a colleague who is signed in: their next click is
   refused.
10. With 2FA done, every page loads. A raw API call from a second, unverified
    session gets 403.

### D. Manual acceptance on the internal environment (real people, real devices)
- [ ] Passkey with **Windows Hello** on each staff laptop
- [ ] Google Authenticator **and** Microsoft Authenticator on a phone
- [ ] Code email lands in the **inbox**, not spam, for @induduzo.co.za and Gmail. Check SPF, DKIM and DMARC pass in the message headers
- [ ] A computer with its clock 1 minute off still works
- [ ] Trusted computer shown in Settings with the right date; Forget works
- [ ] **Lost-phone drill:** sign in with a recovery code
- [ ] **Owner-locked-out drill:** break-glass from the Railway console
- [ ] All 5 people set up, and recovery codes stored offline

### E. Security checks before production
- [ ] Logs from a full E2E run contain no code, secret or token. Search for 6-digit codes, base32 and base64url
- [ ] `pip-audit` and `npm audit` clean for the new libraries
- [ ] Guard test passing, and no route on the allowlist that shouldn't be
- [ ] Portal CSP live and tested on the deployed portal
- [ ] Supabase: sign-up still off, Data API still closed (no `authenticated` grants)
- [ ] Production keys generated fresh and sealed; enforcement on

**CI also gains a portal job.** CI doesn't build or check the portal today, and
it must before any 2FA screens ship. It runs `npm ci`, typecheck, build and
`npm audit --omit=dev --audit-level=high` in `portal/`.

---

## 12. Build order: one bit per session

The build is split into small **bits**. Each bit is one fresh Claude Code session
and one pull request: branch from `Dev`, merge into `Dev`, then promote to
`internal`. Bits are done **in order**, and everything listed under "Depends on"
must be merged first. The portal must keep working after every merge.

**Why a fresh session per bit:** every step of a session re-reads the whole
conversation. Starting each bit from this document, rather than from one long
conversation, is the biggest single saving in tokens. Rough sizes are given per
bit; the whole build is about 120–150 million tokens when done this way.

### Tracker

Each bit's pull request updates its own row.

| Bit | What | Depends on | Size (tokens) | Status |
|---|---|---|---|---|
| 0 | Land the groundwork: the Supabase fix (0014) and this plan | — | ~3M | In progress |
| 1 | Portal checks in CI | 0 | ~4M | Not started |
| 2 | Prove the office email sends on internal | — | ~2M | Not started |
| 3 | Database tables, settings and crypto helpers | 0 | ~8M | Not started |
| 4 | Enforcement core and the guard test (enforcement off) | 3 | ~10M | Not started |
| 5 | Emailed code (API) | 2, 4 | ~10M | Not started |
| 6 | Trusted computers and the "Confirm it's you" screen; enforcement on for internal | 1, 5 | ~15M | Not started |
| 7 | Authenticator app | 6 | ~10M | Not started |
| 8 | Passkeys (API) | 6 | ~12M | Not started |
| 9 | Passkeys (portal) and the Windows Hello check | 8 | ~10M | Not started |
| 10 | Recovery codes, "Make sign-in stronger" and Settings → Sign-in security | 7, 9 | ~10M | Not started |
| 11 | Owner tools: reset, deactivation, break-glass, lockout, emails, purge | 10 | ~12M | Not started |
| 12 | Portal security headers | 9 | ~8M | Not started |
| 13 | Browser tests in CI | 11, 12 | ~20–25M | Not started |
| 14 | A week on internal with the team, then §13 | 13 | varies | Not started |
| + | Optional: Change password and Forgot password | 11 | ~8M | Not started |

### Starting a bit

Paste this into a new session, with the bit number filled in:

> Build **Bit N** of `docs/feature-2-staff-two-factor.md` (§12). Read `CLAUDE.md`,
> `ARCHITECTURE.md` and the plan sections listed on the Bit N card first. Branch
> from `Dev` as `feat/2fa-bitN-<short-name>`. Stay inside the card's scope; if
> something outside it needs doing, note it rather than doing it. Never touch
> Supabase or production data; tests run against a throwaway Postgres. When the
> card's "Done when" is met, update the Bit N row in the tracker in the same
> pull request and open it into `Dev`.

### The bits

**Bit 0. Land the groundwork.** *Done in the planning session.*
- A pull request for migration 0014 and the "never grant to `authenticated`" rule
  in CLAUDE.md, ARCHITECTURE.md and SECURITY.md (rule 8).
- A pull request for this plan.
- Done when: both are merged into `Dev`.

**Bit 1. Portal checks in CI.** Read: §11 (last paragraph).
- A new job in `.github/workflows/quality-checks.yml`, working in `portal/`:
  `npm ci`, typecheck, build, `npm audit --omit=dev --audit-level=high`.
- Fix anything it finds, so the job is green before it becomes required.
- Done when: the job is green on the pull request.

**Bit 2. Prove the office email sends on internal.** Read: §9 Emailed code.
- Send one made-up registration on the internal site and confirm it reaches
  admin@induduzo.co.za.
- If it doesn't arrive, find out why from the api logs and fix the settings. The
  mailbox password is pasted by the owner, never typed by an agent.
- Check that SPF, DKIM and DMARC pass in the message headers.
- No code change expected, so no pull request unless something must change.
- Done when: a test email has arrived and its headers pass.

**Bit 3. Database tables, settings and crypto helpers.** Read: §6, §7, §15.
- A migration with the next free number, holding the tables in §6:
  - RLS on;
  - policies for `induduzo_api` only, under a `pg_roles` guard;
  - nothing for `anon` or `authenticated`.
- `config.py`: the `TWO_STEP_*` and `WEBAUTHN_*` settings, with the fail-closed
  and "production refuses `off`" rules.
- A small `services/two_step_crypto.py` that:
  - encrypts and decrypts app secrets (MultiFernet);
  - HMACs codes;
  - hashes device tokens;
  - makes codes.
- Pin `cryptography`, and add `.env.example` entries (placeholders only).
- Unit tests from §11A: crypto, codes and masking.
- Done when: the migration applies on a fresh database in CI, and the unit tests pass.

**Bit 4. Enforcement core and the guard test.** Read: §5; §8 (dependencies, error contract); §11B (fixtures, guard test).
- Split `require_staff` into `require_staff_identity` and the strict
  `require_staff`. Read `session_id` from the token. `StaffUser` gains the new
  fields.
- Session verifications: record and look up, with the 12-hour limit.
- `GET /api/admin/2fa/status` on a new router.
- Test fixtures: `signed_in` (real ES256 tokens), `mailbox` and `clock`.
- The guard test: every `/api/admin` route outside the 2FA allowlist refuses a
  session that hasn't passed the second step.
- `TWO_STEP_ENFORCEMENT` stays **off** in every environment, so nothing changes
  for staff yet.
- Done when: all existing tests pass, and the guard test passes with enforcement
  switched on inside the tests.

**Bit 5. Emailed code (API).** Read: §5 (the code's life), §8, §9 Emailed code.
- `POST /2fa/email/send` and `/2fa/email/verify`, with the limits, replacing of
  old codes, and binding to the session.
- The code email in `services/email.py`: no code in the subject, and sent to the
  staff record's address.
- Failure counting from `staff_events`, and the 15-minute lockout.
- Audit events, with nothing secret in them.
- Done when: every emailed-code test in §11B passes, including "no new email
  after expiry" and "no code in logs".

**Bit 6. Trusted computers, the "Confirm it's you" screen, and enforcement on.** Read: §5; §9 Trusted computers; §10.
- Settle decisions 3 and 4 first.
- API: issue, check and revoke device tokens; add `X-Induduzo-Device` to CORS.
- Portal:
  - the device header and the error `code` in `lib/api.ts`;
  - the gate in `App.tsx`;
  - the "Confirm it's you" screen, with the emailed code and the trust tick-box.
- Turn enforcement **on** for internal, deploy, and check by hand.
- Done when: §11C scenarios 1–4 work by hand on internal, and the
  trusted-computer tests in §11B pass.

**Bit 7. Authenticator app.** Read: §9 Authenticator app, §10.
- API: setup, confirm, verify and remove. Removing needs a recent check.
- Portal: setup in Settings (QR code drawn with `qrcode`), and "Use authenticator
  app" on the "Confirm it's you" screen.
- Done when: the app tests in §11B pass, and Google and Microsoft Authenticator
  both work on internal.

**Bit 8. Passkeys (API).** Read: §9 Passkeys.
- Settle decisions 5 and 6 first.
- `webauthn` 3.x: setup start and finish, sign-in start and verify, rename and
  remove.
- The software passkey helper for tests.
- Done when: every passkey test in §11B passes.

**Bit 9. Passkeys (portal).** Read: §9 Passkeys, §10.
- `@simplewebauthn/browser`: add a passkey in Settings, and "Use your passkey"
  on the "Confirm it's you" screen.
- Done when: a Windows Hello passkey signs in on internal from a real laptop.

**Bit 10. Recovery codes and the security page.** Read: §9 Recovery codes; §10 screens 2 and 3.
- API: make, show once, use and replace.
- Portal: the "Make sign-in stronger" screen, and Settings → Sign-in security.
- Done when: the recovery tests in §11B pass, and the lost-phone drill in §11D
  works.

**Bit 11. Owner tools.** Read: §8 (owner endpoints); §9 Owner reset; §9 Emails to the staff member.
- Owner reset: the endpoint and the Team page column.
- Deactivation revokes trusted computers and sessions.
- The break-glass command.
- Security emails.
- The `purge_two_step` job.
- Done when: the owner tests in §11B pass, and the owner-locked-out drill in §11D
  works.

**Bit 12. Portal security headers.** Read: §10 (last paragraph), §14.
- A CSP and a `Permissions-Policy` for the portal on Railway, keeping passkeys
  allowed. Use a Caddyfile, or a small Caddy image if Railpack ignores one.
- Done when: the headers are checked on the **deployed** internal portal, and
  sign-in, passkeys, Sentry and fonts still work.

**Bit 13. Browser tests in CI.** Read: §11C.
- Spike first: can local Supabase sign ES256 tokens? If not, use the small fake
  auth server.
- A Playwright job with Postgres, Mailpit, the API, the built portal and Chrome's
  virtual passkey. It runs on pull requests into `internal` and `main`.
- Done when: all ten §11C scenarios are green in CI.

**Bit 14. A week on internal, then production.** Read: §11D, §11E, §13.
- The whole team uses internal for a week.
- Work through §11D and §11E, and settle decisions 1 and 2.
- Then the production checklist.
- Done when: nobody is stuck, no lockouts are unresolved, and §13 is ticked.

**Optional. Change password and Forgot password.** After Bit 11.
- Today, staff keep whatever password the owner set, and the Settings page points
  to a reset link that doesn't exist.
- Build both with Supabase's own email flows and redirect URLs.

---

## 13. Production launch checklist
- [ ] `WEBAUTHN_RP_ID=portal.induduzo.co.za`, `WEBAUTHN_ORIGINS=https://portal.induduzo.co.za`
- [ ] Fresh `TWO_STEP_ENCRYPTION_KEYS` and `TWO_STEP_CODE_PEPPER` for production, sealed, never shared with internal
- [ ] `TWO_STEP_ENFORCEMENT=on` (production refuses `off` anyway)
- [ ] `CORS_ORIGINS` is the production portal only, and `X-Induduzo-Device` is allowed
- [ ] Code emails pass SPF, DKIM and DMARC from the production sender
- [ ] Decisions 1 and 2 applied: owners and admins have a passkey or app, and email is off for them
- [ ] Every staff member has set up a method on production (passkeys don't carry over from internal) and stored recovery codes
- [ ] Break-glass drill done on production
- [ ] Portal security headers live and checked on the production URL
- [ ] Supabase: sign-up off, Data API closed, leaked-password protection reviewed (paid plans only)

---

## 14. Risks

| Risk | What happens | Handled by |
|---|---|---|
| Office email down | Emailed codes can't be sent | Passkey, app, recovery code; break-glass for the owner |
| Lost or changed phone | App codes gone | Passkey, recovery code, owner reset |
| Laptop stolen while trusted | Thief still needs the password; trust skips only the second step | Windows sign-in; owner revokes the person's computers; password reset |
| Only owner locked out | Nobody can reset them | Break-glass command in the Railway console |
| Clock drift | App codes off by a step | ±1 step accepted; the API already allows 60 s on tokens |
| Script injected into the portal | Could read the session and device tokens | Strict CSP (Phase 6); React escaping; no `dangerouslySetInnerHTML` |
| Guessing codes | 6 digits, 5 tries per code, 10 failures per 15 min | Odds well under 1 in 10,000 per hour; lockout logged and the owner is emailed |
| A new route forgets protection | Data exposed without the second step | Protection is on the router; the guard test fails CI |
| Someone grants Supabase access again | The API is bypassed | SECURITY.md rule 8; the §11E checklist; check the Supabase advisor |

---

## 15. Do not
- Store or log a code, an app secret, a device token or a recovery code in readable form.
- Put the code in the email subject, or send codes to anything except the staff record's address.
- Send a new code without the person pressing the button.
- Let a method be removed, or recovery codes be replaced, without a fresh second step.
- Use SMS or WhatsApp for codes (cost, SIM-swap risk, and WhatsApp is off).
- Mix in Supabase's own MFA or passkeys. Pick one system: ours (§4).
- Grant anything to Supabase's `authenticated` or `anon` roles on the new tables.
- Trust `X-Forwarded-For` for anything except counting.
