-- 0013 - Enrolling members from the portal, and the premium schedule.
--
-- WHY THIS EXISTS
-- Until now the book of business only ever arrived by spreadsheet import. Staff
-- can now turn an enquiry (or a walk-in) into a person, a policy and its lives
-- from the portal, through the API, in one transaction. Nothing new is needed
-- for that in the schema: 0009 and 0010 already describe it. What is new is
-- money over time.
--
-- ON THE SCHEDULE
-- A premium is not a single fact about a policy, it is a series of debts that
-- fall due on dates. "Is this family behind?" and "who needs a reminder on
-- Friday?" are both questions about rows in that series, so it is stored as
-- rows: one per expected payment. Overdue is never stored; it is a due row
-- whose date has passed, worked out at the moment someone asks.
--
-- What is deliberately NOT here, as in policy_payments: no account number, no
-- bank, no branch code, no card. Recording that a premium was paid, when, and
-- by which method is the office's book-keeping. Collecting it is the payment
-- provider's job.

-- ---------------------------------------------------------------------------
-- How often a policy is paid. The enum has existed since 0002 for the website
-- form; the policy's payment arrangement now records it too.
-- ---------------------------------------------------------------------------
alter table policy_payments
  add column frequency payment_frequency not null default 'monthly';

-- ---------------------------------------------------------------------------
-- One row per expected premium payment.
-- ---------------------------------------------------------------------------
create table premium_instalments (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  archived_at   timestamptz,

  policy_id     uuid not null references policies(id) on delete cascade,

  due_date      date not null,
  -- What was owed on that date, fixed when the row was generated. A later price
  -- change must not rewrite what a family owed in March.
  amount_cents  bigint not null check (amount_cents >= 0),
  currency      char(3) not null default 'ZAR',

  status        text not null default 'due'
                  check (status in ('due', 'paid', 'waived', 'cancelled')),

  -- The office's record of the payment. Never the means of payment itself.
  paid_at           timestamptz,
  paid_amount_cents bigint check (paid_amount_cents is null or paid_amount_cents >= 0),
  paid_method       text check (paid_method is null or paid_method in (
                      'debit_order', 'stop_order', 'eft', 'cash',
                      'card', 'easypay', 'payat', 'undecided')),
  -- Staff email of whoever recorded or waived it.
  recorded_by   text,
  notes         text,

  constraint premium_instalments_paid_has_date
    check (status <> 'paid' or paid_at is not null)
);

comment on table premium_instalments is
  'One row per expected premium payment. Overdue is derived (status due, date passed), never stored. Contains no bank account, branch code or card data.';

-- One expected payment per policy per date, so generating the schedule twice
-- is harmless. This is what lets the roll-forward job be re-run safely.
create unique index premium_instalments_unique_idx
  on premium_instalments (policy_id, due_date)
  where archived_at is null;
-- The reminder and overdue queue: everything still owed, by date.
create index premium_instalments_due_idx
  on premium_instalments (due_date)
  where status = 'due' and archived_at is null;
create index premium_instalments_policy_idx
  on premium_instalments (policy_id, due_date)
  where archived_at is null;

create trigger premium_instalments_set_updated_at
  before update on premium_instalments
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- What was sent about an instalment, so a family is reminded once, not every
-- time the job runs. Created now; filled once WhatsApp sending is approved.
-- ---------------------------------------------------------------------------
create table payment_reminders (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at    timestamptz not null default now(),

  instalment_id uuid not null references premium_instalments(id) on delete cascade,

  kind          text not null check (kind in ('upcoming', 'overdue')),
  channel       text not null check (channel in ('whatsapp', 'sms', 'email', 'call')),
  status        text not null check (status in ('sent', 'failed', 'skipped')),
  -- The provider's message id (Twilio SID). Never the message text, which
  -- carries the family's name and amount.
  provider_reference text,
  sent_at       timestamptz,
  -- 'system' for the job, or the staff email for a reminder made by hand.
  created_by    text not null default 'system'
);

comment on table payment_reminders is
  'Log of premium reminders. A successful reminder of one kind is recorded once per instalment, so re-running the reminder job never sends twice.';

create unique index payment_reminders_once_idx
  on payment_reminders (instalment_id, kind)
  where status = 'sent';
