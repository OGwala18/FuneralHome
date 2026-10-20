-- 0016 - Staff two-step sign-in.
--
-- WHY THIS EXISTS
-- A staff password alone opens the portal, and with it every member's name,
-- phone and ID number. docs/feature-2-staff-two-factor.md adds a second step
-- after the password: a passkey, an authenticator app, or a code emailed to the
-- address on the staff record. A computer the person chooses to trust skips the
-- second step for 30 days. These tables hold what that needs. Nothing reads them
-- yet, and nothing changes for staff until enforcement is switched on.
--
-- NOTHING READABLE IS STORED
-- An emailed or recovery code is kept only as an HMAC, keyed with a pepper the
-- database never sees, and a trusted-computer token only as its SHA-256 hash.
-- Both are 32 bytes and the checks below refuse anything else, so a code or a
-- token written in readable form by mistake is an error, not a row. An
-- authenticator app's secret is stored encrypted, and wiped when the app is
-- removed. backend/app/services/two_step_crypto.py does all of this.
--
-- NOTHING EXPIRED IS STORED AS A FLAG
-- As with overdue premiums in 0013, "expired" is worked out from the clock when
-- someone asks. A code keeps expires_at, used_at, replaced_at and attempts, and
-- is dead if any one of them says so. A flag can be left wrong when something
-- fails to update it. The clock can't.
--
-- WHERE IT RUNS
-- Needs staff_users from 0007. Like 0013, it is not for Supabase until 0005 and
-- 0007 are applied there (CLAUDE.md, "Supabase tracks migrations separately").

-- ---------------------------------------------------------------------------
-- A random handle per person that passkeys carry instead of the email or our
-- row id, so a passkey says nothing about whose it is. Set the first time the
-- person adds a passkey. WebAuthn allows at most 64 bytes.
-- ---------------------------------------------------------------------------
alter table staff_users
  add column webauthn_user_handle bytea unique
    check (octet_length(webauthn_user_handle) between 16 and 64);

-- ---------------------------------------------------------------------------
-- Short-lived, single-use challenges: an emailed code, or the random challenge
-- a passkey signs. Each belongs to one person and one Supabase session, so a
-- code asked for on one computer fails on another.
-- ---------------------------------------------------------------------------
create table staff_mfa_challenges (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id      uuid not null references staff_users(id),

  -- The session_id in the Supabase token it was asked for with.
  session_id         uuid not null,
  kind               text not null check (kind in
                       ('email_code', 'passkey_sign_in', 'passkey_setup')),

  -- HMAC of the emailed code. Never the code.
  code_hash          bytea check (octet_length(code_hash) = 32),
  webauthn_challenge bytea check (octet_length(webauthn_challenge) >= 16),

  -- Wrong guesses so far. The API stops at five.
  attempts           smallint not null default 0 check (attempts >= 0),

  created_at         timestamptz not null default now(),   -- when it was asked for
  expires_at         timestamptz not null,
  used_at            timestamptz,   -- verified, so it can never be used again
  replaced_at        timestamptz,   -- a newer one was asked for

  constraint staff_mfa_challenges_code_only_for_email
    check ((kind = 'email_code') = (code_hash is not null)),
  constraint staff_mfa_challenges_challenge_only_for_passkeys
    check ((kind <> 'email_code') = (webauthn_challenge is not null)),
  -- The API gives codes and passkey challenges five minutes. This is headroom
  -- for it, not the limit: it stops a units mistake making a code that lasts
  -- all day.
  constraint staff_mfa_challenges_short_lived
    check (expires_at <= created_at + interval '15 minutes')
);

comment on table staff_mfa_challenges is
  'Emailed codes and passkey challenges for the staff second step. Single use; expiry is derived from expires_at, used_at, replaced_at and attempts, never stored. Holds an HMAC of each code, never the code.';

