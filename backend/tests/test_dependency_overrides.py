"""Who may call what, and what happens when a call's collaborators fail.

ROLES, through FastAPI's dependency injection. Every staff route declares its
gate in its signature (Depends(require_staff), Depends(require_role(...))).
The routes are DISCOVERED from the app and their minimum role READ from those
dependencies, so a route added later is covered without being listed. Then
require_staff is overridden to sign in as viewer, admin and owner in turn,
and each route must let in exactly the roles it declares (CLAUDE.md: enrol,
dependants and payments are admin and owner; replying on WhatsApp and the
staff list are owner only; viewer reads only).

FAILURES, by replacing a collaborator: the database, the mail and WhatsApp
senders, Supabase's signing keys. Each must end in a coded answer a ticket
can be filed under, never a bare 500, and never cost a saved lead.
"""

from __future__ import annotations

import re
import uuid

import jwt
import psycopg
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

from app import auth, db as db_module
from app.auth import require_staff, require_staff_identity
from app.main import app
from app.routers import enquiries

RANK = {"viewer": 0, "admin": 1, "owner": 2}
WRITES = {"POST", "PUT", "PATCH", "DELETE"}
# POSTs that only read: a search sent in the body so it stays out of URLs
# (test_staff_search.py). Named one by one, so a new viewer-level POST has to
# be added here on purpose rather than slipping through.
READ_ONLY_POSTS = {"/api/admin/enquiries/search", "/api/admin/members/search"}


def _declared_minimum(route: APIRoute) -> str | None:
    """'viewer' for require_staff alone, 'admin'/'owner' for require_role(...),
    None for routes that are not behind require_staff at all."""
    found: set[str] = set()

    def walk(dependant) -> None:
        for dependency in dependant.dependencies:
            call = dependency.call
            if call is require_staff:
                found.add("viewer")
            for cell in getattr(call, "__closure__", None) or ():
                try:
                    value = cell.cell_contents
                except ValueError:
                    continue
                if value in RANK:
                    found.add(value)
            walk(dependency)

    walk(route.dependant)
    return max(found, key=RANK.get) if found else None


def _staff_routes() -> list[tuple[str, str, str]]:
    found = []
    for route in app.routes:
        for candidate in getattr(route, "original_router", None) and \
                route.original_router.routes or [route]:
            if isinstance(candidate, APIRoute) and candidate.path.startswith("/api/admin"):
                minimum = _declared_minimum(candidate)
                if minimum:
                    for method in sorted(candidate.methods):
                        found.append((method, candidate.path, minimum))
    return found


STAFF_ROUTES = _staff_routes()


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda m: "0" if m.group(0) == "{index}" else str(uuid.uuid4()), path)


@pytest.fixture
def as_role():
    def sign_in(role: str) -> None:
        user = auth.StaffUser(user_id=str(uuid.uuid4()), email=f"{role}@staff.test",
                              role=role, staff_id=str(uuid.uuid4()))
        app.dependency_overrides[require_staff] = lambda: user
    yield sign_in
    app.dependency_overrides.pop(require_staff, None)


def test_the_route_discovery_finds_the_staff_routes():
    assert len(STAFF_ROUTES) >= 25
    assert ("POST", "/api/admin/members", "admin") in STAFF_ROUTES
    assert ("POST", "/api/admin/whatsapp/escalations/{escalation_id}/reply", "owner") in STAFF_ROUTES


@pytest.mark.parametrize("method, path, minimum",
                         [r for r in STAFF_ROUTES if r[0] in WRITES and "/2fa/" not in r[1]
                          and r[1] not in READ_ONLY_POSTS])
def test_no_staff_write_is_open_to_a_viewer(method, path, minimum):
    """Declared, not just enforced: a write without a role gate fails here
    before anyone has to try it. (The 2fa routes act on the caller's own
    sign-in and are covered by test_two_step_*.)"""
    assert RANK[minimum] >= RANK["admin"], f"{method} {path} must require admin or owner"


def test_the_read_only_posts_are_searches_open_to_every_role():
    declared = {(path, minimum) for method, path, minimum in STAFF_ROUTES if method == "POST"}
    for path in READ_ONLY_POSTS:
        assert path.endswith("/search")
        assert (path, "viewer") in declared, f"{path} is not a viewer-level POST route"


@pytest.mark.parametrize("role", list(RANK))
@pytest.mark.parametrize("method, path, minimum", STAFF_ROUTES,
                         ids=[f"{m} {p}" for m, p, _ in STAFF_ROUTES])
def test_each_role_gets_exactly_what_the_route_declares(client, as_role, role, method, path, minimum):
    as_role(role)

    response = client.request(method, _concrete(path), json={})

    if RANK[role] < RANK[minimum]:
        assert response.status_code == 403, f"{role} must not pass {method} {path}"
        assert response.json()["code"] == "forbidden"
    else:
        # Past the gate: what follows (404 for a made-up id, 422 for an empty
        # body, 503 for an unconfigured service) is the route's own business.
        assert response.status_code not in (401, 403), response.json()


def test_the_injected_identity_is_who_the_route_acts_as(client, as_role):
    as_role("viewer")
    assert client.get("/api/admin/me").json() | {"id": None} == {
        "email": "viewer@staff.test", "role": "viewer", "id": None}


