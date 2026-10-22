-- 0018 - Enrolment: compliance questions, the plan price list, and quarterly
-- and annual premiums.
--
-- WHY THIS EXISTS
-- The owner reviewed the portal's enrolment form on the internal environment
-- (October 2026) and asked for four things that need the schema:
--
--   1. Compliance questions about the main member: country of birth,
--      citizenship, a passport number for those who are not South African,
--      employment, the source of the money that pays the premium, and the day
--      they are paid.
--   2. The premium set by the plan, not typed in. Staff were free to write any
--      amount, so two families on the same plan could be charged differently
--      by accident. The price list now lives here and the API reads it.
--   3. Quarterly and annual premiums beside monthly.
--   4. Which price a policy was sold on (Plan C has several), so the premium on
--      the policy can always be traced back to a line in the price list.
--
-- 0017 is taken by the WhatsApp line move on its own branch; this is 0018.
--
-- NOT HERE, ON PURPOSE
-- No bank account, branch code or card. The enrolment form shows where debit
-- order banking details will go, greyed out; when debit orders go live they are
-- captured by the payment provider, never stored in this database (CLAUDE.md,
-- "No bank or card details, ever").

-- ---------------------------------------------------------------------------
-- Quarterly and annual premiums. Postgres allows ADD VALUE inside the
-- migration's transaction but not using the new value in it, and nothing below
-- does. 'once_off' stays: the Dome Plan is sold once-off, and the website form
-- still sends it.
-- ---------------------------------------------------------------------------
alter type payment_frequency add value if not exists 'quarterly';
alter type payment_frequency add value if not exists 'annually';

-- ---------------------------------------------------------------------------
-- The price list. One row per price a plan can be sold at. Plans A and B have
-- one price; Plan C is priced by coffin, single or couple, and the main
-- member's age band; the Dome Plan is a once-off payment.
--
-- premium_cents is per month when billing is 'monthly' (a quarterly policy
-- pays three months at once, an annual one twelve), or the whole amount when
-- billing is 'once_off'. A policy keeps its OWN premium_cents too: changing a
-- price here must never rewrite what an existing family pays.
-- ---------------------------------------------------------------------------
create table ref_plan_prices (
  id            uuid primary key default gen_random_uuid(),
  plan_code     text not null references ref_plans(code),
  option_code   text not null check (option_code ~ '^[a-z][a-z0-9_]{1,39}$'),
  option_label  text not null,
  -- The main member's age on the policy start date. Null means no limit.
  min_age       smallint check (min_age is null or min_age between 0 and 120),
  max_age       smallint check (max_age is null or max_age between 0 and 120),
  premium_cents bigint not null check (premium_cents >= 0),
  currency      char(3) not null default 'ZAR',
  billing       text not null check (billing in ('monthly', 'once_off')),
  sort_order    smallint not null default 100,
  is_active     boolean not null default true,

  constraint ref_plan_prices_age_band_in_order
    check (min_age is null or max_age is null or min_age <= max_age)
);

comment on table ref_plan_prices is
  'What each plan costs. premium_cents is per month for monthly billing, or the whole amount for once-off. Policies copy their premium from here at enrolment and keep it.';

-- One price per plan, option and age band.
create unique index ref_plan_prices_band_idx
  on ref_plan_prices (plan_code, option_code, coalesce(min_age, -1))
  where is_active;

-- The published prices on induduzo.co.za (frontend/src/data/plans.ts).
insert into ref_plan_prices
  (plan_code, option_code, option_label, min_age, max_age, premium_cents, billing, sort_order)
values
  ('plan_a',    'standard',        'Plan A (Urban)',            null, null, 35000, 'monthly',  10),
  ('plan_b',    'standard',        'Plan B (Emakhaya)',         null, null, 25000, 'monthly',  20),
  ('plan_c',    'single_flat_lid', 'Single member, flat lid',     21,   45,  5000, 'monthly',  30),
  ('plan_c',    'single_flat_lid', 'Single member, flat lid',     46,   59,  6000, 'monthly',  31),
  ('plan_c',    'single_flat_lid', 'Single member, flat lid',     60,   75,  8000, 'monthly',  32),
  ('plan_c',    'single_flat_lid', 'Single member, flat lid',     76,   85, 12000, 'monthly',  33),
  ('plan_c',    'single_casket',   'Single member, casket',       21,   45, 15000, 'monthly',  34),
  ('plan_c',    'single_casket',   'Single member, casket',       46,   59, 18000, 'monthly',  35),
  ('plan_c',    'single_casket',   'Single member, casket',       60,   75, 20000, 'monthly',  36),
  ('plan_c',    'single_casket',   'Single member, casket',       76,   85, 25000, 'monthly',  37),
  ('plan_c',    'couple_flat_lid', 'Couple, flat lid',            21,   45, 10000, 'monthly',  38),
  ('plan_c',    'couple_flat_lid', 'Couple, flat lid',            46,   59, 20000, 'monthly',  39),
  ('dome_plan', 'once_off',        'Dome Plan, once-off',       null, null, 40000, 'once_off', 40);

