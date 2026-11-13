"""Staff search, with the search in the request body instead of the URL.

Staff search by name, mobile, reference and ID number. In a URL that text is
written down by every proxy and log on the way (Railway's edge included), so
the portal POSTs it to /search (13 Nov 2026). These check the POST answers
exactly as the old GET did, which stays for portal tabs opened before then.
"""

from __future__ import annotations

import uuid

import pytest


def _lead(client, surname: str, mobile: str = "082 000 0009") -> dict:
    response = client.post("/api/enquiries", json={
        "first_name": "Search", "surname": surname, "mobile_number": mobile,
        "contact_consent": True})
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def viewer(staff_as):
    # A read: the lowest staff role may search.
    return staff_as("viewer")


def test_an_enquiry_is_found_by_surname_mobile_and_reference(client, viewer):
    surname = f"Searchable{uuid.uuid4().hex[:8]}"
    lead = _lead(client, surname, "082 555 0199")

    for term in (surname, "+27825550199", lead["reference"]):
        page = client.post("/api/admin/enquiries/search", json={"search": term}).json()
        assert lead["id"] in {row["id"] for row in page["rows"]}, term


@pytest.mark.parametrize("filters", [
    {},
    {"search": "Searchable"},
    {"search": "nobody-has-this-name"},
    {"status": "new", "sort": "surname", "descending": False, "limit": 5, "offset": 0},
], ids=["everything", "a-name", "no-match", "filtered-and-sorted"])
def test_the_post_answers_exactly_as_the_old_get(client, viewer, filters):
    _lead(client, f"Searchable{uuid.uuid4().hex[:8]}")

    posted = client.post("/api/admin/enquiries/search", json=filters)
    got = client.get("/api/admin/enquiries",
                     params={k: str(v).lower() if isinstance(v, bool) else v
                             for k, v in filters.items()})

    assert posted.status_code == got.status_code == 200
    assert posted.json() == got.json()


@pytest.mark.parametrize("filters", [
    {},
    {"search": "nobody-has-this-name"},
    {"search": "8001015009087"},
    {"limit": 3, "offset": 1},
], ids=["everything", "no-match", "an-id-number", "paged"])
def test_the_member_search_answers_exactly_as_the_old_get(client, viewer, filters):
    posted = client.post("/api/admin/members/search", json=filters)
    got = client.get("/api/admin/members", params=filters)

    assert posted.status_code == got.status_code == 200
    assert posted.json() == got.json()


@pytest.mark.parametrize("path, body, field", [
    ("/api/admin/enquiries/search", {"search": "x", "sql": "1=1"}, "sql"),
    ("/api/admin/enquiries/search", {"limit": 5000}, "limit"),
    ("/api/admin/enquiries/search", {"sort": "password"}, "sort"),
    ("/api/admin/enquiries/search", {"search": "x" * 121}, "search"),
    ("/api/admin/members/search", {"limit": 0}, "limit"),
    ("/api/admin/members/search", {"offset": -1}, "offset"),
])
def test_a_search_body_is_validated_like_any_other(client, viewer, path, body, field):
    response = client.post(path, json=body)

    assert response.status_code == 422
    assert field in response.json()["field_errors"]


def test_a_status_that_does_not_exist_is_a_422_not_a_500(client, viewer):
    # The status is cast to the enquiry_status type in SQL; Postgres refuses an
    # unknown one, and that refusal is the caller's mistake.
    response = client.post("/api/admin/enquiries/search", json={"status": "not_a_status"})

    assert response.status_code == 422


def test_search_needs_a_staff_token(client):
    for path in ("/api/admin/enquiries/search", "/api/admin/members/search"):
        response = client.post(path, json={"search": "Dlamini"})
        assert response.status_code == 401
        assert response.json()["code"] == "not_signed_in"
