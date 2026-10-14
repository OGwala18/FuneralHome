-- 0009 - People, and how to reach them.
--
-- WHY THIS EXISTS
-- plan_enquiries stores a person and their enquiry in one wide row. That is
-- correct for a web form (one submission, one row, never edited) and wrong for
-- a book of business, where the SAME human being appears on several policies,
-- changes their phone number, and must still be findable afterwards.
--
-- `people` is the single row per human. Everything else in 0010 points at it.
--
-- ON PHONE NUMBERS
-- A phone number is not an attribute of a person, it is a small table of its
-- own, because:
--
--   * people have more than one (a cell and a work line, or a neighbour's);
--   * numbers change, and the old one must stay searchable for a while;
--   * the office's real query is the REVERSE one. A family phones in and the
--     question is "who is this?" - hence person_phones_number_idx.
--
-- This table is created empty. The 2026 import file carried no phone numbers
-- at all, and that gap is recorded in data_quality_flags by 0011.

create table people (
  -- Skeleton required on every business table (AIA foundation 03 section 5.1)
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  archived_at   timestamptz,

  -- ---------- Identity ----------
  surname       text not null check (length(trim(surname))     between 1 and 100),
  first_names   text not null check (length(trim(first_names)) between 1 and 150),
  initials      text check (initials is null or length(trim(initials)) <= 10),
  preferred_name text,

  -- Digits only, so that '770605 1535 081' and '7706051535081' are one person.
  id_number        text check (id_number is null or id_number ~ '^[0-9]{6,13}$'),
  -- Exactly as it arrived. An import must never be the only place the original
  -- value existed; when a checksum fails, staff need to see what was typed.
  id_number_raw    text,
  id_number_status id_number_status not null default 'missing',

  date_of_birth    date check (date_of_birth is null or date_of_birth <= current_date),
  -- 'supplied' - came from the DOB column. 'derived_from_id' - decoded from the
  -- ID number because no DOB was given. Knowing which matters at claim time.
  date_of_birth_source text check (date_of_birth_source in ('supplied', 'derived_from_id')),

  gender        gender not null default 'unspecified',

  email         text check (email is null or email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  language_preference preferred_language not null default 'zu',

  -- Where this row came from: 'import:funeral_policy_template1', 'website', ...
  source        text not null default 'manual',
  notes         text
);

comment on table people is
  'One row per human being. The single identity all policies, members and contacts point at. Contains POPIA-protected personal information.';
comment on column people.id_number_raw is
  'The ID number exactly as supplied, including spaces and errors. Kept so a failed checksum can be investigated against the original document.';

-- Verified against the source file: 55 thirteen-digit and 2 twelve-digit ID
-- numbers, no duplicates. A collision here means a genuine data problem.
create unique index people_id_number_idx on people (id_number)
  where id_number is not null and archived_at is null;

-- The two searches the office actually performs.
create index people_surname_idx on people (lower(surname), lower(first_names))
  where archived_at is null;
create index people_dob_idx on people (date_of_birth)
  where archived_at is null;
-- Flag-chasing queue: "which records still need a usable ID number?"
create index people_id_status_idx on people (id_number_status)
  where id_number_status <> 'valid' and archived_at is null;

create trigger people_set_updated_at
  before update on people
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Phone numbers. The most important thing in this schema, per the office.
-- ---------------------------------------------------------------------------
create table person_phones (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  archived_at timestamptz,

  person_id   uuid not null references people(id) on delete cascade,

  phone_type  phone_type not null default 'mobile',

  -- Stored E.164 so Twilio can dial it and two spellings of one number cannot
  -- become two rows. '0841451245' is stored as '+27841451245'.
  number      text not null check (number ~ '^\+[1-9][0-9]{7,14}$'),
  -- What the office actually typed or the old system actually held.
  number_raw  text,

  is_primary  boolean not null default false,
  -- Not the same as phone_type='whatsapp': a mobile is usually reachable on
  -- WhatsApp too, and the confirmation flow needs to know which numbers are.
  is_whatsapp boolean not null default false,

  -- Set once a human has actually spoken to someone on this number.
  verified_at timestamptz,
  source      text not null default 'manual',
  notes       text
);

comment on table person_phones is
  'Phone numbers, E.164 normalised, many per person. Created empty: the 2026 policy import supplied no phone numbers.';

-- One number recorded once per person.
create unique index person_phones_unique_idx on person_phones (person_id, number)
  where archived_at is null;
-- At most one primary number per person.
create unique index person_phones_primary_idx on person_phones (person_id)
  where is_primary and archived_at is null;
-- The reverse lookup: an unknown number rings the office, who is it?
create index person_phones_number_idx on person_phones (number)
  where archived_at is null;

create trigger person_phones_set_updated_at
  before update on person_phones
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Addresses. Also many-per-person: residential and postal genuinely differ.
-- ---------------------------------------------------------------------------
create table addresses (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  archived_at  timestamptz,

  person_id    uuid not null references people(id) on delete cascade,
  address_type address_type not null default 'residential',

  line1        text,
  line2        text,
  suburb       text,
  city         text,
  province     text,
  postal_code  text check (postal_code is null or postal_code ~ '^[0-9]{4}$'),
  country      char(2) not null default 'ZA',

  is_primary   boolean not null default false
);

comment on table addresses is
  'Residential and postal addresses. Created empty: the 2026 policy import supplied no addresses.';

create unique index addresses_primary_idx on addresses (person_id, address_type)
  where is_primary and archived_at is null;
create index addresses_person_idx on addresses (person_id)
  where archived_at is null;

create trigger addresses_set_updated_at
  before update on addresses
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Access. These three tables are ALL personal information. The public site
-- gets nothing: no select, no insert, no policy at all for anon.
-- ---------------------------------------------------------------------------
alter table people        enable row level security;
alter table person_phones enable row level security;
alter table addresses     enable row level security;

create policy staff_read_people on people for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_write_people on people for update to authenticated
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

create policy staff_read_phones on person_phones for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_write_phones on person_phones for update to authenticated
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

create policy staff_read_addresses on addresses for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_write_addresses on addresses for update to authenticated
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

grant select, update on people, person_phones, addresses to authenticated;

revoke all on people, person_phones, addresses from anon;

do $guard$
begin
  if exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    grant select, insert, update on people, person_phones, addresses to induduzo_api;

    create policy api_rw_people on people for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
    create policy api_rw_phones on person_phones for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
    create policy api_rw_addresses on addresses for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
  end if;
end
$guard$;
