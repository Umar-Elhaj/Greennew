"""GREEN Map missions: grid, waypoints, export, placement of analyses, heatmap (lot 5)."""

import math

from conftest import jpeg_bytes, register

LAT0, LNG0 = 3.85, 11.50
M_LAT = 1 / 111195.0
M_LNG = 1 / (111195.0 * math.cos(math.radians(LAT0)))
RECT = {"type": "Polygon", "coordinates": [[[LNG0, LAT0], [LNG0 + 50 * M_LNG, LAT0], [LNG0 + 50 * M_LNG, LAT0 + 20 * M_LAT],
                                            [LNG0, LAT0 + 20 * M_LAT], [LNG0, LAT0]]]}


def _parcel(client, h, geometry=RECT):
    return client.post("/api/parcels", json={"name": "Grid", "geometry": geometry}, headers=h).json()["id"]


def _mission(client, h, pid, size=5):
    r = client.post("/api/missions", json={"parcel_id": pid, "cell_size_m": size}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, h, color, **data):
    r = client.post("/api/camera/analyze-frame",
                    files={"file": ("f.jpg", jpeg_bytes(color=color), "image/jpeg")},
                    data={k: str(v) for k, v in data.items()}, headers=h)
    return r


def test_preview_then_create_and_waypoints(client, user):
    h = user["headers"]
    pid = _parcel(client, h)
    prev = client.post("/api/missions/preview", json={"parcel_id": pid, "cell_size_m": 5}, headers=h).json()
    assert prev["cells_total"] == 40
    assert client.get("/api/missions", headers=h).json() == []        # preview saves nothing

    m = _mission(client, h, pid)
    assert m["status"] == "draft" and m["cells_total"] == 40 and m["progress"]["analysed_cells"] == 0
    wp = client.get(f"/api/missions/{m['id']}/waypoints", headers=h).json()
    assert wp["crs"] == "EPSG:4326" and len(wp["waypoints"]) == 40
    assert set(wp["waypoints"][0]) == {"index", "cell_index", "lat", "lng", "capture"}

    gj = client.get(f"/api/missions/{m['id']}/export.geojson", headers=h)
    assert gj.headers["content-type"].startswith("application/geo+json")
    kinds = [f["properties"]["kind"] for f in gj.json()["features"]]
    assert kinds.count("cell") == 40 and kinds.count("path") == 1 and kinds[0] == "parcel"

    r = client.patch(f"/api/missions/{m['id']}", json={"status": "ready", "name": "Passage 1"}, headers=h)
    assert r.json()["status"] == "ready"
    assert client.patch(f"/api/missions/{m['id']}", json={"status": "flying"}, headers=h).status_code == 422


def test_too_many_cells_message(client, user):
    h = {**user["headers"], "Accept-Language": "fr"}
    big = {"type": "Polygon", "coordinates": [[[LNG0, LAT0], [LNG0 + 1000 * M_LNG, LAT0],
                                               [LNG0 + 1000 * M_LNG, LAT0 + 1000 * M_LAT], [LNG0, LAT0 + 1000 * M_LAT],
                                               [LNG0, LAT0]]]}
    pid = _parcel(client, h, big)
    r = client.post("/api/missions/preview", json={"parcel_id": pid, "cell_size_m": 5}, headers=h)
    assert r.status_code == 422 and r.json()["detail"].startswith("Trop de cellules (plus de 5000)")


def test_missions_are_private(client, user, other_user):
    m = _mission(client, user["headers"], _parcel(client, user["headers"]))
    oh = other_user["headers"]
    for path in ("", "/waypoints", "/heatmap", "/export.geojson"):
        assert client.get(f"/api/missions/{m['id']}{path}", headers=oh).status_code == 404
    other_pid = _parcel(client, oh)
    assert client.post("/api/missions", json={"parcel_id": other_pid}, headers=user["headers"]).status_code == 404
    # nor can analyses be attached to someone else's mission
    assert _upload(client, oh, (1, 2, 3), mission_id=m["id"], cell_index=1).status_code == 404


