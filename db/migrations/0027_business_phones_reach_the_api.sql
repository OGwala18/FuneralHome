-- 0027 - Give the API's login the access to business_phone_numbers that 0015 meant to.
--
-- WHY THIS EXISTS
-- 0015 grants induduzo_api its access inside a guard that skips when the role
-- does not exist. On Supabase it ran on 19 Oct 2026, before induduzo_api
-- existed there (0005 arrived with the launch, 12 Nov), so the guard skipped
-- and the launch baselined 0015 rather than running it again. Checked
-- read-only on production, 13 Nov 2026: the table has row-level security on,
-- no policy at all, and no grant to induduzo_api. It was the only table in
-- that state. Locally and on Railway the API has full access, so the gap
-- would only show in production, as "permission denied" on the first feature
-- that reads the business's own numbers. Nothing reads it yet.
--
-- WHAT IT DOES
-- Repeats 0015's access block exactly. Safe to run again; a no-op where the
-- role does not exist.

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  grant select, insert, update on business_phone_numbers to induduzo_api;

  drop policy if exists api_rw_business_phones on business_phone_numbers;
  create policy api_rw_business_phones
    on business_phone_numbers for all
    to induduzo_api
    using      (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');
end
$guard$;
