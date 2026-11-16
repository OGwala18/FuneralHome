-- 0030 - A finished password reset counts as the second step, once.
--
-- WHY THIS EXISTS
-- After "Forgot your password?" (0029) the person signs in with the new
-- password and the portal then asked "Confirm it's you" for an emailed code.
-- The owner pointed out (16 Nov 2026) that this asks twice for the same proof:
-- the temporary password they just used came from that same mailbox. So a
-- successful reset now hands the browser a one-time token, and the sign-in
-- that follows straight after may spend it in place of the emailed code.
--
-- WHAT IT ADDS
-- second_step_hash      SHA-256 of that token; never the token itself.
-- second_step_used_at   when a sign-in spent it. It can be spent once, within
--                       ten minutes of the reset (the API's rule), and only
--                       by the same person.
--
-- No new grant: induduzo_api already has SELECT, INSERT and UPDATE on the
-- table (0029). Safe to run again.

alter table staff_password_resets
  add column if not exists second_step_hash bytea,
  add column if not exists second_step_used_at timestamptz;

do $guard$
begin
  if not exists (
    select 1 from pg_constraint
     where conname = 'staff_password_resets_second_step_hash_len'
       and conrelid = 'staff_password_resets'::regclass
  ) then
    alter table staff_password_resets
      add constraint staff_password_resets_second_step_hash_len
      check (second_step_hash is null or octet_length(second_step_hash) = 32);
  end if;
end
$guard$;

comment on column staff_password_resets.second_step_hash is
  'SHA-256 of the one-time token a finished reset gives the browser, so the sign-in straight after skips the emailed code. Spent once, within 10 minutes.';
