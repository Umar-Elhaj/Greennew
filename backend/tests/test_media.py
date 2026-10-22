"""Lot 2 — image storage: validation, re-encoding, thumbnails, access control."""

import io
import os
import re

from PIL import Image

import media
from conftest import jpeg_bytes, register
from database import SessionLocal
from models import DiseaseAnalysis, User


def _upload(client, headers, content=None, data=None, ctype="image/jpeg"):
    return client.post("/api/camera/upload", files={"file": ("leaf.jpg", content or jpeg_bytes(), ctype)},
                       data=data or {}, headers=headers)


def _jpeg_with_gps(lat=(3, 52, 0), lon=(11, 31, 0)) -> bytes:
    img = Image.new("RGB", (800, 600), (30, 140, 40))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"                      # Make: must be stripped
    gps = {1: "N", 2: tuple(float(x) for x in lat), 3: "E", 4: tuple(float(x) for x in lon)}
    exif[0x8825] = gps
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _set(user_id, **fields):
    db = SessionLocal()
    u = db.get(User, user_id)
    for k, v in fields.items():
        setattr(u, k, v)
    db.commit()
    db.close()


def _row(aid):
    db = SessionLocal()
    a = db.get(DiseaseAnalysis, aid)
    db.close()
    return a


# ---- storage layout ------------------------------------------
def test_layout_thumbnail_and_metadata(client, user, fake_model):
    body = _upload(client, user["headers"], content=_jpeg_with_gps()).json()
    a = _row(body["analysis_id"])
    assert re.fullmatch(r"\d{4}/\d{2}/[0-9a-f]{32}\.jpg", a.image_path)
    full = os.path.join(media.MEDIA_DIR, a.image_path)
    thumb = full[:-4] + "_thumb.jpg"
    assert os.path.exists(full) and os.path.exists(thumb)
    assert (a.image_width, a.image_height) == (800, 600)
    assert a.image_bytes == os.path.getsize(full)
    assert len(a.image_sha256) == 64
    with Image.open(thumb) as t:
        assert t.width == 320
    with Image.open(full) as f:
        assert not f.getexif(), "EXIF must be stripped from the stored file"


def test_gps_kept_only_with_consent(client, user, fake_model):
    a = _row(_upload(client, user["headers"], content=_jpeg_with_gps()).json()["analysis_id"])
    assert a.latitude is None and a.longitude is None

    _set(user["user"]["id"], location_consent=True)
    a = _row(_upload(client, user["headers"], content=_jpeg_with_gps(lat=(4, 3, 0))).json()["analysis_id"])
    assert abs(a.latitude - (4 + 3 / 60)) < 1e-6 and abs(a.longitude - (11 + 31 / 60)) < 1e-6


def test_explicit_position_wins_over_exif(client, user, fake_model):
    _set(user["user"]["id"], location_consent=True)
    body = _upload(client, user["headers"], content=_jpeg_with_gps(),
                   data={"latitude": "5.5", "longitude": "10.4"}).json()
    a = _row(body["analysis_id"])
    assert (a.latitude, a.longitude) == (5.5, 10.4)


