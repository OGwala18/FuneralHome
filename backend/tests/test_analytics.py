"""The owner's Analytics page: who may see it, and what it makes of Plausible.

Plausible itself is never called. The tests stand in for its answers, so a run
needs no key and costs nothing against the account's rate limit.
"""

from __future__ import annotations

import dataclasses
import io
import urllib.error

import pytest

from app.config import get_settings
from app.services import plausible


@pytest.fixture(autouse=True)
def _fresh_cache():
    plausible.clear_cache()
    yield
    plausible.clear_cache()


@pytest.fixture
def connected(monkeypatch):
    """Plausible configured, with a key that is never sent anywhere."""
    settings = dataclasses.replace(get_settings(), plausible_api_key="test-key")
    monkeypatch.setattr(plausible, "get_settings", lambda: settings)
    return settings


def _answers(body: dict) -> dict:
    """What Plausible would say to each of the page's queries."""
    dimensions = body.get("dimensions", [])
    if not dimensions:
        return {"results": [{"dimensions": [], "metrics": [40, 52, 130, 61.5, 74, 2.5]}]}
    if dimensions == ["time:day"]:
        return {"results": [{"dimensions": ["2026-11-02"], "metrics": [12, 30]}],
                "meta": {"time_labels": ["2026-11-01", "2026-11-02", "2026-11-03"]}}
    if dimensions == ["event:goal"]:
        return {"results": [{"dimensions": ["Call"], "metrics": [3, 4, 7.5]},
                            {"dimensions": ["WhatsApp"], "metrics": [5, 9, 12.5]},
                            {"dimensions": ["Visit /join"], "metrics": [18, 20, 45.0]}]}
    if dimensions == ["event:goal", "event:props:place"]:
        return {"results": [{"dimensions": ["WhatsApp", "floating button"], "metrics": [6]},
                            {"dimensions": ["Call", ""], "metrics": [4]}]}
    return {"results": []}


def test_only_an_owner_sees_the_analytics(client, staff_as):
    staff_as("admin")

    response = client.get("/api/admin/analytics")

    assert response.status_code == 403


def test_without_a_key_the_page_says_plausible_is_not_connected(client, staff_as):
    staff_as("owner")

    response = client.get("/api/admin/analytics")

    assert response.status_code == 503
    assert "PLAUSIBLE_API_KEY" in response.json()["detail"]


def test_plausibles_answers_become_the_pages_figures(client, staff_as, connected, monkeypatch):
    staff_as("owner")
    asked = []
    monkeypatch.setattr(plausible, "_post", lambda body: asked.append(body) or _answers(body))

    response = client.get("/api/admin/analytics", params={"period": "7d"})

    assert response.status_code == 200
    stats = response.json()
    assert stats["site"] == "induduzo.co.za"
    assert stats["totals"]["visitors"] == 40
    # A day with no visits is a zero, not a missing day.
    assert [(b["bucket"], b["visitors"]) for b in stats["series"]] == [
        ("2026-11-01", 0), ("2026-11-02", 12), ("2026-11-03", 0)]
    assert [a["goal"] for a in stats["actions"]] == ["Visit /join", "WhatsApp", "Call"]
    assert stats["clicks_by_place"][1] == {"goal": "Call", "where": "(not set)", "events": 4}
    assert [(s["label"], s["visitors"]) for s in stats["path"][:3]] == [
        ("Visited the site", 40), ("Looked at the plans", 18), ("Opened the register form", 0)]
    assert {body["date_range"] for body in asked} == {"7d"}


def test_a_second_look_within_five_minutes_does_not_ask_plausible_again(
        client, staff_as, connected, monkeypatch):
    staff_as("owner")
    asked = []
    monkeypatch.setattr(plausible, "_post", lambda body: asked.append(body) or _answers(body))

    client.get("/api/admin/analytics")
    first = len(asked)
    client.get("/api/admin/analytics")

    assert first > 0 and len(asked) == first


def test_an_unknown_period_is_422(client, staff_as):
    staff_as("owner")

    assert client.get("/api/admin/analytics", params={"period": "forever"}).status_code == 422


@pytest.mark.parametrize("code, says", [
    (401, "did not accept the API key"),
    (402, "Business plan"),
    (429, "limiting requests"),
])
def test_a_refusal_from_plausible_is_explained_and_the_key_never_shown(
        client, staff_as, connected, monkeypatch, caplog, code, says):
    staff_as("owner")

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "refused", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(plausible.urllib.request, "urlopen", refuse)

    with caplog.at_level("WARNING"):
        response = client.get("/api/admin/analytics")

    assert response.status_code in (502, 503)
    assert says in response.json()["detail"]
    assert "test-key" not in response.text
    assert "test-key" not in caplog.text
