"""Reading the live public site's figures from Plausible's Stats API.

The website (frontend/src/lib/analytics.ts) reports visits and a handful of
clicks to Plausible, from induduzo.co.za only. This reads them back for the
owner's Analytics page. Read-only: nothing here writes to Plausible or stores
what it returns, beyond a few minutes' cache.

What comes back is counts. Plausible holds no names, numbers or ID numbers, and
the site strips query strings before anything is sent, so nothing here is
personal data. The key, though, reads every site on the Plausible account: it
lives in the environment, sealed, and is never returned, logged or sent on.

Stats API v2: https://plausible.io/docs/stats-api. It is a Business-plan
feature, so a downgrade shows up here as a refusal, not as wrong numbers.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import get_settings

logger = logging.getLogger(__name__)

# The periods the page offers, in Plausible's own names.
PERIODS = ("day", "7d", "28d", "91d")

# Plausible allows 600 queries an hour per key and one page load costs ten.
# Five minutes is fresh enough for a dashboard and keeps an owner who keeps
# refreshing well inside the limit.
_CACHE_SECONDS = 300
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()

# The goals set up in Plausible on 2 Nov 2026. Names must match exactly.
CLICK_GOALS = ["Call", "WhatsApp", "Email"]
OUTBOUND_GOAL = "Outbound Link: Click"

# The way to an application, in the order a family takes it. Each step counts
# visitors who reached it in the period, not strictly in this order, so a later
# step can occasionally exceed an earlier one.
PATH_STEPS = (
    ("Looked at the plans", "Visit /join"),
    ("Opened the register form", "Visit /register"),
    ("Sent an enquiry", "Enquiry sent"),
    ("Reached the details form", "Visit /register/details"),
    ("Sent a full application", "Application sent"),
)


class PlausibleError(Exception):
    """A refusal to show the owner, worded for them. Never carries the key."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def _post(body: dict[str, Any]) -> dict:
    """One Stats API query, parsed. Raises PlausibleError."""
    settings = get_settings()
    request = urllib.request.Request(
        settings.plausible_api_url + "/api/v2/query",
        data=json.dumps({"site_id": settings.plausible_site_id, **body}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % settings.plausible_api_key,
        },
    )
    site = settings.plausible_site_id
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Status only: the body is Plausible's wording about our query.
        logger.warning("Plausible refused a stats query with HTTP %s", exc.code)
        if exc.code == 401:
            raise PlausibleError("Plausible did not accept the API key. Create a new Stats "
                                 "API key and set it as PLAUSIBLE_API_KEY.") from None
        if exc.code in (402, 403):
            raise PlausibleError("Plausible refused: the Stats API needs the Business plan, "
                                 "and the key must belong to an account that can see %s."
                                 % site) from None
        if exc.code == 404:
            raise PlausibleError("Plausible has no site called %s." % site) from None
        if exc.code == 429:
            raise PlausibleError("Plausible is limiting requests. Try again in a few minutes.",
                                 status=503) from None
        raise PlausibleError("Plausible could not answer (HTTP %s)." % exc.code) from None
    except Exception:  # noqa: BLE001 - timeouts, DNS, bad JSON: all "unreachable" to the owner
        logger.warning("Plausible stats query failed to complete")
        raise PlausibleError("Could not reach Plausible. Try again shortly.", status=503) from None


def _queries(period: str) -> dict[str, dict]:
    """Every query the page needs, by name. Run together, read separately."""
    clicks = [["is", "event:goal", CLICK_GOALS]]

    def top(metrics: list[str], dimensions: list[str], limit: int, **extra: Any) -> dict:
        return {"metrics": metrics, "date_range": period, "dimensions": dimensions,
                "order_by": [[metrics[0], "desc"]], "pagination": {"limit": limit}, **extra}

    return {
        "totals": {"metrics": ["visitors", "visits", "pageviews", "bounce_rate",
                               "visit_duration", "views_per_visit"],
                   "date_range": period},
        "series": {"metrics": ["visitors", "pageviews"], "date_range": period,
                   "dimensions": ["time:hour" if period == "day" else "time:day"],
                   "include": {"time_labels": True}},
        "goals": {"metrics": ["visitors", "events", "conversion_rate"], "date_range": period,
                  "dimensions": ["event:goal"]},
        "by_place": top(["events"], ["event:goal", "event:props:place"], 30, filters=clicks),
        "by_page": top(["events"], ["event:goal", "event:page"], 30, filters=clicks),
        "outbound": top(["events"], ["event:props:url"], 10,
                        filters=[["is", "event:goal", [OUTBOUND_GOAL]]]),
        "pages": top(["visitors", "pageviews"], ["event:page"], 15),
        "sources": top(["visitors"], ["visit:source"], 10),
        "devices": top(["visitors"], ["visit:device"], 10),
        "cities": top(["visitors"], ["visit:city_name"], 10),
    }


