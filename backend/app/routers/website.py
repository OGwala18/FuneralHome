"""The homepage banner: staff change it in the portal, the website shows it.

PUBLIC (the website, no sign-in)
    GET  /api/site/banner                     the words and photo to show
    GET  /api/site/banner/images/{image_id}   a photo a banner uses

STAFF (the portal)
    GET  /api/admin/website/banner            what is live, and recent changes
    POST /api/admin/website/banner            save a new banner (admin, owner)
    POST /api/admin/website/banner/images     upload a photo (admin, owner)
    GET  /api/admin/website/banner/images/{image_id}   any photo, for previews

The banner history is append-only (migration 0032): saving is always a new
row, and the newest row is live. Blank words mean the website's own wording,
and no photo means its own photo, so "back to the standard banner" is a save
with everything blank.

The website asks once per page load. The answer may be cached for a minute,
and a photo for a year: each photo has its own address, and a new photo is a
new address, so a long cache can never show a stale one.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ..auth import StaffUser, require_role, require_staff
from ..config import get_settings
from ..db import connection
from ..errors import ApiError
from ..schemas import Line
from ..services import images
from ..services.staff import log_staff_event

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/api/site", tags=["website"])
admin_router = APIRouter(prefix="/api/admin/website", tags=["admin"],
                         dependencies=[Depends(require_staff)])

# The upload route, exactly; main.py lets only this path carry a photo-sized body.
IMAGE_UPLOAD_PATH = "/api/admin/website/banner/images"

# What the portal sends: 1920 x 800. The bounds leave room for another client
# while refusing a thumbnail or a poster-sized file.
MIN_WIDTH, MAX_WIDTH = 1200, 3840
MIN_HEIGHT, MAX_HEIGHT = 400, 2160

# Photos kept after a save: the live one plus those of the last few banners, so
# "put back last week's photo" is one click. Older ones are emptied.
KEEP_RECENT_BANNERS = 5

_BANNER_CACHE = "public, max-age=60"
_IMAGE_CACHE = "public, max-age=31536000, immutable"

_NO_PHOTO = "That photo is no longer available. Please upload it again."


class BannerOut(BaseModel):
    headline_en: str | None = None
    headline_zu: str | None = None
    message_en: str | None = None
    message_zu: str | None = None
    image_id: UUID | None = None
    # Relative to the API, e.g. /api/site/banner/images/<id>. Null: the site's own photo.
    image_url: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    updated_at: datetime | None = None


class BannerChange(BannerOut):
    id: UUID
    saved_by: str


class BannerAdminOut(BaseModel):
    current: BannerOut
    history: list[BannerChange]
    can_edit: bool
    recommended_width: int = 1920
    recommended_height: int = 800


class BannerIn(BaseModel):
    """A new banner. Blank or missing words mean the website's own wording."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    headline_en: Line | None = Field(default=None, max_length=120)
    headline_zu: Line | None = Field(default=None, max_length=120)
    message_en: Line | None = Field(default=None, max_length=300)
    message_zu: Line | None = Field(default=None, max_length=300)
    image_id: UUID | None = None


class ImageOut(BaseModel):
    id: UUID
    content_type: str
    width: int
    height: int
    byte_size: int


_BANNER_COLUMNS = """
    b.id, b.headline_en, b.headline_zu, b.message_en, b.message_zu, b.image_id,
    b.saved_by, b.created_at, i.width as image_width, i.height as image_height,
    (i.bytes is not null) as image_available
"""


def _banner(row: dict | None) -> BannerOut:
    if row is None:
        return BannerOut()
    has_image = row["image_id"] is not None and row["image_available"]
    return BannerOut(
        headline_en=row["headline_en"], headline_zu=row["headline_zu"],
        message_en=row["message_en"], message_zu=row["message_zu"],
        image_id=row["image_id"] if has_image else None,
        image_url=f"/api/site/banner/images/{row['image_id']}" if has_image else None,
        image_width=row["image_width"] if has_image else None,
        image_height=row["image_height"] if has_image else None,
        updated_at=row["created_at"],
    )


def _current(conn) -> dict | None:
    return conn.execute(
        f"""
        select {_BANNER_COLUMNS}
          from website_banners b
          left join website_banner_images i on i.id = b.image_id
         order by b.created_at desc, b.id desc
         limit 1
        """
    ).fetchone()


def _blank(value: str | None) -> str | None:
    return value or None


# --------------------------------------------------------------- public ---

@public_router.get("/banner", response_model=BannerOut)
def public_banner(response: Response) -> BannerOut:
    """What the homepage shows. Everything null: the site's standard banner."""
    with connection() as conn:
        banner = _banner(_current(conn))
    response.headers["Cache-Control"] = _BANNER_CACHE
    return banner


@public_router.get("/banner/images/{image_id}")
def public_banner_image(image_id: UUID) -> Response:
    """A photo, but only one a saved banner has used. An upload nobody saved
    stays private to the portal."""
    with connection() as conn:
        row = conn.execute(
            """
            select i.content_type, i.bytes
              from website_banner_images i
             where i.id = %s and i.bytes is not null
               and exists (select 1 from website_banners b where b.image_id = i.id)
            """,
            (image_id,),
        ).fetchone()
    if row is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", "No such photo.")
    return Response(content=bytes(row["bytes"]), media_type=row["content_type"],
                    headers={"Cache-Control": _IMAGE_CACHE})