-- A person's recent challenges: what the hourly limit on sending codes counts.
create index staff_mfa_challenges_staff_idx
  on staff_mfa_challenges (staff_user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Authenticator apps (Google or Microsoft Authenticator). The API encrypts the
-- secret with TWO_STEP_ENCRYPTION_KEYS before it reaches this table.
-- ---------------------------------------------------------------------------
create table staff_totp_factors (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id    uuid not null references staff_users(id),

  name             text not null default 'Authenticator app'
                     check (length(trim(name)) between 1 and 80),
  secret_encrypted bytea,

  -- Pending until the person enters a correct code, then active until removed.
  status           text not null default 'pending'
                     check (status in ('pending', 'active', 'removed')),
  -- The last 30-second step a code was accepted for, so the same code can't
  -- work twice.
  last_used_step   bigint,

  created_at       timestamptz not null default now(),
  confirmed_at     timestamptz,
  last_used_at     timestamptz,
  removed_at       timestamptz,
  removed_by       text,   -- staff email, or 'system'

  -- Removing an app wipes its secret rather than just flagging the row, and
  -- an app that isn't removed still has one.
  constraint staff_totp_factors_secret_wiped_on_removal
    check ((status = 'removed') = (secret_encrypted is null)),
  constraint staff_totp_factors_removed_has_date
    check ((status = 'removed') = (removed_at is not null)),
  constraint staff_totp_factors_active_was_confirmed
    check (status <> 'active' or confirmed_at is not null)
);

comment on table staff_totp_factors is
  'Authenticator apps for the staff second step. The secret is encrypted by the API, and wiped when the app is removed.';

create index staff_totp_factors_staff_idx
  on staff_totp_factors (staff_user_id)
  where removed_at is null;

-- ---------------------------------------------------------------------------
-- Passkeys: Windows Hello on a work laptop, or one a password manager syncs.
-- Only the public key is here. The private key never leaves the device.
-- ---------------------------------------------------------------------------
create table staff_passkeys (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id   uuid not null references staff_users(id),

  credential_id   bytea not null unique,
  public_key      bytea not null,
  -- The authenticator's signature counter. One that goes backwards may mean a
  -- cloned passkey. Synced passkeys always report 0.
  sign_count      bigint not null default 0 check (sign_count >= 0),
  transports      text[] not null default '{}',
  aaguid          uuid,                -- the authenticator model, if it says
  backup_eligible boolean not null,    -- true: it can sync to other devices
  backed_up       boolean not null,
  name            text not null check (length(trim(name)) between 1 and 80),

  created_at      timestamptz not null default now(),
  last_used_at    timestamptz,
  removed_at      timestamptz,
  removed_by      text
);

comment on table staff_passkeys is
  'Passkeys for the staff second step: public keys and counters only.';

create index staff_passkeys_staff_idx
  on staff_passkeys (staff_user_id)
  where removed_at is null;

-- ---------------------------------------------------------------------------
-- Computers a person chose to trust. The browser keeps a random 32-byte token
-- and sends it as X-Induduzo-Device. Only its SHA-256 hash is here, so a copy
-- of this table can't be replayed as a trusted computer. Trust lasts at most
-- 30 days from when it was given, and using the computer doesn't extend it.
-- ---------------------------------------------------------------------------
create table staff_trusted_devices (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id uuid not null references staff_users(id),

  token_hash    bytea not null unique check (octet_length(token_hash) = 32),
  -- "Chrome on Windows". For the person to recognise it in Settings, nothing more.
  label         text not null check (length(trim(label)) between 1 and 120),

  created_at    timestamptz not null default now(),
  expires_at    timestamptz not null,
  last_used_at  timestamptz,
  revoked_at    timestamptz,
  revoked_by    text,

  constraint staff_trusted_devices_thirty_days_at_most
    check (expires_at <= created_at + interval '30 days')
);

comment on table staff_trusted_devices is
  'Computers trusted to skip the staff second step for up to 30 days. Holds the SHA-256 hash of each device token, never the token.';

create index staff_trusted_devices_staff_idx
  on staff_trusted_devices (staff_user_id)
  where revoked_at is null;

-- ---------------------------------------------------------------------------
-- "This session passed the second step, until <time>." A Supabase session id
-- stays the same across token refreshes until the person signs out, so a new
-- sign-in is asked again unless the computer is trusted.
-- ---------------------------------------------------------------------------
create table staff_session_verifications (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id uuid not null references staff_users(id),

  session_id    uuid not null,
  method        text not null check (method in
                  ('email_code', 'authenticator_app', 'passkey',
                   'recovery_code', 'trusted_device')),

  verified_at   timestamptz not null default now(),
  expires_at    timestamptz not null,
  -- Cut short by an owner's reset or by deactivation. Set, not deleted, so the
  -- row still says when and how the session passed.
  revoked_at    timestamptz
);

comment on table staff_session_verifications is
  'Supabase sessions that passed the staff second step, and until when.';

-- The question every staff request asks: has this session passed?
create index staff_session_verifications_session_idx
  on staff_session_verifications (session_id, staff_user_id, expires_at desc);
-- A person's history, and revoking all of it at once.
create index staff_session_verifications_staff_idx
  on staff_session_verifications (staff_user_id, verified_at desc);

-- ---------------------------------------------------------------------------
-- One-time recovery codes, for a lost phone or laptop. Ten at a time, shown
-- once, stored as HMACs. A new set replaces the whole of the old batch.
-- ---------------------------------------------------------------------------
create table staff_recovery_codes (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id uuid not null references staff_users(id),

  batch_id      uuid not null,
  code_hash     bytea not null check (octet_length(code_hash) = 32),

  created_at    timestamptz not null default now(),
  used_at       timestamptz,
  replaced_at   timestamptz
);

comment on table staff_recovery_codes is
  'One-time recovery codes for the staff second step. Holds an HMAC of each code, never the code.';

-- The codes a person can still use.
create index staff_recovery_codes_staff_idx
  on staff_recovery_codes (staff_user_id)
  where used_at is null and replaced_at is null;

-- ---------------------------------------------------------------------------
-- Access: the API only (SECURITY.md rule 8). Nothing for anon or
-- authenticated. The revoke matters on Supabase, whose default privileges give
-- both roles every new table. staff_users now holds the passkey handle and
-- staff_events will hold the two-step audit trail, so they are closed too. On
-- a database built from these migrations, that part changes nothing.
-- ---------------------------------------------------------------------------
alter table staff_mfa_challenges        enable row level security;
alter table staff_totp_factors          enable row level security;
alter table staff_passkeys              enable row level security;
alter table staff_trusted_devices       enable row level security;
alter table staff_session_verifications enable row level security;
alter table staff_recovery_codes        enable row level security;

revoke all on staff_mfa_challenges, staff_totp_factors, staff_passkeys,
              staff_trusted_devices, staff_session_verifications,
              staff_recovery_codes, staff_users, staff_events
  from anon, authenticated;

-- No DELETE, as everywhere else for this role. Removing a method, forgetting a
-- computer and using a code are all timestamps. The housekeeping job in the
-- plan (purge_two_step) will need DELETE on challenges, verifications and
-- devices; that is its own decision, in its own migration.
do $guard$
declare
  tables   text[] := array['staff_mfa_challenges', 'staff_totp_factors',
                           'staff_passkeys', 'staff_trusted_devices',
                           'staff_session_verifications', 'staff_recovery_codes'];
  policies text[] := array['api_rw_mfa_challenges', 'api_rw_totp_factors',
                           'api_rw_passkeys', 'api_rw_trusted_devices',
                           'api_rw_session_verifications', 'api_rw_recovery_codes'];
  i int;
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  for i in 1 .. array_length(tables, 1) loop
    execute format('grant select, insert, update on %I to induduzo_api', tables[i]);
    execute format('drop policy if exists %I on %I', policies[i], tables[i]);
    execute format(
      'create policy %I on %I for all to induduzo_api '
      'using (tenant_id = %L) with check (tenant_id = %L)',
      policies[i], tables[i],
      '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001');
  end loop;
end
$guard$;
