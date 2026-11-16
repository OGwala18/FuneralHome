-- 0031 - Member book history: what every record used to say, and who changed it.
--
-- WHY THIS EXISTS
-- Staff can now correct a member after enrolment (ID number, surname, mobile,
-- email, address, citizenship and income, payment) and move a policy to
-- another plan without enrolling the family again (16 Nov 2026). Every such
-- change overwrites a value. The owner asked for the old value to be kept, so
-- that a correction which was itself a mistake can be put back from the record
-- rather than from memory or from last night's backup.
--
-- HOW IT WORKS
-- A trigger on each member-book table writes one row here for every insert,
-- update and delete: the table, the row, the columns that changed with their
-- old and new values, when, and who. Because it is a trigger, nothing that
-- writes to these tables can skip it: the portal, the daily schedule job, an
-- import script or someone at a SQL prompt.
--
-- WHO
-- The API names the staff member at the start of each write transaction with
-- set_config('induduzo.actor', <email>, true). Without that (an import, the
-- jobs cron, a migration) the database login is recorded instead.
--
-- WHY THE API CANNOT FORGE OR ERASE IT
-- The trigger function is SECURITY DEFINER, owned by the migrating role, so it
-- inserts here with the owner's rights. induduzo_api is granted SELECT only:
-- it can read the history, never write a false line into it, update or
-- delete one. Update and delete are additionally turned into no-ops by rules,
-- as enquiry_events is (0004).
--
-- WHAT IS LEFT OUT
-- premium_instalments is recorded on update and delete only: the schedule job
-- inserts every policy's next premium each morning, and those rows say nothing
-- that the policy does not. updated_at alone changing is not a change.
--
-- PERSONAL DATA
-- The old values include ID numbers, names and phone numbers: this table holds
-- the same POPIA-protected information as the tables it watches, and is
-- protected the same way (RLS on, nothing to anon or authenticated, 0026). It
-- is in `public`, so db/backup.py includes it in the daily backup.
--
-- WHERE IT RUNS
-- Everywhere. The grant is guarded by a pg_roles check, as from 0008 on.
-- Safe to run again.

create table if not exists member_book_history (
  id             bigint generated always as identity primary key,
  tenant_id      uuid not null default '00000000-0000-0000-0000-000000000001',
  changed_at     timestamptz not null default now(),
  -- The staff email the API set, or the database login.
  changed_by     text not null,

  table_name     text not null,
  row_id         uuid not null,
  operation      text not null check (operation in ('insert', 'update', 'delete')),

  -- Who and what the row belongs to, so one member's or one policy's whole
  -- history is a single indexed read.
  person_id      uuid,
  policy_id      uuid,

  -- For an update, only the columns that changed. For an insert, the new row;
  -- for a delete, the row as it was.
  old_values     jsonb,
  new_values     jsonb
);

comment on table member_book_history is
  'Append-only history of the member book: every insert, update and delete on people, phones, addresses, policies, lives, beneficiaries, payment arrangements and premium changes, with the old values. Written by trigger only. Contains POPIA-protected personal information.';

create index if not exists member_book_history_person_idx
  on member_book_history (person_id, changed_at desc) where person_id is not null;
create index if not exists member_book_history_policy_idx
  on member_book_history (policy_id, changed_at desc) where policy_id is not null;
create index if not exists member_book_history_row_idx
  on member_book_history (table_name, row_id, changed_at desc);

-- Append-only, whoever asks.
create or replace rule member_book_history_no_update as
  on update to member_book_history do instead nothing;
create or replace rule member_book_history_no_delete as
  on delete to member_book_history do instead nothing;

-- ---------------------------------------------------------------------------
-- The trigger.
-- ---------------------------------------------------------------------------
create or replace function record_member_book_change() returns trigger
  language plpgsql
  security definer
  set search_path = public, pg_temp
as $fn$
declare
  before_row jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
  after_row  jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
  the_row    jsonb := coalesce(after_row, before_row);
  old_diff   jsonb := '{}'::jsonb;
  new_diff   jsonb := '{}'::jsonb;
  col        text;
begin
  if tg_op = 'UPDATE' then
    for col in select jsonb_object_keys(after_row) loop
      if col <> 'updated_at'
         and (before_row -> col) is distinct from (after_row -> col) then
        old_diff := old_diff || jsonb_build_object(col, before_row -> col);
        new_diff := new_diff || jsonb_build_object(col, after_row -> col);
      end if;
    end loop;
    if new_diff = '{}'::jsonb then
      return null;   -- nothing but updated_at moved
    end if;
  end if;

  insert into member_book_history
    (changed_by, table_name, row_id, operation, person_id, policy_id, old_values, new_values)
  values (
    coalesce(nullif(current_setting('induduzo.actor', true), ''), session_user),
    tg_table_name,
    (the_row ->> 'id')::uuid,
    lower(tg_op),
    case when tg_table_name = 'people' then (the_row ->> 'id')::uuid
         else (the_row ->> 'person_id')::uuid end,
    case when tg_table_name = 'policies' then (the_row ->> 'id')::uuid
         else (the_row ->> 'policy_id')::uuid end,
    case tg_op when 'UPDATE' then old_diff when 'DELETE' then before_row end,
    case tg_op when 'UPDATE' then new_diff when 'INSERT' then after_row end
  );
  return null;
end
$fn$;

comment on function record_member_book_change() is
  'Writes member_book_history. SECURITY DEFINER so the API role, which may only read the history, cannot write it.';

revoke all on function record_member_book_change() from public;

do $tables$
declare
  watched text[] := array['people', 'person_phones', 'addresses', 'policies',
                          'policy_members', 'policy_payments', 'policy_beneficiaries'];
  t text;
begin
  foreach t in array watched loop
    execute format('drop trigger if exists %I on %I', t || '_history', t);
    execute format(
      'create trigger %I after insert or update or delete on %I '
      'for each row execute function record_member_book_change()',
      t || '_history', t);
  end loop;

  -- The daily job inserts tomorrow's premiums; only changes to them are history.
  drop trigger if exists premium_instalments_history on premium_instalments;
  create trigger premium_instalments_history
    after update or delete on premium_instalments
    for each row execute function record_member_book_change();
end
$tables$;

alter table member_book_history enable row level security;
revoke all on member_book_history from anon, authenticated;

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  -- Read only. The trigger writes; the API never does.
  grant select on member_book_history to induduzo_api;
  drop policy if exists api_read_member_book_history on member_book_history;
  create policy api_read_member_book_history on member_book_history
    for select to induduzo_api
    using (tenant_id = '00000000-0000-0000-0000-000000000001');
end
$guard$;