-- The plan catalogue's headline price, where a plan has exactly one.
update ref_plans set premium_cents = 35000 where code = 'plan_a' and premium_cents is null;
update ref_plans set premium_cents = 25000 where code = 'plan_b' and premium_cents is null;

-- Which price a policy was sold on. Null for the policies that came in by
-- import, which were priced on paper.
alter table policies
  add column plan_option text check (plan_option is null or plan_option ~ '^[a-z][a-z0-9_]{1,39}$');

-- ---------------------------------------------------------------------------
-- Compliance questions about a person. Asked of the main member at enrolment;
-- null for everyone else and for the imported book. The lists of allowed
-- values live in the API (backend/app/routers/members.py), except where a
-- wrong value would be a real data problem.
--
-- A passport number is as sensitive as an ID number: never logged, never put
-- in a URL or a message.
-- ---------------------------------------------------------------------------
alter table people
  -- ISO 3166 two-letter codes. 'ZA' is South Africa.
  add column country_of_birth   char(2) check (country_of_birth ~ '^[A-Z]{2}$'),
  add column citizenship        char(2) check (citizenship ~ '^[A-Z]{2}$'),
  -- Upper case letters and digits only, so 'a1234567' and 'A 123 4567' are one.
  add column passport_number    text check (passport_number is null
                                            or passport_number ~ '^[A-Z0-9]{5,20}$'),

  add column employment_status  text check (employment_status in (
                                  'full_time', 'part_time', 'pensioner',
                                  'self_employed', 'unemployed')),
  add column employer_name      text check (length(trim(employer_name)) between 1 and 150),
  add column industry           text check (length(trim(industry)) between 1 and 80),
  add column occupation         text check (length(trim(occupation)) between 1 and 100),
  add column job_role           text check (length(trim(job_role)) between 1 and 60),

  add column source_of_funds    text check (source_of_funds in (
                                  'employment', 'inheritance', 'allowance',
                                  'pension', 'other')),
  add column source_of_funds_other text check (length(trim(source_of_funds_other))
                                                between 1 and 150),
  -- 31 means the last day of the month, whatever its length.
  add column salary_day         smallint check (salary_day between 1 and 31),

  -- South Africans are identified by their ID number, not a passport.
  add constraint people_passport_only_for_non_citizens
    check (passport_number is null or citizenship is distinct from 'ZA'),
  add constraint people_employer_only_when_working
    check ((employer_name is null and industry is null and job_role is null)
           or employment_status in ('full_time', 'part_time', 'self_employed')),
  add constraint people_other_funds_explained
    check (source_of_funds_other is null or source_of_funds = 'other');

comment on column people.passport_number is
  'Only for people who are not South African citizens. POPIA-protected like id_number: never logged.';
comment on column people.salary_day is
  'Day of the month the person is paid, 1-31. 31 means the last day of the month.';

-- The same passport is the same person, as with ID numbers in 0009.
create unique index people_passport_idx on people (citizenship, passport_number)
  where passport_number is not null and archived_at is null;

-- ---------------------------------------------------------------------------
-- Access: the API only. Reference data carries no tenant, as in 0008. The
-- price list changes by migration, so the API may read it but not write it.
-- ---------------------------------------------------------------------------
alter table ref_plan_prices enable row level security;
revoke all on ref_plan_prices from anon, authenticated;

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  grant select on ref_plan_prices to induduzo_api;

  drop policy if exists api_read_plan_prices on ref_plan_prices;
  create policy api_read_plan_prices
    on ref_plan_prices for select
    to induduzo_api
    using (true);
end
$guard$;
