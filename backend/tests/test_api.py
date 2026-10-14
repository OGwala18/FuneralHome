"""What must stay true before this API takes real registrations.

Each check runs against a real Postgres built from db/migrations, connected as
the restricted API role, because the bugs worth catching live in the SQL, the
grants and the row-level security rather than in Python alone.

No real person appears here. The ID numbers are generated, with a valid check
digit, and the mobile number is a placeholder that is never messaged: conftest
switches every notification channel off.
"""

from __future__ import annotations

import random
import re
import uuid

import psycopg
import pytest

from app import main
from app.schemas import valid_sa_id


def _lead(**overrides) -> dict:
    payload = {
        "first_name": "Test",
        "surname": "Applicant",
        "mobile_number": "082 000 0001",
        "plan_interest": "plan_a",
        "contact_consent": True,
    }
    payload.update(overrides)
    return payload


def _synthetic_id_number() -> str:
    """A made-up SA ID number that passes the same check the API applies."""
    body = "%02d%02d%02d%04d08" % (
        random.randint(50, 99), random.randint(1, 12), random.randint(1, 28),
        random.randint(0, 9999),
    )
    return next(body + str(d) for d in range(10) if valid_sa_id(body + str(d)))


def _count(db, query: str, *params) -> int:
    return db.execute(query, params).fetchone()[0]


# --- /health -------------------------------------------------------------------

def test_health_is_200_when_the_database_answers(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "up"


def test_health_is_503_when_the_database_does_not(client, monkeypatch):
    def unreachable():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "connection", unreachable)
    response = client.get("/health")

    # Railway and uptime monitors read any 2xx as healthy.
    assert response.status_code == 503
    assert response.json()["database"] == "down"


# --- Stage 1 -------------------------------------------------------------------

def test_stage_one_saves_one_lead_and_one_lead_captured_event(client, db):
    response = client.post("/api/enquiries", json=_lead())

    assert response.status_code == 201
    body = response.json()
    assert re.fullmatch(r"IND-\d{4}-\d{6}", body["reference"])
    assert body["mobile_number"] == "+27820000001"

    assert db.execute(
        "select stage::text, status::text from plan_enquiries where id = %s", (body["id"],)
    ).fetchall() == [("lead", "new")]
    assert _count(
        db,
        "select count(*) from enquiry_events where enquiry_id = %s and event_type = 'lead_captured'",
        body["id"],
    ) == 1


@pytest.mark.parametrize(
    "change, field",
    [
        ({"mobile_number": "12345"}, "mobile_number"),
        ({"contact_consent": False}, "contact_consent"),
        ({"first_name": ""}, "first_name"),
        ({"website": "https://spam.example"}, "website"),  # the honeypot
        ({"account_number": "123"}, "account_number"),  # unknown fields are refused
    ],
)
def test_an_invalid_lead_is_422_and_saves_nothing(client, db, change, field):
    before = _count(db, "select count(*) from plan_enquiries")

    response = client.post("/api/enquiries", json=_lead(**change))

    assert response.status_code == 422
    assert field in response.json()["field_errors"]
    assert _count(db, "select count(*) from plan_enquiries") == before


# --- Stage 2 -------------------------------------------------------------------

def test_stage_two_promotes_the_same_enquiry_rather_than_adding_one(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]
    id_number = _synthetic_id_number()
    before = _count(db, "select count(*) from plan_enquiries")

    response = client.patch(
        f"/api/enquiries/{enquiry_id}/application",
        json={"id_number": id_number, "plan_selected": "plan_a", "terms_accepted": True},
    )

    assert response.status_code == 200
    assert response.json()["id"] == enquiry_id
    assert _count(db, "select count(*) from plan_enquiries") == before
    assert db.execute(
        "select stage::text, status::text, id_number from plan_enquiries where id = %s",
        (enquiry_id,),
    ).fetchall() == [("application", "application_submitted", id_number)]
    assert _count(
        db,
        "select count(*) from enquiry_events "
        "where enquiry_id = %s and event_type = 'application_submitted'",
        enquiry_id,
    ) == 1


def test_an_invalid_application_is_422_and_leaves_the_lead_alone(client, db):
    enquiry_id = client.post("/api/enquiries", json=_lead()).json()["id"]

    response = client.patch(
        f"/api/enquiries/{enquiry_id}/application",
        json={"id_number": "1234567890123", "terms_accepted": True},
    )

    assert response.status_code == 422
    assert "id_number" in response.json()["field_errors"]
    assert db.execute(
        "select stage::text from plan_enquiries where id = %s", (enquiry_id,)
    ).fetchall() == [("lead",)]


def test_an_application_for_an_unknown_enquiry_is_404(client):
    response = client.patch(
        f"/api/enquiries/{uuid.uuid4()}/application", json={"terms_accepted": True}
    )

    assert response.status_code == 404


# --- The staff gate --------------------------------------------------------------

def _staff_routes() -> list[tuple[str, str]]:
    """Every staff route the app actually registers, found rather than listed,
    so a route added later is checked without anyone remembering to add it."""
    # Read from the OpenAPI schema rather than app.routes: FastAPI now wraps
    # included routers in a private type, and the schema is the public view.
    found = []
    for path, operations in main.app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            concrete = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
            found += [(method.upper(), concrete) for method in sorted(operations)]
    return found


def test_there_are_staff_routes_to_check():
    assert len(_staff_routes()) >= 9


@pytest.mark.parametrize("method, path", _staff_routes())
def test_staff_routes_refuse_a_caller_without_a_token(client, method, path):
    response = client.request(method, path, json={})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
