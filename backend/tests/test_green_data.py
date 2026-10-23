"""GREEN Data: roles, consent, disclosure control (>= 5 analyses from >= 5 farmers, complementary
cells masked), aggregates on a fixed data set (lot 6, review 8.3)."""

import csv
import io
from datetime import datetime, timedelta

import pytest

from conftest import register
from database import SessionLocal
from models import DiseaseAnalysis, Parcel, User
from routers.green_data_router import cell, split_table, suppress

NOW = datetime.utcnow()


def _role(uid, role):
    db = SessionLocal()
    db.get(User, uid).role = role
    db.commit()
    db.close()


@pytest.fixture
def partner(client):
    p = register(client)
    _role(p["user"]["id"], "partner")
    return p


def _parcel(uid, region):
    db = SessionLocal()
    p = Parcel(user_id=uid, name=f"P-{region}", region=region, area_ha=2.0)
    db.add(p)
    db.commit()
    pid = p.id
    db.close()
    return pid


def _add(uid, n, *, detected="Corn_Streak", plant="Corn", parcel_id=None, consent=True, demo=False,
         days_ago=1, severity=None, confidence=0.9, verified=None, image=True, version="efficientnet-v1"):
    db = SessionLocal()
    for i in range(n):
        db.add(DiseaseAnalysis(
            user_id=uid, parcel_id=parcel_id, detected_disease=detected, plant_type=plant,
            consent_dataset=consent, is_demo=demo, created_at=NOW - timedelta(days=days_ago, minutes=i),
            severity=severity or ("none" if detected == "healthy" else "high"), confidence=confidence,
            verified_label=verified, image_path=f"2026/10/{uid:016x}{i:016x}.jpg" if image else None,
            model_version=version, source="camera"))
    db.commit()
    db.close()


def _farmers(client, k, region=None):
    """k farmers who agreed to share their analyses."""
    return [register(client, region=region, dataset_consent=True)["user"]["id"] for _ in range(k)]


def _set_user(uid, **fields):
    db = SessionLocal()
    u = db.get(User, uid)
    for k, v in fields.items():
        setattr(u, k, v)
    db.commit()
    db.close()


@pytest.fixture
def dataset(client):
    """5 farmers in Centre, 5 in Littoral; the expected figures are written next to each line."""
    centre, littoral = _farmers(client, 5, "Centre"), _farmers(client, 5, "Littoral")
    for uid in centre:
        pid = _parcel(uid, "Centre")
        _add(uid, 2, parcel_id=pid, days_ago=40)                                      # 10 streak (5 farmers)
        _add(uid, 1, detected="healthy", parcel_id=pid, days_ago=40)                  # 5 healthy maize
        _add(uid, 1, detected="healthy", plant="Cassava", parcel_id=pid, days_ago=40)  # 5 healthy cassava
    for uid in littoral:
        _add(uid, 2, parcel_id=_parcel(uid, "Littoral"), days_ago=3)                  # 10 streak, recent
    first = littoral[0]
    _add(first, 2, days_ago=30)                                       # 2 in the baseline (user region Littoral)
    _add(first, 3, detected="Tomato_Blight_Leaf", plant="Tomato")    # 3 tomato from 1 farmer: hidden
    _add(centre[0], 10, consent=False)                                # analysis not consented: ignored
    _add(centre[0], 8, demo=True)                                     # demo: ignored
    gone = _farmers(client, 1, "Centre")[0]
    _add(gone, 5)
    _set_user(gone, dataset_consent=False)                            # consent withdrawn: ignored
    return {"centre": centre, "littoral": littoral}


# ---- disclosure control, unit level ---------------------------------
def test_primary_suppression_needs_5_analyses_and_5_farmers():
    a, b, c, zero = suppress([cell(10, 5), cell(10, 4), cell(4, 4), cell(0, 0)])
    assert not a["hidden"] and b["hidden"] and c["hidden"] and not zero["hidden"]


def test_a_lone_hidden_cell_takes_the_smallest_visible_one_with_it():
    big, small, mid = suppress([cell(30, 9, k="a"), cell(3, 3, k="b"), cell(8, 6, k="c")], ("k",))
    assert small["hidden"] and mid["hidden"] and not big["hidden"]   # 3 = total - 30 - 8 otherwise
    # zero cells are public and never used as a cover
    one, zero = suppress([cell(3, 3, k="a"), cell(0, 0, k="b")], ("k",))
    assert one["hidden"] and not zero["hidden"]


def test_no_table_line_keeps_exactly_one_hidden_cell():
    cells = suppress([cell(n, u, r=r, c=c) for r, c, n, u in [
        ("x", 1, 20, 9), ("x", 2, 2, 2), ("x", 3, 9, 5),
        ("y", 1, 7, 5), ("y", 2, 12, 6), ("y", 3, 30, 8)]], ("r", "c"))
    for key in ("r", "c"):
        for v in {c[key] for c in cells}:
            assert sum(c["hidden"] for c in cells if c[key] == v) != 1


