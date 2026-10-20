"""The two-step sign-in tables from migration 0016, as the API role meets them.

What keeps these tables safe lives in the database: row-level security, what
each role may do, and the checks that refuse a code or a token in readable
form. So this runs against a real Postgres as induduzo_api, like the rest of
the suite. Every staff member here is invented, at @staff.test.
"""

from __future__ import annotations

import base64
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from cryptography.fernet import Fernet
from psycopg import sql

from app.services import two_step_crypto as crypto

TABLES = (
    "staff_mfa_challenges",
    "staff_totp_factors",
    "staff_passkeys",
    "staff_trusted_devices",
    "staff_session_verifications",
    "staff_recovery_codes",
)

PEPPER = secrets.token_urlsafe(32)
KEY = Fernet.generate_key().decode()


@pytest.fixture
def staff_id(db):
    email = f"two-step-{uuid.uuid4().hex[:12]}@staff.test"
    return db.execute(
        "insert into staff_users (email) values (%s) returning id", (email,)
    ).fetchone()[0]


def _valid(table: str, staff_id, now: datetime) -> dict:
    """One acceptable row per table, timed from `now` as the API will time it."""
    return {
        "staff_mfa_challenges": {
            "staff_user_id": staff_id, "session_id": uuid.uuid4(), "kind": "email_code",
            "code_hash": crypto.hash_code(PEPPER, uuid.uuid4(), crypto.new_code()),
            "created_at": now, "expires_at": now + timedelta(minutes=5),
        },
        "staff_totp_factors": {
            "staff_user_id": staff_id,
            "secret_encrypted": crypto.encrypt_secret(
                base64.b32encode(secrets.token_bytes(20)).decode(), [KEY]
            ),
        },
        "staff_passkeys": {
            "staff_user_id": staff_id, "credential_id": secrets.token_bytes(32),
            "public_key": secrets.token_bytes(77), "backup_eligible": False,
            "backed_up": False, "name": "Test laptop",
        },
        "staff_trusted_devices": {
            "staff_user_id": staff_id,
            "token_hash": crypto.hash_device_token(crypto.new_device_token()),
            "label": "Chrome on Windows",
            "created_at": now, "expires_at": now + timedelta(days=30),
        },
        "staff_session_verifications": {
            "staff_user_id": staff_id, "session_id": uuid.uuid4(), "method": "email_code",
            "verified_at": now, "expires_at": now + timedelta(hours=12),
        },
        "staff_recovery_codes": {
            "staff_user_id": staff_id, "batch_id": uuid.uuid4(),
            "code_hash": crypto.hash_code(PEPPER, staff_id, "ABCD-EFGH"),
        },
    }[table]


def _insert(db, table: str, row: dict):
    query = sql.SQL("insert into {} ({}) values ({}) returning id").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, row)),
        sql.SQL(", ").join(sql.Placeholder() * len(row)),
    )
    return db.execute(query, tuple(row.values())).fetchone()[0]


# --- Who may do what --------------------------------------------------------

@pytest.mark.parametrize("table", TABLES)
def test_row_level_security_is_on(db, table):
    assert db.execute(
        "select relrowsecurity from pg_class where oid = %s::regclass", (table,)
    ).fetchone() == (True,)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("table", TABLES + ("staff_users", "staff_events"))
def test_supabase_roles_get_nothing(db, table, role):
    # SECURITY.md rule 8: no privilege and no policy, so Supabase's Data API
    # can never serve these rows to anyone.
    privileges = db.execute(
        "select p from unnest(array['SELECT', 'INSERT', 'UPDATE', 'DELETE', "
        "'TRUNCATE', 'REFERENCES', 'TRIGGER']) as p "
        "where has_table_privilege(%s, %s, p)",
        (role, table),
    ).fetchall()
    policies = db.execute(
        "select policyname from pg_policies "
        "where schemaname = 'public' and tablename = %s and %s = any(roles)",
        (table, role),
    ).fetchall()

    assert privileges == []
    assert policies == []


@pytest.mark.parametrize("table", TABLES)
def test_the_api_role_reads_and_writes_but_never_deletes(db, table):
    def can(privilege: str) -> bool:
        return db.execute(
            "select has_table_privilege(current_user, %s, %s)", (table, privilege)
        ).fetchone()[0]

    assert can("SELECT") and can("INSERT") and can("UPDATE")
    assert not can("DELETE") and not can("TRUNCATE")


@pytest.mark.parametrize("table", TABLES)
def test_the_api_role_adds_and_reads_back_a_row(db, staff_id, table):
    row_id = _insert(db, table, _valid(table, staff_id, datetime.now(timezone.utc)))

    assert db.execute(
        sql.SQL("select staff_user_id from {} where id = %s").format(sql.Identifier(table)),
        (row_id,),
    ).fetchone() == (staff_id,)


# --- Rows the database refuses ----------------------------------------------
# A timedelta is taken from the row's own `now`.

@pytest.mark.parametrize(
    "table, change",
    [
        # Nothing readable: a code or a token that isn't a 32-byte digest.
        ("staff_mfa_challenges", {"code_hash": b"123456"}),
        ("staff_recovery_codes", {"code_hash": b"ABCD-EFGH"}),
        ("staff_trusted_devices", {"token_hash": secrets.token_urlsafe(32).encode()}),
        # Each challenge carries what its kind needs, and only that.
        ("staff_mfa_challenges", {"code_hash": None}),
        ("staff_mfa_challenges", {"kind": "passkey_sign_in"}),
        # Short lives stay short.
        ("staff_mfa_challenges", {"expires_at": timedelta(days=1)}),
        ("staff_trusted_devices", {"expires_at": timedelta(days=31)}),
        # An app is confirmed before it is active.
        ("staff_totp_factors", {"status": "active"}),
    ],
)
def test_a_row_that_breaks_the_rules_is_refused(db, staff_id, table, change):
    now = datetime.now(timezone.utc)
    row = _valid(table, staff_id, now)
    row.update({k: now + v if isinstance(v, timedelta) else v for k, v in change.items()})

    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(db, table, row)


def test_removing_an_app_wipes_its_secret(db, staff_id):
    factor_id = _insert(
        db, "staff_totp_factors", _valid("staff_totp_factors", staff_id, datetime.now(timezone.utc))
    )

    # Flagging it removed while the secret is still there is refused...
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "update staff_totp_factors set status = 'removed', removed_at = now() where id = %s",
            (factor_id,),
        )

    # ...so removal always takes the secret with it.
    db.execute(
        "update staff_totp_factors "
        "set status = 'removed', removed_at = now(), removed_by = 'system', "
        "    secret_encrypted = null "
        "where id = %s",
        (factor_id,),
    )
    assert db.execute(
        "select status, secret_encrypted from staff_totp_factors where id = %s", (factor_id,)
    ).fetchone() == ("removed", None)


def test_a_passkey_handle_is_at_most_64_bytes_and_one_per_person(db, staff_id):
    handle = secrets.token_bytes(64)
    db.execute(
        "update staff_users set webauthn_user_handle = %s where id = %s", (handle, staff_id)
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "update staff_users set webauthn_user_handle = %s where id = %s",
            (secrets.token_bytes(65), staff_id),
        )

    another = db.execute(
        "insert into staff_users (email) values (%s) returning id",
        (f"two-step-{uuid.uuid4().hex[:12]}@staff.test",),
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(
            "update staff_users set webauthn_user_handle = %s where id = %s", (handle, another)
        )
