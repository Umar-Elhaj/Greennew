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


@pytest.mark.xfail(strict=True, reason="Lot 5.3 — validation géométrique serveur pas encore implémentée")
@pytest.mark.parametrize("geometry", [
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},   # bow-tie
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]},                   # < 3 points
    {"type": "Polygon", "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 0]]]},   # lng out of range
    {"type": "Point", "coordinates": [11.5, 3.8]},
])
def test_invalid_geometry_is_rejected(client, user, geometry):
    r = client.post("/api/parcels", json={"name": "bad", "geometry": geometry}, headers=user["headers"])
    assert r.status_code == 422
