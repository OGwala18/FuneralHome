-- 0022 - Payment reminders are claimed before they are sent.
--
-- WHY THIS EXISTS
-- The owner, 11 Nov 2026: on a family's payment day (the 1st, 25th or 30th)
-- WhatsApp them our bank details with their policy number as the reference;
-- if the premium is still unpaid the day after, remind them once more.
-- app/jobs/payment_reminders.py does it, using the payment_reminders log that
-- 0013 created for exactly this and left empty:
--   kind 'upcoming'  the reminder on the payment day itself
--   kind 'overdue'   the one the day after, still unpaid
--
-- WHAT CHANGES
-- 0013 kept a reminder unique only once it was 'sent', so a failed send could
-- be tried again: two runs of the job could both send. Now the job writes the
-- row FIRST, as 'pending', then sends and records the outcome. The unique index
-- covers every status, so a family never gets the same reminder twice, even
-- after a failure or two runs at once. `detail` says why one was skipped or
-- failed ('no_phone', 'opted_out', a Twilio error code); never message text.
--
-- WHERE IT RUNS
-- Wherever 0013 ran. Not Supabase yet (as 0013).

alter table payment_reminders drop constraint if exists payment_reminders_status_check;
alter table payment_reminders add constraint payment_reminders_status_check
  check (status in ('pending', 'sent', 'failed', 'skipped'));

alter table payment_reminders add column if not exists detail text
  check (detail is null or length(detail) <= 60);

drop index if exists payment_reminders_once_idx;
create unique index payment_reminders_once_idx
  on payment_reminders (instalment_id, kind);

comment on table payment_reminders is
  'Premium reminders, one row per instalment and kind (upcoming = on the payment day, overdue = the day after). Written as pending before sending, so none is ever sent twice.';

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;
  -- The outcome is recorded on the row the job claimed.
  grant select, insert, update on payment_reminders to induduzo_api;
end
$guard$;
