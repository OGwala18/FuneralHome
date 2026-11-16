"""Two hundred registrations through a real server, at once, and an account of each.

The other checks prove one behaviour at a time through TestClient. This one
runs the business as it happens: a real Uvicorn server on a local port, eight
families submitting at the same time, real SMTP to tests/smtp_sink.py, and a
stand-in WhatsApp sender. Then it reads everything back and checks it adds up.

Every submission is a SCENARIO with its own X-Request-ID (flow-042-full), so a
failure says exactly which message, what was expected, what came back, and
the error code: the same id the server's log lines carry.

    lead_only     110  stage 1, then the family leaves (still a lead to phone)
    full           60  stage 1 then stage 2: office mail, applicant mail, WhatsApp
    double_tap     10  stage 1 sent twice with one Idempotency-Key: one row, one mail
    hostile        10  input the API must refuse with 422 and save nothing from
    mail_down      10  the mail server refuses: the lead is kept, the failure coded
                  ---
                  200

Round trip: every saved row is compared field by field with what was typed,
after the normalising the API promises (mobile to +27, email lower case,
names single-spaced). No personal data may appear in any log line.

Set FLOW_REPORT=path.json to keep the per-message report.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import random
import socket
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

import httpx
import pytest
import uvicorn

from app.main import app
from app.routers import enquiries
from app.schemas import valid_sa_id
from app.services.whatsapp import WhatsAppResult

WORKERS = 8
PLANS = ["plan_a", "plan_b", "plan_c", "dome_plan", "unsure"]
PRICES = {"plan_a": 35000, "plan_b": 25000}  # one-price plans (test_api.py)
FIRST = ["Sipho", "Thandeka", "Nomvula", "Bongani", "Zanele", "Mandla", "Lindiwe", "Themba"]
CITY = ["Pietermaritzburg", "Edendale", "Imbali", "Howick", "Mpophomeni", None]


@dataclass
class Outcome:
    n: int
    scenario: str
    request_id: str
    expected: list[int]
    got: list[int] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    ms: list[int] = field(default_factory=list)
    enquiry_id: str | None = None
    reference: str | None = None
    problem: str | None = None

    @property
    def ok(self) -> bool:
        return self.problem is None and self.got == self.expected


# --- A real server ---------------------------------------------------------------

@pytest.fixture
def live_server(client):
    """The app under Uvicorn on a free local port. `client` has opened the pool;
    lifespan stays off here so this server does not close it on the way out."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="warning",
                                           access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "Uvicorn did not start"
    yield f"http://127.0.0.1:{port}", server
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


@pytest.fixture
def whatsapp_outbox(monkeypatch):
    """Stands in for Twilio: keeps each confirmation and answers like a send."""
    sent: list[dict] = []
    lock = threading.Lock()

    def send(*, to_mobile: str, first_name: str, reference: str) -> WhatsAppResult:
        with lock:
            sent.append({"to": to_mobile, "reference": reference})
            return WhatsAppResult(sent=True, message_sid="SMflow" + uuid.uuid4().hex[:26])

    monkeypatch.setattr(enquiries, "send_registration_confirmation", send)
    return sent


# --- Scenario data -------------------------------------------------------------------

def _unique_id_number(db, used: set[str]) -> str:
    """A made-up ID with a valid check digit, born 1930-49 (other tests use
    1950-99), and not already in this throwaway database."""
    while True:
        body = "%02d%02d%02d%04d08" % (random.randint(30, 49), random.randint(1, 12),
                                       random.randint(1, 28), random.randint(0, 9999))
        number = next(body + str(d) for d in range(10) if valid_sa_id(body + str(d)))
        if number in used:
            continue
        if db.execute("select 1 from plan_enquiries where id_number = %s", (number,)).fetchone():
            continue
        used.add(number)
        return number