# ---------------------------------------------------------------- staff ---

@admin_router.get("/banner", response_model=BannerAdminOut)
def admin_banner(staff: StaffUser = Depends(require_staff)) -> BannerAdminOut:
    with connection() as conn:
        rows = conn.execute(
            f"""
            select {_BANNER_COLUMNS}
              from website_banners b
              left join website_banner_images i on i.id = b.image_id
             order by b.created_at desc, b.id desc
             limit 10
            """
        ).fetchall()
    history = [BannerChange(id=r["id"], saved_by=r["saved_by"], **_banner(r).model_dump())
               for r in rows]
    return BannerAdminOut(
        current=_banner(rows[0] if rows else None),
        history=history,
        can_edit=staff.role in ("admin", "owner"),
    )


@admin_router.post("/banner", response_model=BannerOut, status_code=status.HTTP_201_CREATED)
def save_banner(payload: BannerIn,
                staff: StaffUser = Depends(require_role("admin"))) -> BannerOut:
    """Make this the live banner. The website shows it within a minute."""
    with connection() as conn:
        if payload.image_id is not None:
            usable = conn.execute(
                "select 1 from website_banner_images where id = %s and bytes is not null",
                (payload.image_id,),
            ).fetchone()
            if usable is None:
                raise ApiError(422, "image_not_accepted",
                               _NO_PHOTO)
        banner_id = conn.execute(
            """
            insert into website_banners
                   (headline_en, headline_zu, message_en, message_zu, image_id, saved_by)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (_blank(payload.headline_en), _blank(payload.headline_zu),
             _blank(payload.message_en), _blank(payload.message_zu),
             payload.image_id, staff.email),
        ).fetchone()["id"]
        pruned = _prune(conn)
        # What changed, never the words themselves: they are public anyway, but
        # the audit trail records actions, not content.
        log_staff_event(conn, staff.email, "website_banner_saved", str(banner_id), {
            "custom_headline": bool(payload.headline_en or payload.headline_zu),
            "custom_message": bool(payload.message_en or payload.message_zu),
            "custom_photo": payload.image_id is not None,
            "photos_pruned": pruned,
        })
        banner = _banner(_current(conn))
    logger.info("Homepage banner %s saved", banner_id)
    return banner


def _prune(conn) -> int:
    """Empty the photos no recent banner uses, keeping fresh uploads (someone
    may be mid-edit). The API cannot delete; the rows stay, with no bytes."""
    rows = conn.execute(
        """
        update website_banner_images i
           set bytes = null, pruned_at = now()
         where i.bytes is not null
           and i.created_at < now() - interval '1 day'
           and i.id not in (
                 select b.image_id from (
                   select image_id from website_banners
                    order by created_at desc, id desc
                    limit %s) b
                  where b.image_id is not null)
        returning i.id
        """,
        (KEEP_RECENT_BANNERS,),
    ).fetchall()
    return len(rows)


@admin_router.post("/banner/images", response_model=ImageOut,
                   status_code=status.HTTP_201_CREATED)
async def upload_banner_image(request: Request,
                              staff: StaffUser = Depends(require_role("admin"))) -> ImageOut:
    """The photo's bytes as the request body, as the portal sends them.

    Checked from the bytes themselves (services/images.py), never from the
    Content-Type or a filename. It is not live until a banner is saved with it.
    """
    data = await request.body()
    limit = get_settings().max_banner_image_bytes
    if not data or len(data) > limit:
        raise ApiError(422, "image_not_accepted",
                       f"Please choose a photo under {limit // 1_000_000} MB.")
    try:
        info = images.inspect(data)
    except images.NotAnImage:
        raise ApiError(422, "image_not_accepted",
                       "That file is not a photo we can use. Please choose a JPEG, PNG "
                       "or WebP photo.") from None
    if not (MIN_WIDTH <= info.width <= MAX_WIDTH and MIN_HEIGHT <= info.height <= MAX_HEIGHT):
        raise ApiError(422, "image_not_accepted",
                       f"That photo is {info.width} x {info.height} pixels. The banner needs "
                       f"one at least {MIN_WIDTH} x {MIN_HEIGHT}; 1920 x 800 is ideal.")

    with connection() as conn:
        image_id = conn.execute(
            """
            insert into website_banner_images
                   (content_type, bytes, byte_size, width, height, uploaded_by)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (info.content_type, data, len(data), info.width, info.height, staff.email),
        ).fetchone()["id"]
        log_staff_event(conn, staff.email, "website_banner_photo_uploaded", str(image_id), {
            "content_type": info.content_type, "width": info.width,
            "height": info.height, "bytes": len(data),
        })
    return ImageOut(id=image_id, content_type=info.content_type, width=info.width,
                    height=info.height, byte_size=len(data))


@admin_router.get("/banner/images/{image_id}")
def admin_banner_image(image_id: UUID) -> Response:
    """Any stored photo, saved or not, for the portal's previews."""
    with connection() as conn:
        row = conn.execute(
            "select content_type, bytes from website_banner_images "
            "where id = %s and bytes is not null",
            (image_id,),
        ).fetchone()
    if row is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", _NO_PHOTO)
    return Response(content=bytes(row["bytes"]), media_type=row["content_type"])
