-- 0010 - Policies, and the lives covered by them (the "FK tables").
--
-- WHY THIS EXISTS
-- The import spreadsheet is one row per LIFE, with the policy number, entry
-- date and premium written once on the first life of each family and left
-- blank down the rest. That shape is fine for a human filling in Excel and
-- unusable as storage: the premium of a policy is not a property of whichever
-- family member happened to be typed first.
--
-- So it splits in two:
--
--   policies          one row per policy   - number, dates, money, product
--   policy_members    one row per life     - who is covered, and as what
--
-- policy_members is the junction table. It is what makes the same person able
-- to appear on their own policy and on their mother's without being stored
-- twice, which is the thing that was impossible before.

create table policies (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  archived_at   timestamptz,

  -- Normalised: no spaces, upper case. The file contained both 'AA 1324' and
  -- 'AA1324' for what is plainly one policy.
  policy_number     text not null check (policy_number ~ '^[A-Z0-9][A-Z0-9-]{1,29}$'),
  -- As written on the paper file, so staff can match what they are holding.
  policy_number_raw text,

  status_code   text not null default 'active'  references ref_policy_statuses(code),
  plan_code     text                            references ref_plans(code),
  branch_code   text                            references ref_branches(code),

  entry_date    date,

  -- Money as integer minor units + explicit currency (AIA 03 section 5.2).
  -- Never a float: R250.00 is 25000, not 250.0.
  premium_cents bigint check (premium_cents is null or premium_cents >= 0),
  cover_cents   bigint check (cover_cents   is null or cover_cents   >= 0),
  currency      char(3) not null default 'ZAR',

  -- The conversion link. A policy that began life as a website enquiry keeps a
  -- pointer back to it, so the funnel can be measured end to end. Null for the
  -- book of business that predates the website.
  enquiry_id    uuid references plan_enquiries(id) on delete set null,

  source        text not null default 'manual',
  notes         text
);

comment on table policies is
  'One row per funeral policy. Money is held in integer cents. Deliberately contains no bank account, branch code or card data - see 0010 policy_payments.';

create unique index policies_number_idx on policies (policy_number)
  where archived_at is null;
create index policies_status_idx on policies (status_code)
  where archived_at is null;
create index policies_entry_date_idx on policies (entry_date desc);
-- Enquiry-to-policy conversion lookups.
create index policies_enquiry_idx on policies (enquiry_id)
  where enquiry_id is not null;

create trigger policies_set_updated_at
  before update on policies
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- The junction. One row per life covered by a policy.
-- ---------------------------------------------------------------------------
create table policy_members (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  archived_at timestamptz,

  -- Delete a policy and its membership rows go with it; the PEOPLE stay.
  policy_id   uuid not null references policies(id) on delete cascade,
  -- A person who is covered by a policy cannot be deleted out from under it.
  person_id   uuid not null references people(id)   on delete restrict,

  member_type text not null default 'unspecified' references ref_member_types(code),

  -- Age at which this life joined, straight from the EntryAge column. Kept as
  -- recorded rather than recomputed: underwriting priced on this number.
  entry_age   smallint check (entry_age is null or entry_age between 0 and 120),

  joined_at   date,
  left_at     date check (left_at is null or joined_at is null or left_at >= joined_at),

  -- True when member_type was worked out by the importer rather than stated on
  -- the source document. Anything true here is a question for the office.
  is_inferred boolean not null default false,

  notes       text
);

comment on table policy_members is
  'Junction table: which people are covered by which policy, and in what role. The same person may appear on several policies.';
comment on column policy_members.is_inferred is
  'member_type was derived by the importer (e.g. main member taken to be the life carrying the policy number and entry date), not read from the source document.';

-- A person appears at most once on a given policy.
create unique index policy_members_unique_idx on policy_members (policy_id, person_id)
  where archived_at is null;
-- And a policy has at most one main member. This is the rule the wide
-- spreadsheet could not express at all.
create unique index policy_members_one_main_idx on policy_members (policy_id)
  where member_type = 'main_member' and archived_at is null;
-- "Which policies is this person on?" - the lookup after a phone call.
create index policy_members_person_idx on policy_members (person_id)
  where archived_at is null;
-- The office's correction queue.
create index policy_members_inferred_idx on policy_members (policy_id)
  where is_inferred and archived_at is null;

create trigger policy_members_set_updated_at
  before update on policy_members
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Supplementary benefits (the SupplimentaryBenefits sheet).
-- ---------------------------------------------------------------------------
create table policy_benefits (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  archived_at   timestamptz,

  policy_id     uuid not null references policies(id) on delete cascade,
  -- Null when the benefit covers the whole policy rather than one named life.
  person_id     uuid references people(id) on delete restrict,

  benefit_code  text not null references ref_benefit_types(code),

  premium_cents bigint check (premium_cents is null or premium_cents >= 0),
  cover_cents   bigint check (cover_cents   is null or cover_cents   >= 0),
  currency      char(3) not null default 'ZAR',

  notes         text
);

comment on table policy_benefits is
  'Extra benefits attached to a policy. Created empty: the SupplimentaryBenefits sheet of the 2026 import held only the template example row.';

create index policy_benefits_policy_idx on policy_benefits (policy_id)
  where archived_at is null;