def _person(n: int, rng: random.Random) -> dict:
    """A lead as a person types it: stray spaces, local mobile format."""
    tag = "".join(chr(97 + (n // 26 ** i) % 26) for i in range(3))
    lead = {
        "first_name": f"  {rng.choice(FIRST)} ",
        "surname": f"Flow  Mkhize{tag}",
        "mobile_number": "0%d%d %03d %04d" % (rng.choice([6, 7, 8]), rng.randint(0, 9),
                                              rng.randint(0, 999), n),
        "plan_interest": rng.choice(PLANS),
        "language_preference": rng.choice(["zu", "en", "xh"]),
        "contact_consent": True,
        "marketing_consent": rng.random() < 0.3,
    }
    if rng.random() < 0.5:
        lead["email"] = f"Flow.{tag}{n}@Example.TEST"
    city = rng.choice(CITY)
    if city:
        lead["city"] = city
    return lead


HOSTILE = [
    ({"first_name": "Si\x00pho"}, "first_name"),
    ({"surname": '=HYPERLINK("http://x","click")'}, "surname"),
    ({"email": "admin,attacker@example.test"}, "email"),
    ({"surname": "Dlamini‮evil"}, "surname"),
    ({"first_name": "<script>alert(1)</script>"}, "first_name"),
    ({"contact_consent": False}, "contact_consent"),
    ({"website": "https://spam.example"}, "website"),
    ({"mobile_number": "+1 555 0100"}, "mobile_number"),
    ({"premium_amount_cents": 1}, "premium_amount_cents"),
    ({"city": "@SUM(A1:A9)"}, "city"),
]


def _expected_row(lead: dict) -> dict:
    """What the API promises to store for what was typed."""
    digits = "".join(c for c in lead["mobile_number"] if c.isdigit())
    return {
        "first_name": " ".join(lead["first_name"].split()),
        "surname": " ".join(lead["surname"].split()),
        "mobile_number": "+27" + digits[1:],
        "email": lead["email"].lower() if lead.get("email") else None,
        "city": lead.get("city"),
        "plan_interest": lead["plan_interest"],
        "language_preference": lead["language_preference"],
        "marketing_consent": lead["marketing_consent"],
    }


# --- The run --------------------------------------------------------------------------

def test_two_hundred_registrations_add_up(live_server, db, smtp_sink, whatsapp_outbox, caplog):
    base_url, _server = live_server
    rng = random.Random(20261113)
    used_ids: set[str] = set()
    rows_before = db.execute("select count(*) from plan_enquiries").fetchone()[0]

    plan: list[tuple[str, int]] = (
        [("lead_only", 110), ("full", 60), ("double_tap", 10), ("hostile", 10)]
    )
    jobs = []
    n = 0
    for scenario, count in plan:
        for _ in range(count):
            n += 1
            jobs.append((n, scenario, _person(n, rng)))
    id_numbers = {n: _unique_id_number(db, used_ids) for n, s, _ in jobs if s == "full"}
    typed: dict[int, dict] = {}

    def run(job) -> Outcome:
        n, scenario, lead = job
        request_id = f"flow-{n:03d}-{scenario}"
        headers = {"X-Request-ID": request_id,
                   # A different visitor each: the proxy's right-most entry.
                   "X-Forwarded-For": f"10.{n // 250}.{n % 250}.7"}
        expected = {"lead_only": [201], "full": [201, 200], "double_tap": [201, 201],
                    "hostile": [422], "mail_down": [201]}[scenario]
        out = Outcome(n, scenario, request_id, expected)
        with httpx.Client(base_url=base_url, timeout=30) as http:
            def call(method, path, body, extra=None):
                started = time.perf_counter()
                response = http.request(method, path, json=body, headers={**headers, **(extra or {})})
                out.ms.append(int((time.perf_counter() - started) * 1000))
                out.got.append(response.status_code)
                payload = response.json()
                if response.status_code >= 400:
                    out.codes.append(payload.get("code", "?"))
                if response.headers.get("x-request-id") != request_id:
                    out.problem = "response did not echo X-Request-ID"
                return response, payload

            if scenario == "hostile":
                change, field_name = HOSTILE[(n - 1) % len(HOSTILE)]
                _, body = call("POST", "/api/enquiries", {**lead, **change})
                if field_name not in body.get("field_errors", {}):
                    out.problem = f"422 did not name {field_name}: {body.get('field_errors')}"
                return out

            key = str(uuid.uuid4())
            response, body = call("POST", "/api/enquiries", lead, {"Idempotency-Key": key})
            if response.status_code != 201:
                return out
            out.enquiry_id, out.reference = body["id"], body["reference"]
            typed[n] = lead
            if scenario == "double_tap":
                again, body2 = call("POST", "/api/enquiries", lead, {"Idempotency-Key": key})
                if body2.get("id") != out.enquiry_id or again.headers.get("idempotent-replayed") != "true":
                    out.problem = "second tap was not a replay of the first"
            if scenario == "full":
                call("PATCH", f"/api/enquiries/{out.enquiry_id}/application", {
                    "id_number": id_numbers[n], "plan_selected": lead["plan_interest"]
                    if lead["plan_interest"] != "unsure" else "plan_a",
                    "payment_preference": "debit_order", "terms_accepted": True,
                    "notes": f"Flow {n}: line one\nline two"})
            return out

    with caplog.at_level("INFO"):
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            outcomes = list(pool.map(run, jobs))
        # The last ten while the mail server refuses: each lead is still kept.
        expected_mail = (sum(1 for o in outcomes if o.enquiry_id)
                         + 2 * sum(1 for o in outcomes if o.scenario == "full")
                         - sum(1 for o in outcomes
                               if o.scenario == "full" and not typed.get(o.n, {}).get("email")))
        _wait_for(lambda: len(smtp_sink.received) >= expected_mail, "first-batch mail")
        smtp_sink.mode = "auth_required"
        for _ in range(10):
            n += 1
            lead = _person(n, rng)
            jobs.append((n, "mail_down", lead))
            outcomes.append(run((n, "mail_down", lead)))
        elapsed = time.perf_counter() - started
        _wait_for(lambda: _events_settled(db, outcomes), "notification events")

    assert len(outcomes) == 200
    problems = [o for o in outcomes if not o.ok]
    _write_report(outcomes, elapsed)
    assert not problems, "\n" + "\n".join(
        f"{o.request_id}: expected {o.expected} got {o.got} codes={o.codes} {o.problem or ''}"
        for o in problems)

    saved = [o for o in outcomes if o.enquiry_id]
    # 180 accepted in the first batch (hostile saves nothing) + 10 while mail was down.
    assert len(saved) == 190
    assert db.execute("select count(*) from plan_enquiries").fetchone()[0] == rows_before + 190
    assert len({o.reference for o in saved}) == 190, "references must be unique"

    # Round trip: what is stored is what was typed, normalised as promised.
    mismatches = []
    for o in saved:
        row = db.execute(
            "select first_name, surname, mobile_number, email, city, plan_interest::text, "
            "language_preference::text, marketing_consent, stage::text, premium_amount_cents, "
            "id_number from plan_enquiries where id = %s", (o.enquiry_id,)).fetchone()
        expected = _expected_row(typed[o.n])
        actual = dict(zip(list(expected), row[:8]))
        if actual != expected:
            mismatches.append(f"{o.request_id}: stored {actual} != typed {expected}")
        if o.scenario == "full":
            plan_code = typed[o.n]["plan_interest"]
            plan_code = "plan_a" if plan_code == "unsure" else plan_code
            if (row[8], row[10], row[9]) != ("application", id_numbers[o.n], PRICES.get(plan_code)):
                mismatches.append(f"{o.request_id}: stage/id/premium {row[8:11]}")
        elif row[8] != "lead":
            mismatches.append(f"{o.request_id}: stage {row[8]}")
    assert not mismatches, "\n".join(mismatches)

    # Exactly one audit event per step, never two (the double taps included).
    counts = dict(db.execute(
        "select event_type, count(*) from enquiry_events where enquiry_id = any(%s) "
        "group by event_type", ([o.enquiry_id for o in saved],)).fetchall())
    assert counts.get("lead_captured") == 190
    assert counts.get("application_submitted") == 60
    assert counts.get("lead_email_sent") == 180
    assert counts.get("lead_email_failed") == 10
    assert counts.get("application_email_sent") == 60
    assert counts.get("whatsapp_sent") == 60
    failed_codes = {row[0] for row in db.execute(
        "select payload->>'error' from enquiry_events where enquiry_id = any(%s) "
        "and event_type = 'lead_email_failed'", ([o.enquiry_id for o in saved],)).fetchall()}
    assert failed_codes == {"email_auth_required"}

    # Mail: one office email per lead, threaded by reference, none twice.
    office = [m.message["X-Induduzo-Reference"] for m in smtp_sink.received
              if m.rcpt_to == ["office@induduzo.test"]]
    lead_refs = [o.reference for o in saved if o.scenario != "mail_down"]
    full_refs = [o.reference for o in saved if o.scenario == "full"]
    assert sorted(office) == sorted(lead_refs + full_refs)
    applicant = sorted(m.message["X-Induduzo-Reference"] for m in smtp_sink.received
                       if m.rcpt_to != ["office@induduzo.test"])
    assert applicant == sorted(o.reference for o in saved
                               if o.scenario == "full" and typed[o.n].get("email"))

    # WhatsApp: one confirmation per application, to the number as stored.
    assert sorted(m["reference"] for m in whatsapp_outbox) == sorted(full_refs)

    # Rule 9: nothing a family typed about themselves reaches a log line.
    for o in saved:
        lead = typed[o.n]
        for secret in (_expected_row(lead)["mobile_number"], _expected_row(lead)["email"],
                       _expected_row(lead)["surname"], id_numbers.get(o.n)):
            assert not secret or secret not in caplog.text, f"{o.request_id} leaked into the log"

    # Every request's log lines carry its id, so a ticket can find them.
    stamped = {getattr(record, "request_id", None) for record in caplog.records}
    assert {o.request_id for o in saved} <= stamped


# --- Helpers ---------------------------------------------------------------------------

def _wait_for(check, what: str, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


def _events_settled(db, outcomes) -> bool:
    """Background sends finish after the response; wait until each has
    recorded its outcome before counting."""
    ids = [o.enquiry_id for o in outcomes if o.enquiry_id]
    fulls = sum(1 for o in outcomes if o.scenario == "full" and o.enquiry_id)
    counts = dict(db.execute(
        "select split_part(event_type, '_', 1) || '_' || split_part(event_type, '_', 2), "
        "count(*) from enquiry_events where enquiry_id = any(%s) group by 1", (ids,)).fetchall())
    return (counts.get("lead_email", 0) >= len(ids)
            and counts.get("application_email", 0) >= fulls
            and counts.get("whatsapp_sent", 0) + counts.get("whatsapp_failed", 0) >= fulls)


def _write_report(outcomes: list[Outcome], elapsed: float) -> None:
    timings = sorted(ms for o in outcomes for ms in o.ms)
    summary = {
        "messages": len(outcomes),
        "ok": sum(o.ok for o in outcomes),
        "seconds": round(elapsed, 2),
        "requests": len(timings),
        "p50_ms": timings[len(timings) // 2],
        "p95_ms": timings[int(len(timings) * 0.95)],
        "max_ms": timings[-1],
        "by_scenario": {s: sum(1 for o in outcomes if o.scenario == s)
                        for s in dict.fromkeys(o.scenario for o in outcomes)},
    }
    print("\nFLOW SUMMARY", json.dumps(summary))
    path = os.getenv("FLOW_REPORT")
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"summary": summary, "messages": [asdict(o) for o in outcomes]},
                      handle, indent=2)
