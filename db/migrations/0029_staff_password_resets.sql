-- 0029 - Forgotten staff passwords: an emailed temporary password.
--
-- WHY THIS EXISTS
-- Until now a member of staff who forgot their password had to ask the owner,
-- who reset it in the Supabase dashboard and emailed the new one by hand. The
-- owner asked (16 Nov 2026) for the portal to do this itself: "Forgot your
-- password?" emails a temporary password that works once, and the person
-- types it as the old password beside a new one of their own.
--
-- HOW IT WORKS
-- The API makes the temporary password, keeps only an HMAC of it here (keyed
-- with TWO_STEP_CODE_PEPPER, which the database never sees, exactly like the
-- emailed sign-in codes in 0016), and emails it to the address on the staff
-- record. The person's real Supabase password is NOT changed when the email
-- goes out, so a stranger who types someone's address locks nobody out. Only
-- when the right temporary password comes back with a new password does the
-- API set that new password in Supabase and stamp used_at.
--
-- NOTHING EXPIRED IS STORED AS A FLAG
-- As in 0013 and 0016, a row is dead when used_at, replaced_at, attempts or the
-- clock say so. The API gives a temporary password 30 minutes and five wrong
-- tries; the checks below are headroom, not the limit.
--
-- WHERE IT RUNS
-- Everywhere 0016 runs (it needs staff_users from 0007), Supabase included.
-- induduzo_api gets SELECT, INSERT and UPDATE; no DELETE, as everywhere else.
-- Nothing is granted to anon or authenticated (0026). Safe to run again.

create table if not exists staff_password_resets (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null default '00000000-0000-0000-0000-000000000001',
  staff_user_id  uuid not null references staff_users(id),

  -- HMAC-SHA256 of the temporary password, bound to this row's id. Never the
  -- password itself: anything that is not exactly 32 bytes is refused.
  temp_hash      bytea not null check (octet_length(temp_hash) = 32),

  -- Wrong temporary passwords tried against this row. The API stops at five.
  attempts       smallint not null default 0 check (attempts between 0 and 50),

  created_at     timestamptz not null default now(),   -- when it was emailed
  expires_at     timestamptz not null,
  used_at        timestamptz,   -- the new password was set; never usable again
  replaced_at    timestamptz,   -- a newer one was asked for

  constraint staff_password_resets_short_lived
    check (expires_at > created_at and expires_at <= created_at + interval '2 hours')
);

comment on table staff_password_resets is
  'Emailed one-use temporary passwords for staff who forgot theirs. Holds an HMAC of each, never the password. Dead when used, replaced, tried five times or past expires_at.';

-- A person's recent requests: the live one, and what the hourly limit counts.
create index if not exists staff_password_resets_staff_idx
  on staff_password_resets (staff_user_id, created_at desc);

alter table staff_password_resets enable row level security;

revoke all on staff_password_resets from anon, authenticated;

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  grant select, insert, update on staff_password_resets to induduzo_api;
  drop policy if exists api_rw_password_resets on staff_password_resets;
  create policy api_rw_password_resets on staff_password_resets
    for all to induduzo_api
    using (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');
end
$guard$;