def test_consents_editable_and_returned(client, user):
    r = client.put("/api/auth/me", json={"dataset_consent": True, "location_consent": True},
                   headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["dataset_consent"] is True and r.json()["location_consent"] is True
    assert r.json()["role"] == "farmer"
    r = client.put("/api/auth/me", json={"role": "admin"}, headers=user["headers"])
    assert client.get("/api/auth/me", headers=user["headers"]).json()["role"] == "farmer"


# ---- upload validation ---------------------------------------
def test_fake_image_with_image_content_type_rejected(client, user, fake_model):
    r = _upload(client, user["headers"], content=b"\xff\xd8\xff not really a jpeg" * 10)
    assert r.status_code == 415
    assert fake_model == []


def test_png_accepted_and_reencoded_as_jpeg(client, user, fake_model):
    buf = io.BytesIO()
    Image.new("RGBA", (100, 80), (0, 200, 0, 128)).save(buf, format="PNG")
    body = _upload(client, user["headers"], content=buf.getvalue(), ctype="image/png").json()
    with Image.open(os.path.join(media.MEDIA_DIR, _row(body["analysis_id"]).image_path)) as f:
        assert f.format == "JPEG" and f.mode == "RGB"


def test_upload_size_limit(client, user, fake_model, monkeypatch):
    monkeypatch.setattr(media, "MAX_UPLOAD_MB", 1)
    big = os.urandom(1024 * 1024 + 10)
    r = _upload(client, user["headers"], content=big)
    assert r.status_code == 413
    assert fake_model == []


def test_parcel_of_another_user_rejected(client, user, other_user, fake_model):
    pid = client.post("/api/parcels", json={"name": "P"}, headers=other_user["headers"]).json()["id"]
    r = _upload(client, user["headers"], data={"parcel_id": str(pid)})
    assert r.status_code == 404
    assert fake_model == []


# ---- access control ------------------------------------------
def test_signed_url_and_thumbnail(client, user, fake_model):
    body = _upload(client, user["headers"]).json()
    r = client.get(body["image_path"])               # signed, no header: <img src>
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert "private" in r.headers["cache-control"]
    t = client.get(body["thumb_path"])
    assert t.status_code == 200 and len(t.content) <= len(r.content)


def test_tampered_or_expired_signature(client, user, other_user, fake_model):
    url = _upload(client, user["headers"]).json()["image_path"]
    assert client.get(url[:-2] + "xx").status_code == 401
    # someone else's id with the owner's signature
    forged = re.sub(r"u=\d+", f"u={other_user['user']['id']}", url)
    assert client.get(forged).status_code == 401
    path = url.split("?")[0][len("/api/media/"):]
    uid = user["user"]["id"]
    expired = f"/api/media/{path}?u={uid}&exp=1000&sig={media._signature(path, uid, 1000)}"
    assert client.get(expired).status_code == 401


def test_agronomist_and_admin_can_read(client, user, fake_model):
    path = _upload(client, user["headers"]).json()["image_path"].split("?")[0]
    agro = register(client)
    assert client.get(path, headers=agro["headers"]).status_code == 403
    _set(agro["user"]["id"], role="agronomist")
    assert client.get(path, headers=agro["headers"]).status_code == 200
    partner = register(client)
    _set(partner["user"]["id"], role="partner")
    assert client.get(path, headers=partner["headers"]).status_code == 403


def test_path_traversal_and_unknown_paths(client, user, fake_model):
    _upload(client, user["headers"])
    h = user["headers"]
    for p in ["../config.py", "..%2F..%2Fconfig.py", "2026/10/../../../backend/config.py",
              "%2e%2e/%2e%2e/etc/passwd", "2026/10/notauuid.jpg", "/etc/passwd"]:
        assert client.get(f"/api/media/{p}", headers=h).status_code in (404, 401), p


def test_media_not_publicly_mounted(client):
    from main import app
    from starlette.routing import Mount

    assert not any(isinstance(r, Mount) and r.path == "/api/media" for r in app.routes)


def test_delete_removes_files(client, user, fake_model):
    aid = _upload(client, user["headers"]).json()["analysis_id"]
    full = os.path.join(media.MEDIA_DIR, _row(aid).image_path)
    assert client.delete(f"/api/analysis/{aid}", headers=user["headers"]).status_code == 200
    assert not os.path.exists(full) and not os.path.exists(full[:-4] + "_thumb.jpg")


def test_dedup_is_per_user(client, user, other_user, fake_model):
    img = jpeg_bytes(color=(1, 2, 3))
    a = _upload(client, user["headers"], content=img).json()
    b = _upload(client, other_user["headers"], content=img).json()
    assert a["analysis_id"] != b["analysis_id"]
    assert len(fake_model) == 2