def test_without_an_override_every_staff_route_wants_a_token(client):
    assert require_staff not in app.dependency_overrides
    for method, path, _ in STAFF_ROUTES:
        response = client.request(method, _concrete(path), json={})
        assert response.status_code == 401, f"{method} {path}"
        assert response.json()["code"] == "not_signed_in"


# --- The database fails ----------------------------------------------------------------

class _Unreachable:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def connection(self, *args, **kwargs):
        raise self.error


@pytest.mark.parametrize("error", [psycopg.OperationalError("connection refused"),
                                   PoolTimeout("couldn't get a connection after 30.00 sec")],
                         ids=["database-down", "pool-exhausted"])
@pytest.mark.parametrize("method, path, body", [
    ("POST", "/api/enquiries", {"first_name": "Sipho", "surname": "Zulu",
                                "mobile_number": "0820000004", "contact_consent": True}),
    ("PATCH", f"/api/enquiries/{uuid.uuid4()}/application", {"terms_accepted": True}),
    ("GET", "/api/admin/enquiries", None),
    ("GET", "/api/admin/members", None),
    ("GET", "/api/admin/instalments", None),
], ids=["stage-1", "stage-2", "staff-enquiries", "staff-members", "staff-payments"])
def test_a_database_outage_is_a_coded_503_not_a_500(client, as_role, monkeypatch,
                                                    error, method, path, body):
    as_role("admin")
    monkeypatch.setattr(db_module, "_pool", _Unreachable(error))

    response = client.request(method, path, json=body)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    payload = response.json()
    assert payload["code"] == "database_unavailable"
    assert payload["request_id"] == response.headers["x-request-id"]
    assert "connection refused" not in response.text  # the server's text stays inside


# --- A notifier fails -------------------------------------------------------------------

def _events(db, enquiry_id: str) -> dict[str, dict]:
    return {row[0]: row[1] for row in db.execute(
        "select event_type, payload from enquiry_events where enquiry_id = %s",
        (enquiry_id,)).fetchall()}


def test_a_mail_sender_that_raises_still_keeps_the_lead_and_says_so(client, db, monkeypatch):
    def broken(_row):
        raise RuntimeError("template bug")

    monkeypatch.setattr(enquiries, "send_new_lead", broken)

    response = client.post("/api/enquiries", json={
        "first_name": "Sipho", "surname": "Zulu", "mobile_number": "0820000005",
        "contact_consent": True})

    assert response.status_code == 201
    events = _events(db, response.json()["id"])
    assert "lead_captured" in events
    assert events["lead_email_failed"]["error"] == "email_failed"


def test_a_whatsapp_sender_that_raises_still_keeps_the_application(client, db, monkeypatch):
    def broken(**_kwargs):
        raise ConnectionError("twilio unreachable")

    monkeypatch.setattr(enquiries, "send_registration_confirmation", broken)
    lead = client.post("/api/enquiries", json={
        "first_name": "Sipho", "surname": "Zulu", "mobile_number": "0820000006",
        "contact_consent": True}).json()

    response = client.patch(f"/api/enquiries/{lead['id']}/application",
                            json={"terms_accepted": True})

    assert response.status_code == 200
    assert _events(db, lead["id"])["whatsapp_failed"]["error"] == "whatsapp_failed"


# --- Supabase's signing keys fail -------------------------------------------------------

class _Keys:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_signing_key_from_jwt(self, _token):
        raise self.error


def test_unreachable_sign_in_keys_are_a_503_not_a_sign_in_loop(client, two_step, monkeypatch):
    two_step("off")
    monkeypatch.setattr(auth, "_client", lambda: _Keys(jwt.PyJWKClientConnectionError("down")))

    response = client.get("/api/admin/me", headers={"Authorization": "Bearer x.y.z"})

    assert response.status_code == 503
    assert response.json()["code"] == "upstream_failed"


def test_a_token_signed_by_a_key_we_do_not_know_is_still_401(client, two_step, monkeypatch):
    two_step("off")
    monkeypatch.setattr(auth, "_client", lambda: _Keys(jwt.PyJWKClientError("no matching key")))

    response = client.get("/api/admin/me", headers={"Authorization": "Bearer x.y.z"})

    assert response.status_code == 401
    assert response.json()["code"] == "not_signed_in"


# --- A bug ------------------------------------------------------------------------------

def test_an_unexpected_error_is_json_with_a_request_id_and_no_internals(client, monkeypatch):
    def bug(_key):
        raise RuntimeError("internal detail 8001015009087 must not leave")

    monkeypatch.setattr(enquiries, "_find_by_key", bug)
    # Not `with TestClient(...)`: that would run the lifespan again and close
    # the pool the session's `client` opened, under every test that follows.
    anonymous = TestClient(app, raise_server_exceptions=False)
    response = anonymous.post(
        "/api/enquiries",
        json={"first_name": "Sipho", "surname": "Zulu", "mobile_number": "0820000007",
              "contact_consent": True},
        headers={"Idempotency-Key": str(uuid.uuid4()), "X-Request-ID": "ticket-test-0001"})

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Something went wrong on our side. Please try again, or phone us.",
        "code": "internal_error", "request_id": "ticket-test-0001"}
    assert response.headers["x-request-id"] == "ticket-test-0001"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "8001015009087" not in response.text


def test_require_staff_identity_is_never_overridden_by_these_tests():
    assert require_staff_identity not in app.dependency_overrides
