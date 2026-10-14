-- 0001 — Extensions and roles.
--
-- Portable across vanilla Postgres (local dev) and Supabase (staging/prod).
-- Supabase already ships the `anon` and `authenticated` roles; a local
-- container does not. Creating them here keeps ONE set of migrations valid in
-- both places, so the RLS policies in 0004 never have to be forked.

create extension if not exists pgcrypto;   -- gen_random_uuid() on PG < 13

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
end
$$;

-- The API user connects as the owner locally; these grants mirror what Supabase
-- sets up so behaviour matches between environments.
grant usage on schema public to anon, authenticated;
