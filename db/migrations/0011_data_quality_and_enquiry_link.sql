-- 0011 - Data quality flags, and the enquiry-to-person link.
--
-- WHY THIS EXISTS
-- The first real import brought in 61 lives across 11 policies, and the source
-- spreadsheet was honest office work rather than clean data: eleven ID numbers
-- fail their own checksum, one decodes to the 38th of April, two disagree with
-- the date of birth typed beside them, and not one row carried a phone number.
--
-- There are three things you can do with that, and two of them are wrong.
-- Dropping the bad rows loses real clients. Quietly "correcting" them invents
-- facts about real families that will be discovered at a claim, which is the
-- worst possible moment. So the data goes in exactly as supplied, and every
-- problem becomes a row here: a work queue the office can actually clear,
-- against the paper application forms.
--
-- A flag is not an error log. It is a task.

create table data_quality_flags (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at   timestamptz not null default now(),

  -- Exactly one of these is set, so the flag always points at a real row and
  -- disappears with it. A polymorphic entity_id column would not.
  person_id        uuid references people(id)         on delete cascade,
  policy_id        uuid references policies(id)       on delete cascade,
  policy_member_id uuid references policy_members(id) on delete cascade,

  constraint data_quality_flags_one_subject check (
    (person_id        is not null)::int +
    (policy_id        is not null)::int +
    (policy_member_id is not null)::int = 1
  ),

  issue_code   text not null check (issue_code in (
                 'id_number_missing',      -- no ID number supplied
                 'id_number_malformed',    -- present, but not 13 digits
                 'id_checksum_failed',     -- 13 digits, checksum does not pass
                 'id_date_impossible',     -- ID encodes a date that cannot exist
                 'dob_id_mismatch',        -- DOB column disagrees with the ID
                 'phone_number_missing',   -- nobody can be telephoned
                 'member_type_unknown',    -- role on the policy was never recorded
                 'plan_missing',           -- policy has no product assigned
                 'cover_missing',          -- policy has no cover amount
                 'premium_missing',        -- policy has no premium
                 'entry_date_missing')),

  severity     text not null default 'medium'
                 check (severity in ('high', 'medium', 'low')),

  field        text,   -- which column the problem is in
  raw_value    text,   -- what was actually in the file, verbatim
  detail       text,   -- one plain sentence a non-technical person can act on

  source       text not null default 'import',

  -- Cleared when someone has checked the paper file and fixed the row.
  resolved_at  timestamptz,
  resolved_by  text,
  resolution   text
);

comment on table data_quality_flags is
  'Work queue of known problems in imported records. Each row is a task for the office to resolve against the original paper application, not an error log.';
comment on column data_quality_flags.raw_value is
  'The offending value exactly as it appeared in the source file, so staff can compare it against what is written on the form.';

-- The queue itself: what is still outstanding, worst first.
create index data_quality_flags_open_idx
  on data_quality_flags (severity, issue_code)
  where resolved_at is null;
create index data_quality_flags_person_idx on data_quality_flags (person_id)
  where person_id is not null and resolved_at is null;
create index data_quality_flags_policy_idx on data_quality_flags (policy_id)
  where policy_id is not null and resolved_at is null;

-- The same problem should not be raised twice against the same row.
create unique index data_quality_flags_unique_open_idx
  on data_quality_flags (
    coalesce(person_id, policy_id, policy_member_id), issue_code, coalesce(field, '')
  )
  where resolved_at is null;

-- ---------------------------------------------------------------------------
-- The join between the website and the book of business.
--
-- plan_enquiries stays exactly as it is: a raw, append-mostly record of what
-- somebody typed into a form, which is the right shape for a submission log
-- and should not be rewritten later. What it gains is a pointer, so that once
-- a lead is recognised as a person we already know - or becomes one - the two
-- halves of the system are connected rather than merely similar.
-- ---------------------------------------------------------------------------
alter table plan_enquiries
  add column person_id uuid references people(id) on delete set null;

comment on column plan_enquiries.person_id is
  'Set once this enquiry has been matched to a person record. Null means the enquiry has not been worked yet, or the lead never became a client.';

create index plan_enquiries_person_idx on plan_enquiries (person_id)
  where person_id is not null;

-- ---------------------------------------------------------------------------
-- Access.
-- ---------------------------------------------------------------------------
alter table data_quality_flags enable row level security;

create policy staff_read_flags on data_quality_flags for select to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');
-- Staff resolve flags; that is the whole point of the table.
create policy staff_write_flags on data_quality_flags for update to authenticated
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

grant select, update on data_quality_flags to authenticated;
revoke all on data_quality_flags from anon;

do $guard$
begin
  if exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    grant select, insert, update on data_quality_flags to induduzo_api;

    create policy api_rw_flags on data_quality_flags for all to induduzo_api
      using      (tenant_id = '00000000-0000-0000-0000-000000000001')
      with check (tenant_id = '00000000-0000-0000-0000-000000000001');
  end if;
end
$guard$;
