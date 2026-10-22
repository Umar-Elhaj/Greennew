# ============================================================
# GREEN App — Analysed images on disk
#
# Layout: MEDIA_DIR/<yyyy>/<mm>/<uuid>.jpg + <uuid>_thumb.jpg (320 px wide).
# The database keeps only the relative path, sha256, size and dimensions.
# Images are never public: GET /api/media/{path} requires either the
# Authorization header or a short-lived signed URL issued to a user who
# may see the image (an <img> tag cannot send the header).
# ============================================================

import base64
import hashlib
import hmac
import io
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from config import MAX_UPLOAD_MB, MEDIA_DIR, MEDIA_URL_PREFIX, SECRET_KEY

os.makedirs(MEDIA_DIR, exist_ok=True)

ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO = JPEG from some phone cameras
MAX_PIXELS = 50_000_000          # decompression-bomb guard (~ 8000 x 6000)
MAX_STORED_SIDE = 2048           # stored images are downscaled to this long side
THUMB_WIDTH = 320
JPEG_QUALITY = 88
SIGNED_URL_TTL = 3600            # seconds

# Only paths produced by save_image() are ever served.
MEDIA_PATH_RE = re.compile(r"^(\d{4}/\d{2}/[0-9a-f]{32})(_thumb)?\.jpg$")


@dataclass
class ProcessedImage:
    jpeg: bytes                  # re-encoded, orientation applied, no metadata
    thumb: bytes
    width: int
    height: int
    sha256: str                  # of the bytes as uploaded (duplicate detection)
    gps: Optional[Tuple[float, float]]


# ---- Upload validation --------------------------------------
async def read_upload(file: UploadFile) -> bytes:
    """Read at most MAX_UPLOAD_MB; larger files are refused without reading them fully."""
    limit = MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Image too large. Maximum {MAX_UPLOAD_MB} MB.")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    return data


def _gps_from_exif(img: Image.Image) -> Optional[Tuple[float, float]]:
    try:
        gps = img.getexif().get_ifd(0x8825)  # GPSInfo
        if not gps or 2 not in gps or 4 not in gps:
            return None

        def to_deg(dms, ref):
            d, m, s = (float(x) for x in dms)
            val = d + m / 60 + s / 3600
            return -val if ref in ("S", "W") else val

        lat = to_deg(gps[2], gps.get(1, "N"))
        lon = to_deg(gps[4], gps.get(3, "E"))
        if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0.0, 0.0):
            return round(lat, 7), round(lon, 7)
    except Exception:  # noqa: S110 — malformed EXIF must never block an analysis
        pass
    return None


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)  # no exif= → metadata dropped
    return buf.getvalue()


def process_image(raw: bytes) -> ProcessedImage:
    """
    Check that the bytes really are an image (Pillow verify(), then reopen),
    apply the EXIF orientation, re-encode as JPEG without any metadata and
    build the thumbnail. EXIF GPS is returned separately: the caller decides
    whether the user consented to keep it.
    """
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ACCEPTED_FORMATS:
            raise HTTPException(status_code=415, detail="Unsupported image format (JPEG, PNG or WebP).")
        img = Image.open(io.BytesIO(raw))
        gps = _gps_from_exif(img)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise HTTPException(status_code=415, detail="The file is not a valid image.")

    img.thumbnail((MAX_STORED_SIDE, MAX_STORED_SIDE))
    thumb = img.copy()
    if thumb.width > THUMB_WIDTH:
        thumb = thumb.resize((THUMB_WIDTH, max(1, round(thumb.height * THUMB_WIDTH / thumb.width))))

    return ProcessedImage(
        jpeg=_jpeg(img), thumb=_jpeg(thumb), width=img.width, height=img.height,
        sha256=hashlib.sha256(raw).hexdigest(), gps=gps,
    )


# ---- Storage ------------------------------------------------
def save_image(p: ProcessedImage) -> str:
    """Write image + thumbnail; return the path relative to MEDIA_DIR."""
    now = datetime.utcnow()
    stem = f"{now:%Y}/{now:%m}/{uuid.uuid4().hex}"
    os.makedirs(os.path.join(MEDIA_DIR, f"{now:%Y}", f"{now:%m}"), exist_ok=True)
    for suffix, data in (("", p.jpeg), ("_thumb", p.thumb)):
        with open(os.path.join(MEDIA_DIR, f"{stem}{suffix}.jpg"), "wb") as f:
            f.write(data)
    return f"{stem}.jpg"


def thumb_path(rel_path: str) -> str:
    return rel_path[:-4] + "_thumb.jpg"


def media_file(rel_path: Optional[str]) -> Optional[str]:
    """Absolute path on disk of a stored image, or None for anything not produced by save_image()."""
    if not rel_path or not MEDIA_PATH_RE.match(rel_path):
        return None
    filepath = os.path.abspath(os.path.join(MEDIA_DIR, rel_path))
    if not filepath.startswith(MEDIA_DIR + os.sep):
        return None
    return filepath


def delete_image(rel_path: Optional[str]) -> None:
    if not rel_path or not MEDIA_PATH_RE.match(rel_path):
        return
    for p in (rel_path, thumb_path(rel_path)):
        f = media_file(p)
        if f and os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass  # non-critical: media_report.py lists orphans


# ---- Signed URLs --------------------------------------------
def _signature(rel_path: str, user_id: int, exp: int) -> str:
    mac = hmac.new(SECRET_KEY.encode(), f"media|{rel_path}|{user_id}|{exp}".encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()[:18]).decode().rstrip("=")


def media_url(rel_path: Optional[str], user_id: int, thumb: bool = False) -> Optional[str]:
    """
    URL of a stored image for this user, valid SIGNED_URL_TTL seconds.
    Rounded expiry → the same URL for an hour, so browsers can cache it.
    """
    if not rel_path or not MEDIA_PATH_RE.match(rel_path):
        return None
    path = thumb_path(rel_path) if thumb else rel_path
    exp = (int(time.time()) // SIGNED_URL_TTL + 2) * SIGNED_URL_TTL
    return f"{MEDIA_URL_PREFIX}/{path}?u={user_id}&exp={exp}&sig={_signature(path, user_id, exp)}"


def verify_signed(rel_path: str, user_id: int, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    return hmac.compare_digest(_signature(rel_path, user_id, exp), sig)