def test_placement_rules(client, user, fake_model):
    h = user["headers"]
    pid = _parcel(client, h)
    m = _mission(client, h, pid)
    assert _upload(client, h, (200, 9, 9), mission_id=m["id"], cell_index=41).status_code == 422
    other = _parcel(client, h)
    assert _upload(client, h, (9, 200, 8), mission_id=m["id"], parcel_id=other).status_code == 422
    assert _upload(client, h, (9, 9, 200), cell_index=3).status_code == 422          # cell without mission
    assert fake_model == []

    # GPS only: the cell and the parcel are found by point-in-polygon
    cell7 = next(c for c in m["grid"] if c["index"] == 7)
    r = _upload(client, h, (120, 60, 6), mission_id=m["id"], latitude=cell7["center"][1], longitude=cell7["center"][0])
    a = client.get(f"/api/analysis/{r.json()['analysis_id']}", headers=h).json()
    assert a["parcel_id"] == pid
    r = _upload(client, h, (60, 120, 200), latitude=LAT0 + 10 * M_LAT, longitude=LNG0 + 10 * M_LNG,
                captured_at="2026-10-20T08:30:00+01:00")
    a = client.get(f"/api/analysis/{r.json()['analysis_id']}", headers=h).json()
    assert a["parcel_id"] == pid


def test_full_scenario_six_analyses_heatmap(client, user, fake_model, monkeypatch):
    """parcel -> mission -> 6 simulated analyses -> heatmap values known in advance."""
    import rover_common

    plan = iter([
        ("Corn_Streak", "high", 0.92), ("healthy", "none", 0.95),         # cell 1: 1 of 2 diseased
        ("Corn_Streak", "medium", 0.70), ("Corn_Streak", "low", 0.50),     # cell 2: 2 of 2
        ("Corn_Leaf_Blight", "medium", 0.60),                              # cell 3: 1 of 1
        ("healthy", "none", 0.90),                                          # cell 5: 0 of 1
    ])

    def predict(_bytes):
        code, sev, conf = next(plan)
        return {"class_raw": code if code != "healthy" else "Corn_Healthy", "detected_disease": code,
                "disease_name": code, "plant_type": "Corn", "confidence": conf, "severity": sev, "top3": []}

    monkeypatch.setattr(rover_common, "predict", predict)
    h = user["headers"]
    m = _mission(client, h, _parcel(client, h))
    for i, cell in enumerate([1, 1, 2, 2, 3, 5]):
        assert _upload(client, h, (i * 40, 10, 20), mission_id=m["id"], cell_index=cell).status_code == 200

    hm = client.get(f"/api/missions/{m['id']}/heatmap", headers=h).json()
    by = {c["index"]: c for c in hm["cells"]}
    assert set(by) == {1, 2, 3, 5}
    assert (by[1]["analyses"], by[1]["diseased"], by[1]["rate"], by[1]["max_alert"]) == (2, 1, 0.5, "high")
    assert (by[2]["rate"], by[2]["max_alert"], by[2]["dominant"]) == (1.0, "medium", "Corn_Streak")
    assert by[3]["dominant"] == "Corn_Leaf_Blight"
    assert (by[5]["rate"], by[5]["max_alert"], by[5]["dominant"]) == (0.0, "none", None)
    assert hm["mission"]["progress"] == {"analysed_cells": 4, "total_cells": 40, "ratio": 0.1}
    assert hm["diseases"] == ["Corn_Leaf_Blight", "Corn_Streak"]

    only = client.get(f"/api/missions/{m['id']}/heatmap?disease=Corn_Leaf_Blight", headers=h).json()
    assert [c["index"] for c in only["cells"]] == [3]

    # deleting the mission keeps the analyses, without the link
    assert client.delete(f"/api/missions/{m['id']}", headers=h).status_code == 200
    assert client.get("/api/analysis/history", headers=h).json()["total"] == 6
