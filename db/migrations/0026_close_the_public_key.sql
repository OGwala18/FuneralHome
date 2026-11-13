-- 0026 - Take Supabase's public `anon` role off every table, and keep it off.
--
-- WHY THIS EXISTS
-- 0004 let the public key INSERT into plan_enquiries and enquiry_events, for a
-- website that once wrote to Supabase directly. The website has posted to our
-- API ever since (frontend/src/lib/registration.ts), where every field is
-- revalidated, the honeypot checked and the rate limit counted. The grant and
-- its two policies were never taken back: 0014 and 0025 left `anon` alone on
-- purpose. Checked read-only on production, 13 Nov 2026: anyone holding the
-- publishable key, which is public by design and sits in portal/.env.example,
-- could write a lead straight into the portal's list, and append to the audit
-- trail, around every one of those checks. (No such row existed.)
--
-- The same check found `anon` holding every privilege, TRUNCATE included, on
-- the ref_* tables and policy_overview. Row-level security answered most of
-- that; TRUNCATE ignores row-level security.
--
-- And the cause of both: Supabase's default privileges grant `anon` and
-- `authenticated` everything on each table a migration creates. 0025 took
-- `authenticated` back once; the next migration to create a table would have
-- handed both roles everything again (CLAUDE.md: never grant to authenticated).
--
-- WHAT IT DOES
-- 1. Drops the two anon insert policies from 0004.
-- 2. Revokes everything `anon` holds on tables, views, sequences and functions
--    in `public`, and `authenticated` too (0025 already did that on Supabase;
--    repeated so this file stands on its own).
-- 3. Changes the default privileges of whoever runs the migrations (postgres
--    on Supabase), so objects created from now on grant nothing to `anon` or
--    `authenticated`. The API's own role keeps being granted by name in each
--    migration, as it always has been.
--
-- Nothing reads or writes data with the public key: the site posts to the API
-- and the portal uses Supabase for sign-in only. Safe to run again; harmless
-- where the Supabase roles do not exist.

drop policy if exists anon_can_submit_enquiry on plan_enquiries;
drop policy if exists anon_can_log_event on enquiry_events;

do $close$
declare
  role_name text;
begin
  foreach role_name in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = role_name) then
      execute format('revoke all on all tables in schema public from %I', role_name);
      execute format('revoke all on all sequences in schema public from %I', role_name);
      execute format('revoke all on all functions in schema public from %I', role_name);
      execute format('alter default privileges in schema public revoke all on tables from %I', role_name);
      execute format('alter default privileges in schema public revoke all on sequences from %I', role_name);
      execute format('alter default privileges in schema public revoke all on functions from %I', role_name);
    end if;
  end loop;
end
$close$;