create trigger policy_benefits_set_updated_at
  before update on policy_benefits
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Master/child policy linkage (the Masterchildpolicy sheet). A group scheme
-- policy owning individual member policies underneath it.
-- ---------------------------------------------------------------------------
create table policy_links (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at       timestamptz not null default now(),

  master_policy_id uuid not null references policies(id) on delete cascade,
  child_policy_id  uuid not null references policies(id) on delete cascade,

  -- A policy cannot be its own parent.
  constraint policy_links_no_self check (master_policy_id <> child_policy_id)
);

comment on table policy_links is
  'Master-to-child policy hierarchy for group schemes. Created empty: the linkage sheet of the 2026 import held only the template example row.';

create unique index policy_links_unique_idx on policy_links (master_policy_id, child_policy_id);
-- A child belongs to one master.
create unique index policy_links_child_idx on policy_links (child_policy_id);

-- ---------------------------------------------------------------------------
-- How a policy is paid.
--
-- READ THIS BEFORE ADDING A COLUMN.
-- There is deliberately no account_number, no bank, no branch_code and no
-- account_type here, even though the import template has all four. Collecting
-- them is the payment provider's job, and storing them would turn this
-- database into a far larger POPIA and card-industry target for no benefit we
-- currently need. What IS here is the non-secret operational half: which
-- method, which day of the month, and the provider's own reference for the
-- mandate. See SECURITY.md and the note at the top of 0003.
-- ---------------------------------------------------------------------------
create table policy_payments (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  archived_at   timestamptz,

  policy_id     uuid not null references policies(id) on delete cascade,

  method        text not null check (method in (
                  'debit_order', 'stop_order', 'eft', 'cash',
                  'card', 'easypay', 'payat', 'undecided')),

  debit_day     smallint check (debit_day is null or debit_day between 1 and 31),

  -- The payment provider's mandate id. An opaque handle, not a credential:
  -- it identifies the arrangement, it cannot be used to move money.
  provider_reference text,

  -- Stop orders are collected by an employer, who has to be named.
  employer_name text,
  -- Public payment reference numbers printed on a client's card. These are
  -- lookup codes at a till, not bank account numbers.
  easypay_number text,
  payat_number   text,

  is_active     boolean not null default true,
  notes         text
);

comment on table policy_payments is
  'How a policy is collected. Contains NO bank account number, branch code or card data by design - those live with the payment provider. See SECURITY.md.';

create unique index policy_payments_active_idx on policy_payments (policy_id)
  where is_active and archived_at is null;

create trigger policy_payments_set_updated_at
  before update on policy_payments
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- One convenient read. The normalised tables are correct to write against and
-- tedious to read from, so the join every screen needs is written once here.
-- security_invoker means the caller's RLS applies: this view cannot be used to
-- see a row the caller could not already select.
-- ---------------------------------------------------------------------------
create view policy_overview
with (security_invoker = true) as
select
  p.id                as policy_id,
  p.policy_number,
  p.status_code,
  s.label             as status_label,
  p.plan_code,
  p.branch_code,
  p.entry_date,
  p.premium_cents,
  p.cover_cents,
  p.currency,
  holder.id           as main_member_id,
  holder.surname      as main_member_surname,
  holder.first_names  as main_member_first_names,
  holder.id_number    as main_member_id_number,
  phone.number        as main_member_phone,
  (select count(*) from policy_members pm
     where pm.policy_id = p.id and pm.archived_at is null) as lives_covered,
  p.tenant_id,
  p.created_at
from policies p
join ref_policy_statuses s on s.code = p.status_code
left join policy_members hm
  on hm.policy_id = p.id
 and hm.member_type = 'main_member'
 and hm.archived_at is null
left join people holder on holder.id = hm.person_id
left join person_phones phone
  on phone.person_id = holder.id
 and phone.is_primary
 and phone.archived_at is null
where p.archived_at is null;

comment on view policy_overview is
  'One row per active policy with its main member and primary phone number already joined. Read-only convenience for the staff portal.';

-- ---------------------------------------------------------------------------
-- Access. Every table here is personal or commercial information. anon gets
-- nothing at all.
-- ---------------------------------------------------------------------------
alter table policies        enable row level security;
alter table policy_members  enable row level security;
alter table policy_benefits enable row level security;
alter table policy_links    enable row level security;
alter table policy_payments enable row level security;

create policy staff_read_policies on policies for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_write_policies on policies for update to authenticated
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

create policy staff_read_members on policy_members for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_write_members on policy_members for update to authenticated
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

create policy staff_read_benefits on policy_benefits for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_read_links on policy_links for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_read_payments on policy_payments for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');

grant select, update on policies, policy_members to authenticated;
grant select on policy_benefits, policy_links, policy_payments, policy_overview to authenticated;

revoke all on policies, policy_members, policy_benefits,
               policy_links, policy_payments from anon;

do $guard$
begin
  if exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    grant select, insert, update on policies, policy_members, policy_benefits,
                                    policy_links, policy_payments to induduzo_api;
    grant select on policy_overview to induduzo_api;

    create policy api_rw_policies on policies for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
    create policy api_rw_members on policy_members for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
    create policy api_rw_benefits on policy_benefits for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
    create policy api_rw_links on policy_links for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
    create policy api_rw_payments on policy_payments for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
  end if;
end
$guard$;
