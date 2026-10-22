"""Bilingual knowledge base, class mapping and field sheets (lot 3.5 / T16)."""

import json

import knowledge
from conftest import jpeg_bytes
from inference import CLASS_NAMES


def test_every_entry_is_complete_in_both_languages():
    db = json.load(open(knowledge.DISEASES_DB_PATH, encoding="utf-8"))
    ids = [e["id"] for e in db]
    assert len(ids) == len(set(ids))
    for e in db:
        for field in ("name", "description", "affectedPlants", "symptoms", "actions"):
            assert set(e[field]) == {"fr", "en"}, (e["id"], field)
            assert e[field]["fr"] != e[field]["en"] or field == "name" or not e[field]["fr"], (e["id"], field)
        assert e["name"]["fr"] and e["description"]["fr"] and e["description"]["en"]
        assert len(e["actions"]["fr"]) == len(e["actions"]["en"]) > 0


def test_every_model_class_maps_to_an_entry():
    for code in CLASS_NAMES:
        entry = knowledge.get_entry(knowledge.CLASS_TO_DISEASE_ID[code])
        assert entry is not None, code
        assert code in knowledge.CLASS_NAMES_I18N


def test_former_duplicate_ids_still_resolve():
    for old, new in [("oidium", "powdery-mildew"), ("rouille", "rust-disease"), ("fusariose", "fusarium-wilt"),
                     ("black-sigatoka-2", "black-sigatoka"), ("cassava-mosaic-2", "cassava-mosaic"),
                     ("maize-streak-virus", "maize-streak")]:
        assert knowledge.get_entry(old)["id"] == new


def test_api_language_and_bilingual_search(client):
    fr = client.get("/api/diseases/mildiou", headers={"Accept-Language": "fr"}).json()
    en = client.get("/api/diseases/mildiou?lang=en").json()
    assert fr["name"].startswith("Mildiou") and en["name"] == "Late blight"
    assert fr["symptoms"][0] != en["symptoms"][0]
    # "tomato" finds tomato diseases even when the UI is in French
    hits = client.get("/api/diseases?q=tomato", headers={"Accept-Language": "fr"}).json()
    assert any(h["id"] == "early-blight" for h in hits) and hits[0]["name"]
    assert client.get("/api/diseases?q=maïs&lang=en").json()
    assert all(h["category"] == "pest" for h in client.get("/api/diseases?category=pest").json())


def test_fiche_follows_reader_language(client, user, fake_model):
    h = user["headers"]
    up = client.post("/api/camera/upload", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")},
                     headers={**h, "Accept-Language": "fr"}).json()
    assert up["fiche_terrain"]["lang"] == "fr"
    assert "pas un diagnostic" in up["fiche_terrain"]["disclaimer"]
    aid = up["analysis_id"]
    en = client.get(f"/api/analysis/{aid}?lang=en", headers=h).json()["fiche_terrain"]
    fr = client.get(f"/api/analysis/fiche/{aid}", headers={**h, "Accept-Language": "fr"}).json()
    assert en["winner"]["name"] == "Maize leaf blight" and fr["winner"]["name"] == "Brûlure des feuilles du maïs"
    assert en["winner"]["reference_id"] == "northern-leaf-blight"
    assert en["recommendations"] and en["recommendations"] != fr["recommendations"]


def test_healthy_prediction_has_no_alert():
    f = knowledge.build_fiche(detected_disease="healthy", plant_type="Tomato", confidence=0.95, severity="none",
                              top3=[], source="upload", parcel_id=None, latitude=None, longitude=None, lang="fr")
    assert f["winner"]["type"] == "healthy" and f["severity"] == "none"
    assert f["winner"]["name"] == "Tomate saine" and f["winner"]["symptoms"] == []