def test_rates_are_masked_with_either_side():
    t = split_table([("a", 10, 6, 8, 6, 1), ("b", 20, 9, 10, 6, 5), ("c", 10, 5, 10, 5, 0)], "g")
    assert t["a"]["rest"]["hidden"] and t["a"]["part"]["hidden"] and t["a"]["rate"]["masked"]   # 2 healthy, 1 farmer
    assert t["c"]["rate"] == {"value": 1.0, "masked": False}                                   # 0 on one side is public
    # the "part" column now has a lone hidden cell (a) -> b's part is hidden as its cover
    assert t["b"]["part"]["hidden"] and t["b"]["rate"]["masked"]


# ---- endpoints -----------------------------------------------------------
def test_access_by_role(client, user, partner):
    assert client.get("/api/green-data/overview").status_code == 401
    assert client.get("/api/green-data/overview", headers=user["headers"]).status_code == 403
    agro = register(client)
    _role(agro["user"]["id"], "agronomist")
    assert client.get("/api/green-data/overview", headers=agro["headers"]).status_code == 403
    assert client.get("/api/green-data/overview", headers=partner["headers"]).status_code == 200
    admin = register(client)
    _role(admin["user"]["id"], "admin")
    for path in ("meta", "overview", "plants", "diseases", "regions", "seasonality", "confidence",
                 "model-quality", "alerts", "dataset", "export.csv", "export.geojson"):
        assert client.get(f"/api/green-data/{path}", headers=admin["headers"]).status_code == 200, path
    r = client.get("/api/green-data/overview", headers={**user["headers"], "Accept-Language": "fr"})
    assert r.json()["detail"] == "Vous n'avez pas accès à cette page."


def test_consent_demo_and_volume(client, partner, dataset):
    o = client.get("/api/green-data/overview", headers=partner["headers"]).json()
    assert o["analyses"] == {"value": 35, "masked": False}   # not the unconsented, demo or withdrawn ones
    assert o["farmers"] == {"value": 10, "masked": False}
    assert o["disease_rate"]["value"] == pytest.approx(25 / 35, abs=1e-4)
    # include_demo is refused outside DEBUG
    o2 = client.get("/api/green-data/overview?include_demo=true", headers=partner["headers"]).json()
    assert o2["analyses"]["value"] == 35


def test_meta_publishes_no_small_count(client, partner, dataset):
    m = client.get("/api/green-data/meta", headers=partner["headers"]).json()
    assert m["n"] == {"value": 35, "masked": False}
    assert len(m["period"]["from"]) == 7 and len(m["period"]["to"]) == 7          # YYYY-MM
    assert m["plants"] == ["Cassava", "Corn"]                                      # Tomato: 1 farmer
    assert m["diseases"] == ["Corn_Streak"]
    small = client.get("/api/green-data/meta?plant=Tomato", headers=partner["headers"]).json()
    assert small["n"] == {"value": None, "masked": True} and small["period"] == {"from": None, "to": None}


def test_plants_regions_and_masking(client, partner, dataset):
    h = partner["headers"]
    plants = {p["plant"]: p for p in client.get("/api/green-data/plants", headers=h).json()}
    assert plants["Corn"]["analyses"] == {"value": 27, "masked": False}
    assert plants["Tomato"]["analyses"]["masked"] and plants["Tomato"]["disease_rate"]["masked"]
    # 35 - 27 would give Tomato's 3 if Cassava's 5 were shown
    assert plants["Cassava"]["analyses"]["masked"]

    regions = {r["region"]: r for r in client.get("/api/green-data/regions", headers=h).json()}
    assert regions["Centre"]["analyses"]["value"] == 20 and regions["Centre"]["disease_rate"]["value"] == 0.5
    assert regions["Littoral"]["top_disease"] == "Corn_Streak"
    assert all("latitude" not in r and "longitude" not in r for r in regions.values())

    d = client.get("/api/green-data/diseases", headers=h).json()
    assert d["top"][0] == {"disease": "Corn_Streak", "analyses": {"value": 22, "masked": False}}
    tomato = next(c for c in d["matrix"]["cells"] if c["plant"] == "Tomato")
    assert tomato["analyses"]["masked"] is True


def test_free_text_regions_are_published_as_unknown(client, partner):
    for uid in _farmers(client, 5):
        _add(uid, 1)
        _set_user(uid, region="Quartier Bastos, chez M. Ndongo")   # legacy value, bypassing validation
    regions = [r["region"] for r in client.get("/api/green-data/regions", headers=partner["headers"]).json()]
    assert regions == ["unknown"]
    csv_text = client.get("/api/green-data/export.csv", headers=partner["headers"]).text
    assert "Bastos" not in csv_text and "unknown" in csv_text


