-- 0008 - Reference tables (the "PK tables").
--
-- WHY THIS EXISTS
-- Until now every categorical value lived in a Postgres enum. Enums are right
-- when the list is fixed and owned by developers (enquiry_stage), and wrong
-- when the office needs to add a branch or retire a product without waiting
-- for a deployment. These tables are the ones real rows point AT.
--
-- The primary key is a short text code, not a uuid, deliberately:
--
--   * a CSV export reads 'main_member', not 'a3f1...'. The office can check it.
--   * moving data between environments needs no id remapping.
--   * a foreign key violation names the value that was actually wrong.
--
-- Every one of these is small, slow-changing, and contains no personal
-- information.

-- ---------------------------------------------------------------------------
-- Types used by the core tables in 0009/0010.
-- ---------------------------------------------------------------------------

-- Derived from digits 7-10 of a South African ID number (>= 5000 is male).
-- 'unspecified' is the honest answer when there is no usable ID number.
create type gender as enum ('male', 'female', 'unspecified');

-- The import carried real ID numbers that fail their own checksum. Silently
-- correcting or dropping those would lose client records, so the number is
-- kept verbatim and its trustworthiness is recorded beside it.
create type id_number_status as enum (
  'valid',            -- 13 digits, checksum passes
  'checksum_failed',  -- 13 digits, checksum does not pass
  'malformed',        -- present but not 13 digits
  'missing'           -- not supplied
);

create type phone_type as enum ('mobile', 'home', 'work', 'whatsapp', 'other');

create type address_type as enum ('residential', 'postal');

-- ---------------------------------------------------------------------------
-- Shared shape for every reference table.
-- ---------------------------------------------------------------------------
--   code        stable machine value, used as the foreign key
--   label       what staff see
--   sort_order  because alphabetical is rarely the useful order
--   is_active   retire a value without breaking rows that already point at it

create table ref_member_types (
  code        text primary key check (code ~ '^[a-z][a-z0-9_]{1,39}$'),
  label       text not null,
  sort_order  smallint not null default 100,
  is_active   boolean not null default true
);

comment on table ref_member_types is
  'Role a person holds on a policy. The spreadsheet Type column maps here.';

-- 'unspecified' is not padding. The 2026 import file had a Type column that was
-- filled on 2 of 61 rows, and both of those contained a first name rather than
-- a type. Guessing spouse-vs-child from a surname would invent facts about real
-- families, so those lives land here and are listed in data_quality_flags for
-- the office to correct from the paper application forms.
insert into ref_member_types (code, label, sort_order) values
  ('main_member', 'Main member',     10),
  ('spouse',      'Spouse',          20),
  ('child',       'Child',           30),
  ('extended',    'Extended family', 40),
  ('beneficiary', 'Beneficiary',     50),
  ('unspecified', 'Not yet recorded', 90);

create table ref_policy_statuses (
  code        text primary key check (code ~ '^[a-z][a-z0-9_]{1,39}$'),
  label       text not null,
  -- A policy in a terminal state is not chased for premiums and cannot claim.
  is_terminal boolean not null default false,
  sort_order  smallint not null default 100,
  is_active   boolean not null default true
);

comment on table ref_policy_statuses is
  'Lifecycle position of a policy. is_terminal marks the states that end cover.';

insert into ref_policy_statuses (code, label, is_terminal, sort_order) values
  ('pending',   'Pending',   false, 10),
  ('active',    'Active',    false, 20),
  ('lapsed',    'Lapsed',    false, 30),
  ('cancelled', 'Cancelled', true,  40),
  ('claimed',   'Claimed',   true,  50);

create table ref_plans (
  code          text primary key check (code ~ '^[a-z][a-z0-9_]{1,39}$'),
  label         text not null,
  description   text,
  -- Published figures for the plan. A policy stores its OWN premium and cover
  -- as well, because what a family actually pays can differ from the list
  -- price, and history must not be rewritten when a price changes.
  cover_cents   bigint check (cover_cents   is null or cover_cents   >= 0),
  premium_cents bigint check (premium_cents is null or premium_cents >= 0),
  currency      char(3) not null default 'ZAR',
  sort_order    smallint not null default 100,
  is_active     boolean not null default true
);

comment on table ref_plans is
  'Product catalogue. Codes match the plan_code enum used by plan_enquiries, so a lead plan_interest lines up with the policy it eventually becomes.';

insert into ref_plans (code, label, sort_order) values
  ('plan_a',    'Plan A',    10),
  ('plan_b',    'Plan B',    20),
  ('plan_c',    'Plan C',    30),
  ('dome_plan', 'Dome Plan', 40);

create table ref_branches (
  code       text primary key check (code ~ '^[a-z][a-z0-9_]{1,39}$'),
  label      text not null,
  town       text,
  province   text,
  sort_order smallint not null default 100,
  is_active  boolean not null default true
);

comment on table ref_branches is
  'Office a policy was written at. Seeded from the Branch column of the import.';

insert into ref_branches (code, label, town, province, sort_order) values
  ('pmburg', 'Pietermaritzburg', 'Pietermaritzburg', 'KwaZulu-Natal', 10);

create table ref_benefit_types (
  code        text primary key check (code ~ '^[a-z][a-z0-9_]{1,39}$'),
  label       text not null,
  description text,
  sort_order  smallint not null default 100,
  is_active   boolean not null default true
);

comment on table ref_benefit_types is
  'Supplementary benefits that attach to a policy, e.g. grocery or tombstone cover. Seeded empty: the import file carried no real benefit rows.';

-- ---------------------------------------------------------------------------
-- Access. Reference data is not personal information, but it is still only
-- readable by someone already signed in. The public site has no reason to
-- enumerate our product catalogue straight out of the database.
-- ---------------------------------------------------------------------------
alter table ref_member_types    enable row level security;
alter table ref_policy_statuses enable row level security;
alter table ref_plans           enable row level security;
alter table ref_branches        enable row level security;
alter table ref_benefit_types   enable row level security;

create policy staff_read_member_types    on ref_member_types    for select to authenticated using (true);
create policy staff_read_policy_statuses on ref_policy_statuses for select to authenticated using (true);
create policy staff_read_plans           on ref_plans           for select to authenticated using (true);
create policy staff_read_branches        on ref_branches        for select to authenticated using (true);
create policy staff_read_benefit_types   on ref_benefit_types   for select to authenticated using (true);

grant select on ref_member_types, ref_policy_statuses, ref_plans,
                ref_branches, ref_benefit_types
  to authenticated;

-- The API role only exists once 0005 has been applied. On Supabase it has not
-- been, so guard the grants rather than failing the whole migration.
do $guard$
begin
  if exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    grant select, insert, update on ref_member_types, ref_policy_statuses,
                                    ref_plans, ref_branches, ref_benefit_types
      to induduzo_api;

    create policy api_rw_member_types    on ref_member_types    for all to induduzo_api using (true) with check (true);
    create policy api_rw_policy_statuses on ref_policy_statuses for all to induduzo_api using (true) with check (true);
    create policy api_rw_plans           on ref_plans           for all to induduzo_api using (true) with check (true);
    create policy api_rw_branches        on ref_branches        for all to induduzo_api using (true) with check (true);
    create policy api_rw_benefit_types   on ref_benefit_types   for all to induduzo_api using (true) with check (true);
  end if;
end
$guard$;
