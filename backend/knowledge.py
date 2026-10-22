# ============================================================
# GREEN App — Agronomic knowledge base (diseases.json, FR/EN)
#
# diseases.json entries are bilingual:
#   {"id", "category": "disease|pest|healthy", "scientificName",
#    "name": {"fr", "en"}, "description": {...}, "affectedPlants": {...},
#    "symptoms": {...}, "actions": {...}, "aliases": [...]}
# Aliases include former ids (merged duplicates) and model class codes.
#
# The field sheet ("fiche terrain") of an analysis is built here, in the
# language of the request, from the stored prediction.
# ============================================================

import json
import logging
from datetime import datetime
from typing import Optional

from config import DISEASES_DB_PATH

logger = logging.getLogger(__name__)

# Model class → knowledge-base entry. Validated against the symptoms the
# classes describe; to be confirmed by an agronomist (PROGRESS.md, T16).
CLASS_TO_DISEASE_ID = {
    "Cassava_Mosaic":     "cassava-mosaic",
    "Corn_Brown_Spots":   "leaf-spot-fungi",
    "Corn_Healthy":       "healthy",
    "Corn_Leaf_Blight":   "northern-leaf-blight",
    "Corn_Mildew":        "maize-downy-mildew",
    "Corn_Streak":        "maize-streak",
    "Corn_Stripe":        "maize-stripe",
    "Corn_Yellowing":     "maize-yellowing",
    "Tomato_Brown_Spots": "early-blight",
    "Tomato_Blight_Leaf": "mildiou",
    "Tomato_Healthy":     "healthy",
}

CLASS_NAMES_I18N = {
    "Cassava_Mosaic":     {"fr": "Mosaïque du manioc", "en": "Cassava mosaic"},
    "Corn_Brown_Spots":   {"fr": "Taches brunes du maïs", "en": "Maize brown spots"},
    "Corn_Healthy":       {"fr": "Maïs sain", "en": "Healthy maize"},
    "Corn_Leaf_Blight":   {"fr": "Brûlure des feuilles du maïs", "en": "Maize leaf blight"},
    "Corn_Mildew":        {"fr": "Mildiou du maïs", "en": "Maize mildew"},
    "Corn_Streak":        {"fr": "Striure du maïs", "en": "Maize streak"},
    "Corn_Stripe":        {"fr": "Rayure du maïs", "en": "Maize stripe"},
    "Corn_Yellowing":     {"fr": "Jaunissement du maïs", "en": "Maize yellowing"},
    "Tomato_Brown_Spots": {"fr": "Taches brunes de la tomate", "en": "Tomato brown spots"},
    "Tomato_Blight_Leaf": {"fr": "Brûlure des feuilles de la tomate", "en": "Tomato leaf blight"},
    "Tomato_Healthy":     {"fr": "Tomate saine", "en": "Healthy tomato"},
    "healthy":            {"fr": "Plante saine", "en": "Healthy plant"},
}

PLANT_NAMES_I18N = {
    "Cassava": {"fr": "Manioc", "en": "Cassava"},
    "Corn":    {"fr": "Maïs", "en": "Maize"},
    "Tomato":  {"fr": "Tomate", "en": "Tomato"},
}

LOW_CONFIDENCE_PCT = 70.0

DISCLAIMER = {
    "fr": "Prédiction de l'IA (maladie probable), pas un diagnostic. Faites-la confirmer par un agronome "
          "avant tout traitement.",
    "en": "AI prediction (probable disease), not a diagnosis. Have it confirmed by an agronomist before "
          "any treatment.",
}

_db: Optional[list] = None
_index: Optional[dict] = None


def _lang(lang: Optional[str]) -> str:
    return "fr" if lang == "fr" else "en"


def load_db() -> list:
    global _db, _index
    if _db is None:
        try:
            with open(DISEASES_DB_PATH, encoding="utf-8") as f:
                _db = json.load(f)
        except Exception as exc:
            logger.error("[Knowledge] cannot load diseases.json: %s", exc)
            _db = []
        _index = {}
        for e in _db:
            _index[e["id"]] = e
        for e in _db:  # aliases never shadow a real id
            for alias in e.get("aliases", []):
                _index.setdefault(alias, e)
    return _db


def get_entry(key: Optional[str]) -> Optional[dict]:
    load_db()
    return _index.get(key) if key else None


def localize(entry: dict, lang: str) -> dict:
    """Flat entry in one language (shape of the former diseases.json)."""
    lg = _lang(lang)
    pick = lambda f: (entry.get(f) or {}).get(lg)  # noqa: E731
    return {
        "id":             entry["id"],
        "category":       entry.get("category", "disease"),
        "scientificName": entry.get("scientificName"),
        "name":           pick("name"),
        "description":    pick("description"),
        "affectedPlants": pick("affectedPlants") or [],
        "symptoms":       pick("symptoms") or [],
        "actions":        pick("actions") or [],
        "aliases":        entry.get("aliases", []),
    }


