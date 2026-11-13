"""The contract every response keeps, so issues can be read, routed and fixed.

Every error: `detail` for the screen, `code` from app/errors.py for whoever
triages it, `request_id` matching the X-Request-ID header and the log lines.
Every response: the browser-hardening headers and Cache-Control: no-store.
Every log line: no query-string values, which is where staff searches by
name and ID number travel.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import pytest

from app import observability
from app.db import tls_setting
from app.errors import CATALOG, code_for_status, describe
from app.request_context import (
    AccessLogRedactor,
    RequestContextMiddleware,
    redact_query,
    security_headers,
)

APP_DIR = Path(__file__).resolve().parents[1] / "app"
LEAD = {"first_name": "Sipho", "surname": "Zulu", "mobile_number": "0820000008",
        "contact_consent": True}


# --- Error bodies ----------------------------------------------------------------------

@pytest.mark.parametrize("method, path, body, status, code", [
    ("GET", "/api/nowhere", None, 404, "not_found"),
    ("DELETE", "/api/enquiries", None, 405, "method_not_allowed"),
    ("POST", "/api/enquiries", {"first_name": ""}, 422, "validation_failed"),
    ("GET", "/api/admin/me", None, 401, "not_signed_in"),
    ("PATCH", "/api/enquiries/nope/application", {"terms_accepted": True}, 404, "enquiry_not_found"),
], ids=["unknown-route", "wrong-method", "invalid", "no-token", "unknown-enquiry"])
def test_every_error_names_its_code_and_request(client, method, path, body, status, code):
    response = client.request(method, path, json=body)

    assert response.status_code == status
    payload = response.json()
    assert payload["code"] == code
    assert isinstance(payload["detail"], str) and payload["detail"]
    assert payload["request_id"] == response.headers["x-request-id"]


def test_a_rate_limited_caller_is_told_when_to_come_back(client):
    for _ in range(6):
        client.post("/api/enquiries", json=LEAD)

    response = client.post("/api/enquiries", json=LEAD)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) > 0


def test_a_duplicate_id_number_is_coded_for_the_office(client):
    from test_api import _synthetic_id_number

    id_number = _synthetic_id_number()
    first, second = (client.post("/api/enquiries", json=LEAD).json()["id"] for _ in range(2))
    client.patch(f"/api/enquiries/{first}/application",
                 json={"id_number": id_number, "terms_accepted": True})

    response = client.patch(f"/api/enquiries/{second}/application",
                            json={"id_number": id_number, "terms_accepted": True})

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_id_number"


# --- The request id ---------------------------------------------------------------------

def test_a_callers_own_request_id_is_kept(client):
    response = client.get("/health", headers={"X-Request-ID": "portal-7f3a9c21"})
    assert response.headers["x-request-id"] == "portal-7f3a9c21"


@pytest.mark.parametrize("unsafe", ["short", "has spaces in it", "x" * 65, "quote\"d-request",
                                    "<script>alert(1)</script>"])
def test_an_unsafe_request_id_is_replaced_not_echoed(client, unsafe):
    response = client.get("/health", headers={"X-Request-ID": unsafe})
    assert response.headers["x-request-id"] != unsafe
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


def test_each_request_gets_its_own_id(client):
    ids = {client.get("/health").headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5


# --- Headers on every response -----------------------------------------------------------

@pytest.mark.parametrize("method, path", [("GET", "/health"), ("GET", "/api/nowhere"),
                                          ("POST", "/api/enquiries"), ("GET", "/api/admin/me")])
def test_every_response_carries_the_hardening_headers(client, method, path):
    response = client.request(method, path, json={})

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    # Not deployed here, so no HSTS (it would pin localhost to HTTPS).
    assert "strict-transport-security" not in response.headers


def test_a_deployed_api_sends_hsts():
    assert (b"strict-transport-security", b"max-age=31536000; includeSubDomains") in \
        security_headers(deployed=True)


def test_a_route_that_sets_its_own_cache_rule_keeps_it():
    """The WhatsApp photo route says `private, no-store`; it must not get a second."""
    sent = []

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"cache-control", b"private, no-store")]})
        await send({"type": "http.response.body", "body": b""})

    async def capture(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = RequestContextMiddleware(inner, max_body_bytes=1024, deployed=False)
    asyncio.run(middleware({"type": "http", "headers": []}, receive, capture))

    cache = [value for name, value in sent[0]["headers"] if name == b"cache-control"]
    assert cache == [b"private, no-store"]


def test_the_cors_allowlist_lets_the_site_read_the_request_id(client):
    response = client.post("/api/enquiries", json={}, headers={"Origin": "http://localhost:8080"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_an_origin_outside_the_allowlist_is_not_granted(client):
    response = client.post("/api/enquiries", json={}, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_the_image_does_not_announce_its_server_software():
    dockerfile = (APP_DIR.parents[1] / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "--no-server-header" in dockerfile


# --- Logs and error reports -------------------------------------------------------------

@pytest.mark.parametrize("path, redacted", [
    ("/api/admin/members?search=8001015009087&limit=25", "/api/admin/members?search=*&limit=*"),
    ("/api/admin/enquiries?search=Dlamini", "/api/admin/enquiries?search=*"),
    ("/api/admin/instalments?view=overdue", "/api/admin/instalments?view=*"),
    ("/health", "/health"),
    ("/x?", "/x?*"),
])
def test_query_values_never_reach_the_access_log(path, redacted):
    assert redact_query(path) == redacted


def test_the_access_log_filter_rewrites_uvicorns_record():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                               '%s - "%s %s HTTP/%s" %d',
                               ("10.0.0.1:5000", "GET", "/api/admin/members?search=Zulu", "1.1", 200),
                               None)
    AccessLogRedactor().filter(record)
    assert "Zulu" not in record.getMessage()
    assert "search=*" in record.getMessage()


def test_error_reports_keep_parameter_names_but_not_searches():
    event = {"request": {"query_string": "search=Dlamini&limit=25", "data": {"x": 1}}}
    cleaned = observability._before_send(event, {})
    assert cleaned["request"]["query_string"] == "search=*&limit=*"
    assert "data" not in cleaned["request"]


def test_log_lines_carry_the_request_id(client, caplog):
    with caplog.at_level("INFO"):
        response = client.post("/api/enquiries", json=LEAD,
                               headers={"X-Request-ID": "log-line-check-01"})
    assert response.status_code == 201
    assert any(getattr(r, "request_id", None) == "log-line-check-01" for r in caplog.records)


# --- Encryption in transit ---------------------------------------------------------------

@pytest.mark.parametrize("url, environment, expected", [
    ("postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:5432/postgres", "production",
     {"sslmode": "require"}),
    ("postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:5432/postgres", "internal",
     {"sslmode": "require"}),
    ("postgresql://u:p@postgres.railway.internal:5432/railway", "internal", {}),
    ("postgresql://u:p@db.example.com/x?sslmode=verify-full", "production", {}),
    ("postgresql://u:p@localhost:5433/induduzo", "production", {}),
    ("postgresql://u:p@postgres:5432/induduzo", "production", {}),
    ("postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com/postgres", "development", {}),
], ids=["supabase-live", "supabase-internal", "railway-private", "operator-choice",
        "localhost", "docker-service", "laptop"])
def test_a_database_across_the_internet_must_use_tls(url, environment, expected):
    assert tls_setting(url, environment) == expected


# --- The catalogue ------------------------------------------------------------------------

def test_every_code_the_api_raises_is_in_the_catalogue():
    raised = set()
    for source in APP_DIR.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        raised |= set(re.findall(
            r'(?:ApiError|StaffGateError)\(\s*[^,()]+(?:\([^)]*\))?\s*,\s*"([a-z_]+)"', text))
    assert raised, "the pattern found nothing; it needs updating"
    missing = sorted(code for code in raised if code not in CATALOG)
    assert not missing, f"add these to app/errors.py CATALOG: {missing}"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 409, 413, 418, 422, 429, 500,
                                    502, 503, 504])
def test_every_status_maps_to_a_catalogued_code(status):
    assert code_for_status(status) in CATALOG


def test_every_catalogue_entry_is_complete():
    for code, info in CATALOG.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]+", code)
        assert info.code == code
        assert all([info.area, info.meaning, info.likely_cause, info.fix, info.who])


def test_twilio_codes_are_described_too():
    assert "TWILIO_CONTENT_SID" in describe("twilio_63016").meaning
    assert describe("twilio_99999") is not None
    assert describe("made_up_code") is None