def test_filters(client, partner, dataset):
    h = partner["headers"]
    assert client.get("/api/green-data/overview?region=Centre", headers=h).json()["analyses"]["value"] == 20
    assert client.get("/api/green-data/overview?region=centre", headers=h).json()["analyses"]["value"] == 20
    assert client.get("/api/green-data/overview?region=Mars", headers=h).status_code == 422
    assert client.get("/api/green-data/overview?plant=Tomato", headers=h).json()["analyses"]["masked"] is True
    recent = (NOW - timedelta(days=10)).date().isoformat()
    assert client.get(f"/api/green-data/overview?date_from={recent}", headers=h).json()["analyses"]["value"] == 13


def test_emerging_alert_rule(client, partner, dataset):
    a = client.get("/api/green-data/alerts", headers=partner["headers"]).json()
    assert a["rule"]["min_cases"] == 5 and "2 ×" in a["rule"]["text_fr"]
    # Littoral streak: 10 in 14 days (5 farmers) vs 2 over the 8 previous weeks -> alert;
    # the baseline (2 cases) is masked. Tomato (3 recent) is below the minimum.
    assert [(x["region"], x["disease"], x["recent_cases"], x["baseline_per_period"], x["baseline_masked"])
            for x in a["alerts"]] == [("Littoral", "Corn_Streak", 10, None, True)]


def test_alert_needs_5_farmers(client, partner):
    uid = _farmers(client, 1, "Ouest")[0]
    _add(uid, 12, parcel_id=_parcel(uid, "Ouest"), days_ago=2)
    assert client.get("/api/green-data/alerts", headers=partner["headers"]).json()["alerts"] == []


def test_alert_not_raised_when_not_above_twice_the_baseline(client, partner):
    for uid in _farmers(client, 5, "Ouest"):
        pid = _parcel(uid, "Ouest")
        _add(uid, 2, parcel_id=pid, days_ago=2)      # 10 recent
        _add(uid, 4, parcel_id=pid, days_ago=40)     # baseline 20 / 4 = 5 per 14 days -> 10 is not > 10
    assert client.get("/api/green-data/alerts", headers=partner["headers"]).json()["alerts"] == []


def test_model_quality_and_dataset(client, partner):
    for uid in _farmers(client, 5):
        _add(uid, 2, verified="Corn_Streak")
        _add(uid, 1, verified="Corn_Stripe")
        _add(uid, 1, detected="healthy", image=False)
    q = client.get("/api/green-data/model-quality", headers=partner["headers"]).json()
    assert q["verified"]["value"] == 15
    assert q["agreement"]["value"] == pytest.approx(10 / 15, abs=1e-4)
    ds = {d["class"]: d for d in client.get("/api/green-data/dataset", headers=partner["headers"]).json()}
    assert ds["Corn_Streak"]["images"]["value"] == 15 and ds["Corn_Streak"]["verified"]["value"] == 10
    assert ds["Corn_Stripe"]["verified"]["value"] == 5


def test_exports_have_no_personal_data(client, partner, dataset):
    r = client.get("/api/green-data/export.csv", headers=partner["headers"])
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["region", "month", "plant", "result", "analyses"]
    assert any(row[-1] == "masked" for row in rows[1:])
    assert all(row[-1] == "masked" or int(row[-1]) >= 5 for row in rows[1:])
    assert not any("@" in cell or cell.startswith("+237") for row in rows for cell in row)
    g = client.get("/api/green-data/export.geojson", headers=partner["headers"]).json()
    assert len(g["features"]) == 10 and g["properties"]["consent_only"] is True
    assert g["properties"]["n"] == 35 and len(g["properties"]["period"]["from"]) == 7
    littoral = next(f for f in g["features"] if f["properties"]["region"] == "Littoral")
    assert littoral["properties"]["analyses"] == 15


def test_verify_endpoint_roles(client, user, fake_model):
    from conftest import jpeg_bytes
    aid = client.post("/api/camera/upload", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")},
                      headers=user["headers"]).json()["analysis_id"]
    assert client.post(f"/api/analysis/{aid}/verify", json={"label": "Corn_Streak"}, headers=user["headers"]).status_code == 403
    agro = register(client)
    _role(agro["user"]["id"], "agronomist")
    assert client.post(f"/api/analysis/{aid}/verify", json={"label": "Nope"}, headers=agro["headers"]).status_code == 422
    r = client.post(f"/api/analysis/{aid}/verify", json={"label": "Corn_Streak"}, headers=agro["headers"])
    assert r.status_code == 200 and r.json()["verified_label"] == "Corn_Streak"
