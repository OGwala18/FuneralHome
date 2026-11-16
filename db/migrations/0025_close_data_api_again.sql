-- 0025 - Close Supabase's Data API to signed-in accounts, whatever came before.
--
-- WHY THIS EXISTS
-- 0014 closed it on 16 Oct 2026 (CLAUDE.md: never grant to `authenticated`).
-- But 0013, 0016, 0018, 0020 and 0023 were written while those grants were
-- the pattern, and on Supabase they run AFTER 0014 for the first time (the
-- production launch, 12 Nov 2026). Each would hand `authenticated` a read
-- policy, so anyone with a Supabase login could read the member book around
-- every check the API makes. This runs last and takes all of it back,
-- generically, so a table added later is covered without being named.
--
-- WHAT IT DOES
-- Every policy in `public` that names `authenticated` is dropped, and every
-- privilege `authenticated` holds on a table, view or sequence in `public` is
-- revoked. `anon` is not touched here. The API's own role (induduzo_api) and
-- the owner are unaffected.
--
-- Safe to run again, and harmless where `authenticated` does not exist.

do $close$
declare
  item record;
begin
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    return;
  end if;

  for item in
    select tablename, policyname
      from pg_policies
     where schemaname = 'public' and 'authenticated' = any(roles)
  loop
    execute format('drop policy if exists %I on public.%I', item.policyname, item.tablename);
  end loop;

  execute 'revoke all on all tables in schema public from authenticated';
  execute 'revoke all on all sequences in schema public from authenticated';
end
$close$;
