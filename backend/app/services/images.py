"""What kind of picture a file really is, and how big, from its own bytes.

The homepage banner photo is uploaded from the staff portal and then served to
every visitor of the public website, so the API never trusts the filename or
the Content-Type the browser claims. It reads the file's signature and its
header for the width and height, and refuses anything else.

No imaging library: three formats, each with a fixed header layout, are a few
dozen lines, and a parser that only reads headers cannot be made to run a
decoder's bugs. The portal has already re-drawn the photo on a canvas (which
also drops its EXIF, GPS position included); this is the API's own check that
what arrived is what the portal sends.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageInfo:
    content_type: str
    width: int
    height: int


class NotAnImage(ValueError):
    """The bytes are not a JPEG, PNG or WebP this module can measure."""


def inspect(data: bytes) -> ImageInfo:
    """The real type and size of `data`, or NotAnImage."""
    if data.startswith(b"\xff\xd8\xff"):
        width, height = _jpeg_size(data)
        return ImageInfo("image/jpeg", width, height)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ImageInfo("image/png", *_png_size(data))
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ImageInfo("image/webp", *_webp_size(data))
    raise NotAnImage("Not a JPEG, PNG or WebP image.")


def _jpeg_size(data: bytes) -> tuple[int, int]:
    # Walk the marker segments to the first start-of-frame (SOF0-SOF15, but not
    # DHT C4, JPG C8 or DAC CC), which holds height then width.
    i = 2
    length = len(data)
    while i + 4 <= length:
        if data[i] != 0xFF:
            raise NotAnImage("A JPEG marker was expected.")
        marker = data[i + 1]
        if marker == 0xFF:          # fill byte
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            i += 2
            continue
        if marker == 0xD9:          # end of image before any frame
            break
        (segment,) = struct.unpack(">H", data[i + 2:i + 4])
        if segment < 2:
            raise NotAnImage("A JPEG segment is malformed.")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 > length:
                break
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            if width and height:
                return width, height
            break
        i += 2 + segment
    raise NotAnImage("The JPEG has no readable size.")


def _png_size(data: bytes) -> tuple[int, int]:
    # The first chunk must be IHDR: width and height, big-endian.
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise NotAnImage("The PNG has no header chunk.")
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height:
        raise NotAnImage("The PNG has no size.")
    return width, height


def _webp_size(data: bytes) -> tuple[int, int]:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        # 24-bit little-endian canvas width-1 and height-1.
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    raise NotAnImage("The WebP has no readable size.")
