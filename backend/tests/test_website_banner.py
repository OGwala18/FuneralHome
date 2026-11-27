"""The homepage banner: staff save it in the portal, the website reads it.

Covers the public read, the photo upload and its checks, who may save, the
append-only history, pruning, and the caching rules the website relies on.
"""

from __future__ import annotations

import struct

import pytest

from app.services import images

BANNER = "/api/site/banner"
ADMIN_BANNER = "/api/admin/website/banner"
UPLOAD = "/api/admin/website/banner/images"


def png(width: int = 1920, height: int = 800, padding: int = 2000) -> bytes:
    """Enough of a PNG for the header check: signature and IHDR."""
    ihdr = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
            + b"\x00\x00\x00\x00" + b"\x00" * padding)


def jpeg(width: int = 1920, height: int = 800) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = (b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width)
            + b"\x03" + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01")
    return b"\xff\xd8" + app0 + sof0 + b"\x00" * 1000 + b"\xff\xd9"


def webp_vp8x(width: int = 1920, height: int = 800) -> bytes:
    body = b"VP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00" \
        + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + body + b"\x00" * 500


def upload(client, data: bytes, content_type: str = "image/png"):
    return client.post(UPLOAD, content=data, headers={"Content-Type": content_type})


# --- reading a photo's real type and size ----------------------------------------

@pytest.mark.parametrize("data, kind", [
    (png(1920, 800), "image/png"),
    (jpeg(1920, 800), "image/jpeg"),
    (webp_vp8x(1920, 800), "image/webp"),
])
def test_the_photo_check_reads_type_and_size_from_the_bytes(data, kind):
    info = images.inspect(data)
    assert (info.content_type, info.width, info.height) == (kind, 1920, 800)


@pytest.mark.parametrize("data", [
    b"",
    b"GIF89a" + b"\x00" * 50,
    b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
    b"\xff\xd8\xff\xd9",           # a JPEG with no frame
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 4,
])
def test_anything_else_is_not_an_image(data):
    with pytest.raises(images.NotAnImage):
        images.inspect(data)


# --- the public read --------------------------------------------------------------

def test_the_website_can_always_read_the_banner(client):
    response = client.get(BANNER)
    assert response.status_code == 200
    assert set(response.json()) >= {"headline_en", "headline_zu", "message_en",
                                    "message_zu", "image_url", "updated_at"}
    # Cached briefly by browsers and Cloudflare; a change shows within a minute.
    assert response.headers["cache-control"] == "public, max-age=60"


def test_anonymous_callers_cannot_change_it(client):
    assert client.post(ADMIN_BANNER, json={"headline_en": "Hacked"}).status_code == 401
    assert upload(client, png()).status_code == 401
    assert client.get(ADMIN_BANNER).status_code == 401


def test_a_viewer_can_look_but_not_change_it(client, staff_as):
    staff_as("viewer")
    seen = client.get(ADMIN_BANNER)
    assert seen.status_code == 200 and seen.json()["can_edit"] is False
    assert client.post(ADMIN_BANNER, json={"headline_en": "No"}).status_code == 403
    assert upload(client, png()).status_code == 403


# --- saving ----------------------------------------------------------------------

def test_an_admin_saves_words_and_a_photo_and_the_website_shows_them(client, staff_as, db):
    staff_as("admin")
    photo = upload(client, png(1920, 800))
    assert photo.status_code == 201, photo.text
    image_id = photo.json()["id"]
    assert photo.json()["width"] == 1920

    # Uploaded but not yet saved: the public cannot fetch it.
    assert client.get(f"/api/site/banner/images/{image_id}").status_code == 404

    saved = client.post(ADMIN_BANNER, json={
        "headline_en": "  Caring for families since 1998  ",
        "message_en": "Open 24 hours: 069 706 0387",
        "headline_zu": "",
        "image_id": image_id,
    })
    assert saved.status_code == 201, saved.text

    live = client.get(BANNER).json()
    assert live["headline_en"] == "Caring for families since 1998"
    assert live["message_en"] == "Open 24 hours: 069 706 0387"
    assert live["headline_zu"] is None          # blank means the site's own words
    assert live["image_url"] == f"/api/site/banner/images/{image_id}"

    picture = client.get(live["image_url"])
    assert picture.status_code == 200
    assert picture.headers["content-type"] == "image/png"
    assert picture.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert picture.content == png(1920, 800)

    event = db.execute(
        "select payload from staff_events where event_type = 'website_banner_saved' "
        "order by created_at desc limit 1").fetchone()
    assert event[0]["custom_photo"] is True
    # The audit trail records the action, not the words.
    assert "Caring" not in str(event[0])


