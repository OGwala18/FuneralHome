-- 0005 - A restricted role for the API.
--
-- WHY THIS EXISTS
-- The API previously connected as the table owner. An owner BYPASSES row-level
-- security entirely, which made the policies in 0004 decorative on the one code
-- path that matters. This role is not an owner, so RLS applies to it. It also
-- cannot DROP, TRUNCATE or ALTER anything.
--
-- PORTABLE VERSION. The companion 0005_api_role.sh reads the password from the
-- environment and runs automatically in local Docker. Managed Postgres
-- (Supabase, Railway, RDS) cannot execute shell scripts, so this file exists to
-- be applied by the migration runner instead.
--
-- The password is NOT set here. Set it once, out of band, after applying:
--
--   alter role induduzo_api login password '<from your secret store>';
--
-- That keeps the credential out of the repository and out of migration history.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    -- NOLOGIN until a password is set out of band; a login role with no
    -- password is worse than one that cannot log in yet.
    create role induduzo_api nologin;
  end if;
end
$$;

grant usage on schema public to induduzo_api;

-- Exactly what the endpoints need. No delete, no truncate, no ddl.
grant select, insert, update on plan_enquiries      to induduzo_api;
grant select, insert         on enquiry_events      to induduzo_api;
grant usage, select          on sequence plan_enquiry_ref_seq to induduzo_api;

-- RLS is enabled on both tables, so a role with no policy sees nothing.
drop policy if exists api_rw_enquiries on plan_enquiries;
create policy api_rw_enquiries
  on plan_enquiries for all
  to induduzo_api
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

drop policy if exists api_rw_events on enquiry_events;
create policy api_rw_events
  on enquiry_events for all
  to induduzo_api
  using      (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');