create index payment_reminders_instalment_idx
  on payment_reminders (instalment_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Everything still owed, with who to ring. The Payments screen and the future
-- reminder job both read exactly this, so it is written once.
-- ---------------------------------------------------------------------------
create view instalments_outstanding
with (security_invoker = true) as
select
  i.id                        as instalment_id,
  i.policy_id,
  p.policy_number,
  p.status_code               as policy_status,
  i.due_date,
  i.amount_cents,
  i.currency,
  (current_date - i.due_date) as days_overdue,
  holder.id                   as main_member_id,
  holder.surname              as main_member_surname,
  holder.first_names          as main_member_first_names,
  phone.number                as main_member_phone,
  i.tenant_id
from premium_instalments i
join policies p on p.id = i.policy_id and p.archived_at is null
join ref_policy_statuses s on s.code = p.status_code and not s.is_terminal
left join policy_members hm
  on hm.policy_id = p.id
 and hm.member_type = 'main_member'
 and hm.archived_at is null
left join people holder on holder.id = hm.person_id
left join person_phones phone
  on phone.person_id = holder.id
 and phone.is_primary
 and phone.archived_at is null
where i.status = 'due'
  and i.archived_at is null;

comment on view instalments_outstanding is
  'Every unpaid instalment on a live policy, with the main member and primary phone. days_overdue > 0 means overdue; <= 0 means upcoming.';

-- ---------------------------------------------------------------------------
-- Access. Same shape as 0009-0011: personal and financial, so anon gets
-- nothing, signed-in staff may read, and the API role does the writing.
-- ---------------------------------------------------------------------------
alter table premium_instalments enable row level security;
alter table payment_reminders   enable row level security;

create policy staff_read_instalments on premium_instalments for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
create policy staff_read_reminders on payment_reminders for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');

grant select on premium_instalments, payment_reminders, instalments_outstanding to authenticated;
revoke all on premium_instalments, payment_reminders, instalments_outstanding from anon;

-- The API role. Also RE-ASSERTS its grants on every member-book table from
-- 0008-0012. On a database where induduzo_api did not exist when those ran
-- (Supabase, today), their guarded blocks were skipped; once the role exists,
-- this one file brings it level. Written to be safe to run where they did run.
do $guard$
declare
  -- Table and the policy name it was given in 0008-0011, so the same policy is
  -- replaced rather than a second identical one added beside it.
  ref_tables  text[] := array['ref_member_types', 'ref_policy_statuses', 'ref_plans',
                              'ref_branches', 'ref_benefit_types'];
  ref_names   text[] := array['api_rw_member_types', 'api_rw_policy_statuses', 'api_rw_plans',
                              'api_rw_branches', 'api_rw_benefit_types'];
  book_tables text[] := array['people', 'person_phones', 'addresses', 'policies',
                              'policy_members', 'policy_benefits', 'policy_links',
                              'policy_payments', 'data_quality_flags',
                              'premium_instalments', 'payment_reminders'];
  book_names  text[] := array['api_rw_people', 'api_rw_phones', 'api_rw_addresses', 'api_rw_policies',
                              'api_rw_members', 'api_rw_benefits', 'api_rw_links',
                              'api_rw_payments', 'api_rw_flags',
                              'api_rw_instalments', 'api_rw_reminders'];
  i int;
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  grant select, insert, update on premium_instalments to induduzo_api;
  grant select, insert         on payment_reminders   to induduzo_api;
  grant select on instalments_outstanding, policy_overview to induduzo_api;

  grant select, insert, update on ref_member_types, ref_policy_statuses, ref_plans,
                                  ref_branches, ref_benefit_types,
                                  people, person_phones, addresses,
                                  policies, policy_members, policy_benefits,
                                  policy_links, policy_payments,
                                  data_quality_flags
    to induduzo_api;

  -- Reference data carries no tenant.
  for i in 1 .. array_length(ref_tables, 1) loop
    execute format('drop policy if exists %I on %I', ref_names[i], ref_tables[i]);
    execute format(
      'create policy %I on %I for all to induduzo_api using (true) with check (true)',
      ref_names[i], ref_tables[i]);
  end loop;

  for i in 1 .. array_length(book_tables, 1) loop
    execute format('drop policy if exists %I on %I', book_names[i], book_tables[i]);
    execute format(
      'create policy %I on %I for all to induduzo_api '
      'using (tenant_id = %L) with check (tenant_id = %L)',
      book_names[i], book_tables[i],
      '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001');
  end loop;
end
$guard$;