def test_going_back_to_the_standard_banner_is_a_blank_save(client, staff_as):
    staff_as("owner")
    client.post(ADMIN_BANNER, json={"headline_en": "Something seasonal"})
    assert client.post(ADMIN_BANNER, json={}).status_code == 201
    live = client.get(BANNER).json()
    assert [live[k] for k in ("headline_en", "message_en", "image_url")] == [None, None, None]


def test_every_save_is_kept_in_the_history(client, staff_as, db):
    staff_as("admin")
    before = db.execute("select count(*) from website_banners").fetchone()[0]
    client.post(ADMIN_BANNER, json={"headline_en": "First"})
    client.post(ADMIN_BANNER, json={"headline_en": "Second"})
    assert db.execute("select count(*) from website_banners").fetchone()[0] == before + 2
    history = client.get(ADMIN_BANNER).json()["history"]
    assert [h["headline_en"] for h in history[:2]] == ["Second", "First"]
    assert history[0]["saved_by"] == "admin@staff.test"


@pytest.mark.parametrize("bad", [
    {"headline_en": "x" * 121},
    {"message_en": "y" * 301},
    {"headline_en": "=HYPERLINK(\"http://evil\")"},
    {"headline_en": "Line one\nline two"},
    {"image_id": "not-a-uuid"},
    {"surprise": "field"},
])
def test_the_words_are_checked_like_every_other_form(client, staff_as, bad):
    staff_as("admin")
    assert client.post(ADMIN_BANNER, json=bad).status_code == 422


def test_a_photo_that_does_not_exist_cannot_be_saved(client, staff_as):
    staff_as("admin")
    response = client.post(ADMIN_BANNER, json={
        "image_id": "00000000-0000-0000-0000-00000000dead"})
    assert response.status_code == 422
    assert response.json()["code"] == "image_not_accepted"


# --- the upload's checks -----------------------------------------------------------

@pytest.mark.parametrize("data, content_type", [
    (b"<svg onload=alert(1)></svg>", "image/svg+xml"),
    (b"GIF89a" + b"\x00" * 100, "image/gif"),
    (b"plain text pretending", "image/png"),     # the label is never trusted
    (png(800, 600), "image/png"),                # too small for the banner
    (png(6000, 800), "image/png"),               # far too wide
    (b"", "image/png"),
])
def test_only_a_real_photo_of_a_usable_size_is_accepted(client, staff_as, data, content_type):
    staff_as("admin")
    response = upload(client, data, content_type)
    assert response.status_code == 422
    assert response.json()["code"] == "image_not_accepted"


def test_a_photo_sized_body_is_allowed_on_the_upload_route_only(client, staff_as):
    staff_as("admin")
    big = png(1920, 800, padding=600_000)          # over the 256 KB form limit
    assert upload(client, big).status_code == 201
    # The same body anywhere else is refused before it is read.
    assert client.post(ADMIN_BANNER, content=big,
                       headers={"Content-Type": "application/json"}).status_code == 413


def test_a_photo_over_two_megabytes_is_refused(client, staff_as):
    staff_as("admin")
    assert upload(client, png(1920, 800, padding=2_100_000)).status_code == 413


def test_the_portal_can_preview_an_unsaved_upload(client, staff_as):
    staff_as("viewer")
    staff_as("admin")
    image_id = upload(client, jpeg()).json()["id"]
    staff_as("viewer")
    preview = client.get(f"/api/admin/website/banner/images/{image_id}")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"


# --- pruning ---------------------------------------------------------------------

def test_old_photos_are_emptied_but_the_live_one_never(client, staff_as, db):
    staff_as("admin")
    old_id = upload(client, png()).json()["id"]
    client.post(ADMIN_BANNER, json={"image_id": old_id})
    live_id = upload(client, png()).json()["id"]
    # Age both past the one-day grace an in-progress edit gets.
    db.execute("update website_banner_images set created_at = now() - interval '3 days' "
               "where id in (%s, %s)", (old_id, live_id))
    # Push the old photo out of the last five banners.
    for n in range(5):
        client.post(ADMIN_BANNER, json={"headline_en": f"Words {n}", "image_id": live_id})

    old = db.execute("select bytes is null, pruned_at is not null from website_banner_images "
                     "where id = %s", (old_id,)).fetchone()
    live = db.execute("select bytes is not null from website_banner_images where id = %s",
                      (live_id,)).fetchone()
    assert old == (True, True)
    assert live == (True,)
    assert client.get(f"/api/site/banner/images/{old_id}").status_code == 404
    assert client.get(client.get(BANNER).json()["image_url"]).status_code == 200