def search(q: Optional[str] = None, plant: Optional[str] = None,
           category: Optional[str] = None, lang: str = "en") -> list:
    """Search in both languages, return entries in `lang`."""
    out = []
    for e in load_db():
        if category and e.get("category") != category:
            continue
        plants = [p.lower() for lg in ("fr", "en") for p in e["affectedPlants"][lg]]
        if plant and not any(plant.lower() in p for p in plants):
            continue
        if q:
            ql = q.lower()
            haystack = [e["name"]["fr"], e["name"]["en"], e.get("scientificName") or "", *e.get("aliases", []), *plants]
            if not any(ql in h.lower() for h in haystack):
                continue
        out.append(localize(e, lang))
    return out


# ---- Predictions --------------------------------------------
def class_code(detected_disease: Optional[str], plant_type: Optional[str]) -> str:
    """Model class code of a stored analysis ("healthy" rows keep their plant)."""
    if detected_disease and detected_disease != "healthy":
        return detected_disease
    plant = (plant_type or "").capitalize()
    return f"{plant}_Healthy" if f"{plant}_Healthy" in CLASS_NAMES_I18N else "healthy"


def class_name(code: str, lang: str) -> str:
    names = CLASS_NAMES_I18N.get((code or "").replace(" ", "_"))
    return names[_lang(lang)] if names else (code or "").replace("_", " ")


def plant_name(plant: Optional[str], lang: str) -> Optional[str]:
    names = PLANT_NAMES_I18N.get((plant or "").capitalize())
    return names[_lang(lang)] if names else plant


def build_fiche(
    *,
    detected_disease: Optional[str],
    plant_type: Optional[str],
    confidence: Optional[float],
    severity: Optional[str],
    top3: Optional[list],
    source: Optional[str],
    parcel_id: Optional[int],
    latitude: Optional[float],
    longitude: Optional[float],
    lang: str,
    generated_at: Optional[datetime] = None,
) -> dict:
    """Field sheet of one prediction, in `lang`."""
    lg = _lang(lang)
    code = class_code(detected_disease, plant_type)
    healthy = code.endswith("_Healthy") or code == "healthy"
    entry = get_entry(CLASS_TO_DISEASE_ID.get(code, code))
    info = localize(entry, lg) if entry else localize({"id": code}, lg)
    confidence_pct = round((confidence or 0) * 100, 1)
    low_confidence = confidence_pct < LOW_CONFIDENCE_PCT

    top = []
    for t in top3 or []:
        c = t.get("code") or (t.get("class") or "").replace(" ", "_")
        top.append({"code": c, "class": class_name(c, lg), "confidence": t.get("confidence")})

    winner = {
        "type":            "healthy" if healthy else "disease",
        "code":            code,
        "name":            class_name(code, lg),
        "fr_name":         class_name(code, lg),   # kept for older clients
        "reference_id":    info["id"] if entry else None,
        "reference_name":  info["name"],
        "scientific_name": None if healthy else info["scientificName"],
        "plant_type":      plant_name(plant_type, lg),
        "confidence":      confidence_pct,
        "severity":        "none" if healthy else severity,
        "symptoms":        [] if healthy else info["symptoms"],
        "recommendations": info["actions"],
        "affected_plants": info["affectedPlants"],
        "characteristics": None if healthy else info["description"],
        "low_confidence":  low_confidence,
    }
    return {
        "lang":            lg,
        "winner":          winner,
        "disease_id":      detected_disease,
        "disease_name":    winner["name"],
        "scientific_name": winner["scientific_name"],
        "plant_type":      winner["plant_type"],
        "confidence":      confidence_pct,
        "severity":        winner["severity"],
        "low_confidence":  low_confidence,
        "top3":            top,
        "symptoms":        winner["symptoms"],
        "recommendations": winner["recommendations"],
        "affected_plants": winner["affected_plants"],
        "description":     winner["characteristics"],
        "source":          source,
        "latitude":        latitude,
        "longitude":       longitude,
        "parcel_id":       parcel_id,
        "disclaimer":      DISCLAIMER[lg],
        "generated_at":    (generated_at or datetime.utcnow()).isoformat(),
    }


def fiche_for_analysis(a, lang: str) -> dict:
    """Field sheet of a stored DiseaseAnalysis row."""
    return build_fiche(
        detected_disease=a.detected_disease, plant_type=a.plant_type, confidence=a.confidence,
        severity=a.severity, top3=a.predictions, source=a.source, parcel_id=a.parcel_id,
        latitude=a.latitude, longitude=a.longitude, lang=lang, generated_at=a.created_at,
    )
