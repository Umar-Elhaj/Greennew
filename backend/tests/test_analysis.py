import pytest

from conftest import jpeg_bytes


def _upload(client, headers, data=None, content=None, endpoint="/api/camera/upload"):
    content = content or jpeg_bytes()
    return client.post(endpoint, files={"file": ("leaf.jpg", content, "image/jpeg")},
                       data=data or {}, headers=headers)


@pytest.mark.parametrize("endpoint", ["/api/camera/upload", "/api/camera/analyze-frame"])
def test_upload_runs_model_and_stores_analysis(client, user, fake_model, endpoint):
    r = _upload(client, user["headers"], endpoint=endpoint)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["disease"]["detected_disease"] == "Corn_Leaf_Blight"
    assert body["fiche_terrain"]["winner"]["type"] == "disease"
    assert len(fake_model) == 1

    hist = client.get("/api/analysis/history", headers=user["headers"]).json()
    assert hist["total"] == 1
    assert hist["items"][0]["id"] == body["analysis_id"]


def test_upload_requires_auth(client, fake_model):
    r = client.post("/api/camera/upload", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code in (401, 403)
    assert fake_model == []


def test_upload_rejects_non_image(client, user, fake_model):
    r = client.post("/api/camera/upload", files={"file": ("a.txt", b"hello", "text/plain")},
                    headers=user["headers"])
    assert r.status_code == 415
    assert fake_model == []


def test_analysis_is_private_and_deletable(client, user, other_user, fake_model):
    aid = _upload(client, user["headers"]).json()["analysis_id"]
    assert client.get(f"/api/analysis/{aid}", headers=other_user["headers"]).status_code == 404
    assert client.delete(f"/api/analysis/{aid}", headers=other_user["headers"]).status_code == 404

    r = client.get(f"/api/analysis/{aid}", headers=user["headers"])
    assert r.status_code == 200 and r.json()["fiche_terrain"]
    assert client.delete(f"/api/analysis/{aid}", headers=user["headers"]).status_code == 200
    assert client.get(f"/api/analysis/{aid}", headers=user["headers"]).status_code == 404


def test_dashboard_stats_count_analyses(client, user, fake_model):
    _upload(client, user["headers"])
    s = client.get("/api/dashboard/stats", headers=user["headers"]).json()
    assert s["analyses"] == 1 and s["diseases"] == 1 and s["healthy"] == 0


def test_media_requires_auth_and_ownership(client, user, other_user, fake_model):
    path = _upload(client, user["headers"]).json()["image_path"]
    assert path.startswith("/api/media/")
    path = path.split("?")[0]  # header-based access, without the signed query
    assert client.get(path).status_code == 401
    assert client.get(path, headers=other_user["headers"]).status_code == 403
    assert client.get(path, headers=user["headers"]).status_code == 200


def test_same_image_same_user_is_not_reanalysed(client, user, fake_model):
    img = jpeg_bytes()
    a = _upload(client, user["headers"], content=img).json()
    b = _upload(client, user["headers"], content=img).json()
    assert a["analysis_id"] == b["analysis_id"]
    assert b["duplicate"] is True and a["duplicate"] is False
    assert len(fake_model) == 1
