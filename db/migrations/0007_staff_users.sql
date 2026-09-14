-- 0007 - Staff accounts and roles.
--
-- Supabase Auth proves WHO someone is. This table decides WHAT they may do.
-- Keeping authorisation here rather than in Supabase user metadata means:
--
--   * role changes are ordinary rows we can audit, back up and restore;
--   * the API is the single authority, so a compromised Supabase project
--     cannot grant itself privileges in our system;
--   * a person can be revoked instantly without touching the auth provider.

create type staff_role as enum (
  'viewer',  -- read enquiries only
  'admin',   -- read and edit enquiries
  'owner'    -- everything, plus managing staff accounts
);

create table staff_users (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null default '00000000-0000-0000-0000-000000000001',

  -- Stored lower-case; the unique index enforces one row per person
  -- regardless of how they type their address.
  email             text not null check (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  full_name         text,
  role              staff_role not null default 'viewer',

  -- Revocation is a flag, not a delete: the audit trail must keep pointing at
  -- a real person after they leave.
  is_active         boolean not null default true,

  -- Filled in on first successful sign-in, linking this row to the Supabase
  -- account. Null means invited but never signed in.
  supabase_user_id  uuid,

  invited_by        text,
  last_seen_at      timestamptz,

  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  archived_at       timestamptz
);

create unique index staff_users_email_idx on staff_users (lower(email))
  where archived_at is null;
create index staff_users_active_idx on staff_users (is_active, role)
  where archived_at is null;

comment on table staff_users is
  'Employee accounts for the staff portal. Authentication is delegated to Supabase; this table is the authority on authorisation.';

create trigger staff_users_set_updated_at
  before update on staff_users
  for each row execute function set_updated_at();

-- Staff changes are security-relevant, so they get their own append-only log
-- rather than sharing the enquiry event stream.
create table staff_events (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null default '00000000-0000-0000-0000-000000000001',
  actor_email text not null,
  event_type  text not null,   -- staff_invited, role_changed, staff_deactivated, ...
  subject     text,            -- the account acted upon
  payload     jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create index staff_events_created_idx on staff_events (created_at desc);

create rule staff_events_no_update as on update to staff_events do instead nothing;
create rule staff_events_no_delete as on delete to staff_events do instead nothing;

comment on table staff_events is
  'Append-only record of staff account changes. No UPDATE or DELETE is granted to any role.';

alter table staff_users  enable row level security;
alter table staff_events enable row level security;

-- The API role manages both. There is deliberately no anon policy: the public
-- site must never see that these tables exist.
grant select, insert, update on staff_users  to induduzo_api;
grant select, insert         on staff_events to induduzo_api;

create policy api_rw_staff
  on staff_users for all
  to induduzo_api
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

create policy api_rw_staff_events
  on staff_events for all
  to induduzo_api
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');
