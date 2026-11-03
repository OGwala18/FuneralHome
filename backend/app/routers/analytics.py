"""The owner's Analytics page: the live public site's Plausible figures.

Owner only, decided 3 Nov 2026. Every environment reads the LIVE site
(induduzo.co.za), so internal shows real visitors while the page itself is
being tested. Counts only: see services/plausible.py.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..auth import require_role, require_staff
from ..services import plausible

router = APIRouter(prefix="/api/admin/analytics", tags=["admin"],
                   dependencies=[Depends(require_staff)])


class Totals(BaseModel):
    visitors: int
    visits: int
    pageviews: int
    bounce_rate: float
    visit_duration: float
    views_per_visit: float


class Bucket(BaseModel):
    bucket: str
    visitors: int
    pageviews: int


class Action(BaseModel):
    goal: str
    visitors: int
    events: int
    conversion_rate: float


class Click(BaseModel):
    goal: str
    where: str
    events: int


class Outbound(BaseModel):
    url: str
    events: int


class Page(BaseModel):
    page: str
    visitors: int
    pageviews: int


class Tally(BaseModel):
    label: str
    visitors: int


class Step(BaseModel):
    label: str
    goal: str | None
    visitors: int


class SiteStats(BaseModel):
    period: str
    site: str
    fetched_at: str
    totals: Totals
    series: list[Bucket]
    actions: list[Action]
    clicks_by_place: list[Click]
    clicks_by_page: list[Click]
    outbound: list[Outbound]
    pages: list[Page]
    sources: list[Tally]
    devices: list[Tally]
    cities: list[Tally]
    path: list[Step]


@router.get("", response_model=SiteStats, dependencies=[Depends(require_role("owner"))])
async def site_stats(
    period: Literal["day", "7d", "28d", "91d"] = Query(default="28d"),
) -> SiteStats:
    """Visitors, pages, sources and the clicks the site reports, for one period."""
    try:
        stats = await run_in_threadpool(plausible.site_stats, period)
    except plausible.PlausibleError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    return SiteStats(**stats)
