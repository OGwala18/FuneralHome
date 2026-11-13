-- 0028 - A mobile number on each staff account.
--
-- WHY THIS EXISTS
-- The office keeps a cell number for each employee in the Employee Master
-- File, and the owner asked for it to sit on the staff accounts in the portal
-- (13 Nov 2026), so the Team page can show who to phone. It is optional:
-- not every employee has one, and nothing is sent to it yet.
--
-- WHAT IT DOES
-- Adds staff_users.mobile, stored E.164 like person_phones.number, so
-- '0821234567' is stored as '+27821234567' and Twilio could dial it as is.
-- Only the employee's own number belongs here: never an ID number, and never
-- bank details (staff_users has no column for either, on purpose).
--
-- No new grant: the column is covered by the table-level grants 0007 gave
-- induduzo_api, and nothing is granted to anon or authenticated.
-- Safe to run again.

alter table staff_users
  add column if not exists mobile text;

do $guard$
begin
  if not exists (
    select 1 from pg_constraint
     where conname = 'staff_users_mobile_e164'
       and conrelid = 'staff_users'::regclass
  ) then
    alter table staff_users
      add constraint staff_users_mobile_e164
      check (mobile is null or mobile ~ '^\+[1-9][0-9]{7,14}$');
  end if;
end
$guard$;

comment on column staff_users.mobile is
  'The staff member''s own cell number, E.164. Optional. Shown to owners on the Team page.';
