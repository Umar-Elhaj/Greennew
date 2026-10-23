import pytest

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[11.50, 3.84], [11.501, 3.84], [11.501, 3.841], [11.50, 3.841], [11.50, 3.84]]],
}


def test_parcel_crud(client, user):
    h = user["headers"]
    r = client.post("/api/parcels", json={"name": "Nord", "crop_type": "Maize", "geometry": SQUARE}, headers=h)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["latitude"] == pytest.approx(3.8404, abs=1e-3)
    assert p["longitude"] == pytest.approx(11.5004, abs=1e-3)

    assert [x["id"] for x in client.get("/api/parcels", headers=h).json()] == [p["id"]]

    r = client.put(f"/api/parcels/{p['id']}", json={"name": "Nord-Est"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "Nord-Est"

    assert client.delete(f"/api/parcels/{p['id']}", headers=h).status_code == 200
    assert client.get("/api/parcels", headers=h).json() == []


def test_parcels_are_private(client, user, other_user):
    p = client.post("/api/parcels", json={"name": "A"}, headers=user["headers"]).json()
    oh = other_user["headers"]
    assert client.get(f"/api/parcels/{p['id']}", headers=oh).status_code == 404
    assert client.put(f"/api/parcels/{p['id']}", json={"name": "hack"}, headers=oh).status_code == 404
    assert client.delete(f"/api/parcels/{p['id']}", headers=oh).status_code == 404
    assert client.get(f"/api/parcels/{p['id']}/analyses", headers=oh).status_code == 404


@pytest.mark.parametrize("geometry", [
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},   # bow-tie
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]},                   # < 3 points
    {"type": "Polygon", "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 0]]]},   # lng out of range
    {"type": "Point", "coordinates": [11.5, 3.8]},
])
def test_invalid_geometry_is_rejected(client, user, geometry):
    r = client.post("/api/parcels", json={"name": "bad", "geometry": geometry}, headers=user["headers"])
    assert r.status_code == 422


BUEA = {"type": "Polygon", "coordinates": [[[9.2410, 4.1590], [9.2420, 4.1590], [9.2420, 4.1600], [9.2410, 4.1600],
                                            [9.2410, 4.1590]]]}


def test_measures_and_region_are_computed_server_side(client, user):
    r = client.post("/api/parcels", json={"name": "Buea", "geometry": BUEA, "area_ha": 999, "region": ""},
                    headers=user["headers"])
    p = r.json()
    assert r.status_code == 201
    assert p["area_ha"] == pytest.approx(1.2286, rel=0.01)        # ~110.8 m x 110.9 m, client value ignored
    assert p["perimeter_m"] == pytest.approx(443, rel=0.01)
    assert p["region"] == "Sud-Ouest"                            # the old bounding boxes said "Littoral"
    ring = p["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]


def test_invalid_geometry_message_is_translated(client, user):
    bowtie = {"type": "Polygon", "coordinates": [[[11.5, 3.8], [11.6, 3.9], [11.6, 3.8], [11.5, 3.9], [11.5, 3.8]]]}
    r = client.post("/api/parcels", json={"name": "x", "geometry": bowtie},
                    headers={**user["headers"], "Accept-Language": "fr"})
    assert r.status_code == 422
    assert r.json()["detail"] == "Le contour de la parcelle se croise lui-même."


def test_offline_creation_replay_is_idempotent(client, user):
    body = {"name": "Hors ligne", "geometry": SQUARE, "client_id": "6f1c2a7e-0000-4000-8000-000000000001"}
    a = client.post("/api/parcels", json=body, headers=user["headers"])
    b = client.post("/api/parcels", json=body, headers=user["headers"])
    assert a.status_code == 201 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]
    assert len(client.get("/api/parcels", headers=user["headers"]).json()) == 1


def test_conflict_server_wins(client, user):
    h = user["headers"]
    p = client.post("/api/parcels", json={"name": "V1", "geometry": SQUARE}, headers=h).json()
    stale = p["updated_at"]
    import time
    time.sleep(1.2)
    assert client.put(f"/api/parcels/{p['id']}", json={"name": "V2", "base_updated_at": stale}, headers=h).status_code == 200
    time.sleep(1.2)
    r = client.put(f"/api/parcels/{p['id']}", json={"name": "V3 offline", "base_updated_at": stale},
                   headers={**h, "Accept-Language": "fr"})
    assert r.status_code == 409
    assert r.json()["parcel"]["name"] == "V2"
    assert "version du serveur" in r.json()["detail"]


def test_list_includes_analysis_stats_and_geo_route(client, user, fake_model):
    from conftest import jpeg_bytes
    h = user["headers"]
    p = client.post("/api/parcels", json={"name": "P", "geometry": SQUARE}, headers=h).json()
    client.post("/api/camera/upload", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")},
                data={"parcel_id": str(p["id"]), "latitude": "3.8405", "longitude": "11.5005"}, headers=h)
    row = client.get("/api/parcels", headers=h).json()[0]
    assert row["analyses_count"] == 1 and row["last_analysis_at"]
    geo_points = client.get("/api/parcels/geo/analyses", headers=h)
    assert geo_points.status_code == 200 and len(geo_points.json()) == 1   # was 422 (route order)


def test_parcel_region_must_be_a_region_of_cameroon(client, user):
    h = user["headers"]
    assert client.post("/api/parcels", json={"name": "A", "region": "Tatooine"}, headers=h).status_code == 422
    r = client.post("/api/parcels", json={"name": "B", "region": "littoral"}, headers=h)
    assert r.status_code in (200, 201) and r.json()["region"] == "Littoral"
