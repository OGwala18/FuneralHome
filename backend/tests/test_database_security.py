"""The database's own walls: what the API's login may do, and what nobody else may.

The API checks every request, but the database is where the information
lives, so it must hold even if a check above it is ever wrong. These run as
`induduzo_api`, the login production uses, against a database built from
db/migrations, and assert what is TRUE OF THE SCHEMA rather than of one code
path:

- the API's login is an ordinary role: no superuser, no bypassing row-level
  security, no creating roles, databases or tables;
- it can never DELETE or TRUNCATE anything, and the two audit logs are
  append-only for it;
- Supabase's public roles (`anon`, `authenticated`) hold nothing at all, now or
  on tables created later (0014, 0025, 0026);
- every table has row-level security on; views run as the caller; no
  SECURITY DEFINER function can be steered by a search_path.

The same queries were run read-only against production on 13 Nov 2026; that
is how the open `anon` insert was found (see 0026).
"""

from __future__ import annotations

import psycopg
import pytest

SUPABASE_PUBLIC_ROLES = ("anon", "authenticated")
APPEND_ONLY = ("enquiry_events", "staff_events")
# Created by db/migrate.py itself; no personal data, nothing granted on it.
RUNNER_TABLES = {"schema_migrations"}


def _rows(db, sql: str, *params) -> list[tuple]:
    return db.execute(sql, params).fetchall()


def test_these_checks_run_as_the_api_login(db):
    assert _rows(db, "select current_user") == [("induduzo_api",)]


def test_the_api_login_is_an_ordinary_role(db):
    attributes = _rows(db, """
        select rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication
          from pg_roles where rolname = current_user""")
    assert attributes == [(False, False, False, False, False)]


def test_the_api_login_cannot_change_the_schema(db):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("create table public.should_not_exist (id int)")


def test_the_api_login_can_never_delete_or_truncate(db):
    found = _rows(db, """
        select c.relname, p.priv
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         cross join (values ('DELETE'), ('TRUNCATE')) as p(priv)
         where n.nspname = 'public' and c.relkind in ('r', 'p')
           and has_table_privilege(current_user, c.oid, p.priv)""")
    assert found == [], "nothing the API does needs to destroy a row"


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_the_audit_logs_are_append_only_for_the_api(db, table):
    # Asked of the catalogue: enquiry_events' own rules turn an UPDATE into a
    # silent no-op before any permission check, so trying one proves nothing.
    assert _rows(db, """
        select has_table_privilege(current_user, %s, 'INSERT'),
               has_table_privilege(current_user, %s, 'UPDATE'),
               has_table_privilege(current_user, %s, 'DELETE')""",
                 table, table, table) == [(True, False, False)]


@pytest.mark.parametrize("role", SUPABASE_PUBLIC_ROLES)
def test_the_public_supabase_roles_hold_no_table_or_sequence(db, role):
    if not _rows(db, "select 1 from pg_roles where rolname = %s", role):
        pytest.skip(f"no {role} role in this database")
    tables = _rows(db, """
        select table_name, privilege_type from information_schema.role_table_grants
         where table_schema = 'public' and grantee = %s""", role)
    sequences = _rows(db, """
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public'
           -- CASE, because the planner may test rows before the relkind filter.
           and case when c.relkind = 'S' then has_sequence_privilege(%s, c.oid, 'USAGE')
                    else false end""", role)
    # Our own functions. An extension's (pgcrypto's digest, gen_random_uuid...)
    # read no table, and locally pgcrypto lives in public, not `extensions`.
    functions = _rows(db, """
        select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and has_function_privilege(%s, p.oid, 'EXECUTE')
           and not exists (select 1 from pg_depend d where d.classid = 'pg_proc'::regclass
                            and d.objid = p.oid and d.deptype = 'e')""", role)
    assert (tables, sequences, functions) == ([], [], []), (
        "the public key must reach nothing; every read and write goes through the API")


def test_no_policy_names_the_public_supabase_roles(db):
    assert _rows(db, """
        select tablename, policyname from pg_policies
         where schemaname = 'public' and roles && array['anon', 'authenticated']::name[]""") == []


def test_tables_created_later_grant_the_public_roles_nothing(db):
    """Supabase's defaults grant anon and authenticated everything on each new
    table; 0026 took that back, so the next migration cannot reopen the door."""
    granted = _rows(db, """
        select pg_get_userbyid(d.defaclrole), d.defaclobjtype, d.defaclacl::text
          from pg_default_acl d join pg_namespace n on n.oid = d.defaclnamespace
         where n.nspname = 'public'
           and (d.defaclacl::text ~ '(^|[{,])anon=' or d.defaclacl::text ~ '(^|[{,])authenticated=')""")
    assert granted == []


def test_every_table_has_row_level_security(db):
    missing = {row[0] for row in _rows(db, """
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity""")}
    assert missing <= RUNNER_TABLES


def test_the_api_login_reaches_every_table_it_is_meant_to(db):
    """Production broke this until 0027: business_phone_numbers had row-level
    security, no policy and no grant for the API there, because 0015 ran on
    Supabase before the API's role existed. Run this query against a database
    to find the same drift."""
    unreachable = _rows(db, """
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind in ('r', 'p')
           and not (c.relname = any(%s))
           and (not has_table_privilege(current_user, c.oid, 'SELECT')
                or (c.relrowsecurity and not exists (
                      select 1 from pg_policies p
                       where p.schemaname = 'public' and p.tablename = c.relname
                         and current_user = any(p.roles))))""", list(RUNNER_TABLES))
    assert unreachable == []


def test_views_run_with_the_callers_rights(db):
    definer_views = _rows(db, """
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'v'
           and not coalesce('security_invoker=true' = any(c.reloptions), false)""")
    assert definer_views == [], "a definer view would read past row-level security"


def test_no_security_definer_function_has_an_open_search_path(db):
    unsafe = _rows(db, """
        select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.prosecdef
           and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c
                            where c like 'search_path=%%')""")
    assert unsafe == []
