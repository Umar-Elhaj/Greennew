"""GREEN Data: roles, consent, k-anonymity (< 5 masked), aggregates on a fixed data set (lot 6)."""

import csv
import io
from datetime import datetime, timedelta

import pytest

from conftest import register
from database import SessionLocal
from models import DiseaseAnalysis, Parcel, User

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


@pytest.fixture
def dataset(client):
    """Two farmers in Centre and Littoral; the expected figures are written next to each line."""
    a = register(client, region="Centre")
    b = register(client, region="Littoral")
    ua, ub = a["user"]["id"], b["user"]["id"]
    centre, littoral = _parcel(ua, "Centre"), _parcel(ub, "Littoral")
    _add(ua, 6, parcel_id=centre, days_ago=40)                                       # Centre: 6 streak
    _add(ua, 4, detected="healthy", parcel_id=centre, days_ago=40)                   # Centre: 4 healthy maize
    _add(ub, 7, parcel_id=littoral, days_ago=3)                                      # Littoral: 7 streak, recent
    _add(ub, 2, parcel_id=littoral, days_ago=30)                                     #           2 in the baseline
    _add(ub, 3, detected="Tomato_Blight_Leaf", plant="Tomato", parcel_id=littoral)  # 3 tomato: below 5
    _add(ua, 10, consent=False)                                                       # not consented: ignored
    _add(ua, 8, demo=True)                                                            # demo: ignored
    return {"centre": centre, "littoral": littoral}


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
    assert o["analyses"] == {"value": 22, "masked": False}            # 6+4+7+2+3; not the 10 unconsented, not the 8 demo
    assert o["farmers"] == {"value": None, "masked": True}             # 2 farmers < 5
    assert o["disease_rate"]["value"] == pytest.approx(18 / 22, abs=1e-4)
    # include_demo is refused outside DEBUG
    o2 = client.get("/api/green-data/overview?include_demo=true", headers=partner["headers"]).json()
    assert o2["analyses"]["value"] == 22


def test_plants_regions_and_masking(client, partner, dataset):
    h = partner["headers"]
    plants = {p["plant"]: p for p in client.get("/api/green-data/plants", headers=h).json()}
    assert plants["Corn"]["analyses"]["value"] == 19 and plants["Corn"]["diseased"]["value"] == 15
    assert plants["Corn"]["healthy"] == {"value": None, "masked": True}          # 4 healthy < 5
    assert plants["Tomato"]["analyses"] == {"value": None, "masked": True}
    assert plants["Tomato"]["disease_rate"] == {"value": None, "masked": True}

    regions = {r["region"]: r for r in client.get("/api/green-data/regions", headers=h).json()}
    assert regions["Centre"]["analyses"]["value"] == 10 and regions["Centre"]["disease_rate"]["value"] == 0.6
    assert regions["Littoral"]["top_disease"] == "Corn_Streak"
    assert all("latitude" not in r and "longitude" not in r for r in regions.values())

    d = client.get("/api/green-data/diseases", headers=h).json()
    assert d["top"][0] == {"disease": "Corn_Streak", "analyses": {"value": 15, "masked": False}}
    cell = next(c for c in d["matrix"]["cells"] if c["plant"] == "Tomato")
    assert cell["analyses"]["masked"] is True


def test_filters(client, partner, dataset):
    h = partner["headers"]
    assert client.get("/api/green-data/overview?region=Centre", headers=h).json()["analyses"]["value"] == 10
    assert client.get("/api/green-data/overview?plant=Tomato", headers=h).json()["analyses"]["masked"] is True
    recent = (NOW - timedelta(days=10)).date().isoformat()
    assert client.get(f"/api/green-data/overview?date_from={recent}", headers=h).json()["analyses"]["value"] == 10


def test_emerging_alert_rule(client, partner, dataset):
    a = client.get("/api/green-data/alerts", headers=partner["headers"]).json()
    assert a["rule"]["min_cases"] == 5 and "2 ×" in a["rule"]["text_fr"]
    # Littoral streak: 7 in 14 days vs 2 over the 8 previous weeks (0.5 per 14 days) -> alert
    assert [(x["region"], x["disease"], x["recent_cases"]) for x in a["alerts"]] == [("Littoral", "Corn_Streak", 7)]
    # Tomato (3 recent) is below the 5-case minimum; Centre cases are older than 14 days


def test_alert_not_raised_when_not_above_twice_the_baseline(client, partner):
    u = register(client, region="Ouest")
    pid = _parcel(u["user"]["id"], "Ouest")
    _add(u["user"]["id"], 6, parcel_id=pid, days_ago=2)      # 6 recent
    _add(u["user"]["id"], 12, parcel_id=pid, days_ago=40)    # baseline 12 / 4 = 3 per 14 days -> 6 is not > 6
    assert client.get("/api/green-data/alerts", headers=partner["headers"]).json()["alerts"] == []


def test_model_quality_and_dataset(client, partner):
    u = register(client)
    uid = u["user"]["id"]
    _add(uid, 5, verified="Corn_Streak")
    _add(uid, 1, verified="Corn_Stripe")
    _add(uid, 4, detected="healthy", image=False)
    q = client.get("/api/green-data/model-quality", headers=partner["headers"]).json()
    assert q["verified"]["value"] == 6
    assert q["agreement"]["value"] == pytest.approx(5 / 6, abs=1e-4)
    ds = {d["class"]: d for d in client.get("/api/green-data/dataset", headers=partner["headers"]).json()}
    assert ds["Corn_Streak"]["images"]["value"] == 6 and ds["Corn_Streak"]["verified"]["value"] == 5
    assert ds["Corn_Stripe"]["verified"]["masked"] is True


def test_exports_have_no_personal_data(client, partner, dataset):
    r = client.get("/api/green-data/export.csv", headers=partner["headers"])
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["region", "month", "plant", "result", "analyses"]
    assert any(row[-1] == "<5" for row in rows[1:])
    assert not any("@" in cell or cell.startswith("+237") for row in rows for cell in row)
    g = client.get("/api/green-data/export.geojson", headers=partner["headers"]).json()
    assert len(g["features"]) == 10 and g["properties"]["consent_only"] is True
    littoral = next(f for f in g["features"] if f["properties"]["region"] == "Littoral")
    assert littoral["properties"]["analyses"] == 12


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
