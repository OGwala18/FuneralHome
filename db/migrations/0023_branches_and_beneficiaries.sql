-- 0023 - The three branches, paying at a branch, and beneficiaries who may or
-- may not be covered lives.
--
-- WHY THIS EXISTS
-- The owner, 11 Nov 2026:
--   1. Families pay cash, or by card in person, at one of three branches, and
--      the policy should say which.
--   2. The beneficiary (who receives the payout) is either one of the lives
--      already on the policy ("make this dependant the beneficiary") or
--      someone who isn't covered at all, e.g. a brother with his own funeral
--      cover. That person needs as many details as the main member.
--
-- BENEFICIARIES GET THEIR OWN TABLE
-- policy_members holds each person once per policy (policy_members_unique_idx),
-- so a child who is also the beneficiary could not be both a 'child' row and a
-- 'beneficiary' row. policy_beneficiaries points at any person: a covered life
-- or an outside one. Existing 'beneficiary' member rows are copied across so
-- nothing already captured is lost; those rows stay where they are.
--
-- WHERE IT RUNS
-- Wherever 0013 ran. Not Supabase yet (as 0013).

-- ---------------------------------------------------------------------------
-- The branches, as printed on the application form.
-- ---------------------------------------------------------------------------
insert into ref_branches (code, label, town, province, sort_order) values
  ('edendale',      'Edendale Main Road (Head Office)', 'Pietermaritzburg', 'KwaZulu-Natal', 20),
  ('boshoff',       '161 Boshoff Street',               'Pietermaritzburg', 'KwaZulu-Natal', 30),
  ('langalibalele', '171 Langalibalele Street',         'Pietermaritzburg', 'KwaZulu-Natal', 40)
on conflict (code) do nothing;

-- Where a family pays in person (cash or card). Null for every other method.
alter table policy_payments
  add column if not exists pay_branch_code text references ref_branches(code);

comment on column policy_payments.pay_branch_code is
  'The branch a family pays at, for cash or card in person. Null for other methods.';

-- ---------------------------------------------------------------------------
-- Who the policy pays out to.
-- ---------------------------------------------------------------------------
create table if not exists policy_beneficiaries (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at     timestamptz not null default now(),
  archived_at    timestamptz,

  policy_id      uuid not null references policies(id) on delete cascade,
  person_id      uuid not null references people(id),
  -- To the main member: 'Brother', 'Daughter'. Free text, as on the paper form.
  relationship   text check (relationship is null or length(trim(relationship)) between 1 and 60),
  -- Of the payout. Null means the whole of it, the usual case of one beneficiary.
  share_percent  smallint check (share_percent is null or share_percent between 1 and 100),
  created_by     text not null default 'system'
);

create unique index if not exists policy_beneficiaries_once_idx
  on policy_beneficiaries (policy_id, person_id) where archived_at is null;
create index if not exists policy_beneficiaries_person_idx
  on policy_beneficiaries (person_id);

comment on table policy_beneficiaries is
  'Who a policy pays out to: a life on the policy, or someone not covered by it. Removing one archives the row.';

insert into policy_beneficiaries (policy_id, person_id, created_by)
select pm.policy_id, pm.person_id, 'migration:0023'
  from policy_members pm
 where pm.member_type = 'beneficiary' and pm.archived_at is null
on conflict do nothing;

alter table policy_beneficiaries enable row level security;
revoke all on policy_beneficiaries from anon, authenticated;

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;
  grant select, insert, update on policy_beneficiaries to induduzo_api;
  drop policy if exists api_rw_policy_beneficiaries on policy_beneficiaries;
  create policy api_rw_policy_beneficiaries on policy_beneficiaries for all to induduzo_api
    using (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');
end
$guard$;