def _shape(period: str, answers: dict[str, dict]) -> dict:
    """Plausible's answers, turned into the page's figures."""
    rows = {name: answer.get("results", []) for name, answer in answers.items()}

    totals = rows["totals"][0]["metrics"] if rows["totals"] else [0] * 6
    visitors, visits, pageviews, bounce_rate, visit_duration, views_per_visit = totals

    # Plausible returns only buckets that had visits. Its time_labels list every
    # bucket in the period, so a quiet day shows as zero rather than vanishing.
    by_bucket = {row["dimensions"][0]: row["metrics"] for row in rows["series"]}
    labels = answers["series"].get("meta", {}).get("time_labels") or sorted(by_bucket)
    series = [{"bucket": label,
               "visitors": by_bucket.get(label, [0, 0])[0],
               "pageviews": by_bucket.get(label, [0, 0])[1]} for label in labels]

    goals = {row["dimensions"][0]: row["metrics"] for row in rows["goals"]}
    actions = sorted(
        ({"goal": name, "visitors": m[0], "events": m[1], "conversion_rate": m[2]}
         for name, m in goals.items()),
        key=lambda action: action["events"], reverse=True)

    path = [{"label": "Visited the site", "goal": None, "visitors": visitors}]
    path += [{"label": label, "goal": goal, "visitors": goals.get(goal, [0])[0]}
             for label, goal in PATH_STEPS]

    def clicks(name: str, missing: str) -> list[dict]:
        return [{"goal": r["dimensions"][0], "where": r["dimensions"][1] or missing,
                 "events": r["metrics"][0]} for r in rows[name]]

    def tally(name: str) -> list[dict]:
        return [{"label": r["dimensions"][0] or "(none)", "visitors": r["metrics"][0]}
                for r in rows[name]]

    return {
        "period": period,
        "site": get_settings().plausible_site_id,
        "totals": {"visitors": visitors, "visits": visits, "pageviews": pageviews,
                   "bounce_rate": bounce_rate, "visit_duration": visit_duration,
                   "views_per_visit": views_per_visit},
        "series": series,
        "actions": actions,
        "clicks_by_place": clicks("by_place", "(not set)"),
        "clicks_by_page": clicks("by_page", "(unknown)"),
        "outbound": [{"url": r["dimensions"][0], "events": r["metrics"][0]}
                     for r in rows["outbound"]],
        "pages": [{"page": r["dimensions"][0], "visitors": r["metrics"][0],
                   "pageviews": r["metrics"][1]} for r in rows["pages"]],
        "sources": tally("sources"),
        "devices": tally("devices"),
        "cities": tally("cities"),
        "path": path,
    }


def site_stats(period: str) -> dict:
    """The page's figures for one period. Cached; raises PlausibleError."""
    if not get_settings().plausible_api_key:
        raise PlausibleError("Plausible isn't connected on this server. Set PLAUSIBLE_API_KEY.",
                             status=503)
    if period not in PERIODS:
        raise PlausibleError("Unknown period.", status=422)

    with _cache_lock:
        hit = _cache.get(period)
        if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
            return hit[1]

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {name: pool.submit(_post, body) for name, body in _queries(period).items()}
        answers = {name: future.result() for name, future in futures.items()}

    shaped = _shape(period, answers)
    shaped["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _cache_lock:
        _cache[period] = (time.monotonic(), shaped)
    return shaped


def clear_cache() -> None:
    """For the tests: forget every cached period."""
    with _cache_lock:
        _cache.clear()
