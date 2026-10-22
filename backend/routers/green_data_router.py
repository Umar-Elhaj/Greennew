# ============================================================
# GREEN App — GREEN Data (aggregated statistics for partners)
#
# Reserved to the roles partner and admin. Privacy rules, applied here
# and nowhere else:
#   - only analyses with consent_dataset = true are counted;
#   - demo rows (is_demo) are excluded unless include_demo=true, which is
#     only honoured when DEBUG is on;
#   - every aggregate below K_ANONYMITY (5) analyses is masked (null +
#     "masked": true) — counts, rates and matrix cells alike;
#   - no personal data and no coordinates: the finest geography is the
#     region of Cameroon (parcel region, else the user's region).
# Aggregates are computed in SQL (GROUP BY) and cached 10 minutes.
#
#   GET /api/green-data/meta | overview | plants | diseases | regions
#       | seasonality | confidence | model-quality | alerts | dataset
#       | export.csv | export.geojson
# ============================================================

import csv
import io
import json
import time
from collections import defaultdict
from dataclasses import astuple, dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import and_, case, distinct, extract, func
from sqlalchemy.orm import Session

import geo
from auth import require_roles
from config import DEBUG
from database import get_db
from knowledge import class_code
from models import DiseaseAnalysis, Parcel, User

router = APIRouter(prefix="/api/green-data", tags=["GREEN Data"])

K_ANONYMITY = 5
CACHE_TTL_S = 600
LOW_CONFIDENCE = 0.70
ALERT_RULE = {
    "window_days": 14, "baseline_weeks": 8, "factor": 2.0, "min_cases": 5,
    "text_en": "A probable disease is flagged in a region when its cases over the last 14 days exceed "
               "2 × the average per 14 days of the 8 previous weeks, with at least 5 cases.",
    "text_fr": "Une maladie probable est signalée dans une région quand ses cas des 14 derniers jours dépassent "
               "2 × la moyenne par période de 14 jours des 8 semaines précédentes, avec au moins 5 cas.",
}

guard = require_roles("partner", "admin")
_cache: dict = {}


def clear_cache() -> None:
    _cache.clear()


@dataclass(frozen=True)
class Filters:
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    region: Optional[str] = None
    plant: Optional[str] = None
    disease: Optional[str] = None
    source: Optional[str] = None
    model_version: Optional[str] = None
    include_demo: bool = False


def filters(
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    region: Optional[str] = Query(None, max_length=100), plant: Optional[str] = Query(None, max_length=100),
    disease: Optional[str] = Query(None, max_length=255), source: Optional[str] = Query(None, max_length=50),
    model_version: Optional[str] = Query(None, max_length=100), include_demo: bool = False,
) -> Filters:
    return Filters(date_from, date_to, region, plant, disease, source, model_version, include_demo and DEBUG)


# ---- query helpers ------------------------------------------
A = DiseaseAnalysis
REGION = func.coalesce(Parcel.region, User.region)
DISEASED = case((and_(A.detected_disease.isnot(None), A.detected_disease != "healthy"), 1), else_=0)
MONTH = extract("year", A.created_at) * 100 + extract("month", A.created_at)


def base_query(db: Session, f: Filters, *cols):
    q = (db.query(*cols)
           .select_from(A)
           .join(User, User.id == A.user_id)
           .outerjoin(Parcel, Parcel.id == A.parcel_id)
           .filter(A.consent_dataset == True))  # noqa: E712
    if not f.include_demo:
        q = q.filter(A.is_demo == False)  # noqa: E712
    if f.date_from:
        q = q.filter(A.created_at >= datetime.combine(f.date_from, datetime.min.time()))
    if f.date_to:
        q = q.filter(A.created_at < datetime.combine(f.date_to, datetime.min.time()) + timedelta(days=1))
    if f.region:
        q = q.filter(REGION == f.region)
    if f.plant:
        q = q.filter(A.plant_type == f.plant)
    if f.disease:
        q = q.filter(A.detected_disease == f.disease)
    if f.source:
        q = q.filter(A.source == f.source)
    if f.model_version:
        q = q.filter(A.model_version == f.model_version)
    return q


def masked(n: Optional[int]) -> dict:
    n = int(n or 0)
    return {"value": n, "masked": False} if n >= K_ANONYMITY else {"value": None, "masked": True}


def rate(part: int, total: int) -> dict:
    if total < K_ANONYMITY:
        return {"value": None, "masked": True}
    return {"value": round(part / total, 4), "masked": False}


def cached(name: str):
    """Cache the endpoint result for CACHE_TTL_S, per filter set."""
    def deco(fn):
        def wrapper(f: Filters, db: Session):
            key = (name, astuple(f))
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < CACHE_TTL_S:
                return hit[1]
            value = fn(f, db)
            _cache[key] = (time.time(), value)
            return value
        return wrapper
    return deco


def month_key(v) -> str:
    v = int(v)
    return f"{v // 100:04d}-{v % 100:02d}"


# ---- computations (cached) ----------------------------------
@cached("meta")
def _meta(f: Filters, db: Session) -> dict:
    n = base_query(db, f, func.count(A.id)).scalar() or 0
    first, last = base_query(db, f, func.min(A.created_at), func.max(A.created_at)).one()
    distinct_values = lambda col: sorted(v for (v,) in base_query(db, f, distinct(col)).all() if v)  # noqa: E731
    return {
        "n": n, "k_anonymity": K_ANONYMITY,
        "period": {"from": first.date().isoformat() if first else None, "to": last.date().isoformat() if last else None},
        "regions": [r["properties"]["region"] for r in _regions_geojson()["features"]],
        "plants": distinct_values(A.plant_type),
        "diseases": [d for d in distinct_values(A.detected_disease) if d != "healthy"],
        "sources": distinct_values(A.source),
        "model_versions": distinct_values(A.model_version),
        "demo_available": DEBUG,
        "include_demo": f.include_demo,
    }


@cached("overview")
def _overview(f: Filters, db: Session) -> dict:
    n, farmers, diseased = base_query(db, f, func.count(A.id), func.count(distinct(A.user_id)),
                                      func.sum(DISEASED)).one()
    parcel_rows = base_query(db, f, distinct(Parcel.id), Parcel.area_ha).filter(Parcel.id.isnot(None)).all()
    area = sum(a or 0 for _, a in parcel_rows)
    series = (base_query(db, f, MONTH.label("m"), func.count(A.id), func.count(distinct(A.user_id)), func.sum(DISEASED))
                .group_by(MONTH).order_by(MONTH).all())
    return {
        "analyses": masked(n), "farmers": masked(farmers), "parcels": masked(len(parcel_rows)),
        "area_ha": {"value": round(area, 2), "masked": False} if len(parcel_rows) >= K_ANONYMITY
                   else {"value": None, "masked": True},
        "disease_rate": rate(diseased or 0, n or 0),
        "series": [{"month": month_key(m), "analyses": masked(c), "farmers": masked(u), "disease_rate": rate(d or 0, c)}
                   for m, c, u, d in series],
    }


@cached("plants")
def _plants(f: Filters, db: Session) -> list:
    rows = (base_query(db, f, A.plant_type, func.count(A.id), func.sum(DISEASED))
              .group_by(A.plant_type).order_by(func.count(A.id).desc()).all())
    return [{"plant": p or "unknown", "analyses": masked(n), "diseased": masked(d), "healthy": masked(n - (d or 0)),
             "disease_rate": rate(d or 0, n)} for p, n, d in rows]


@cached("diseases")
def _diseases(f: Filters, db: Session) -> dict:
    rows = (base_query(db, f, A.plant_type, A.detected_disease, func.count(A.id))
              .group_by(A.plant_type, A.detected_disease).all())
    totals: dict = defaultdict(int)
    cells = []
    for plant, code, n in rows:
        code = code or "healthy"
        totals[code] += n
        cells.append({"plant": plant or "unknown", "disease": code, "analyses": masked(n)})
    top = sorted(((c, n) for c, n in totals.items() if c != "healthy"), key=lambda x: -x[1])
    return {
        "top": [{"disease": c, "analyses": masked(n)} for c, n in top],
        "matrix": {"plants": sorted({c["plant"] for c in cells}), "diseases": sorted(totals), "cells": cells},
    }


@cached("regions")
def _regions(f: Filters, db: Session) -> list:
    rows = (base_query(db, f, REGION.label("r"), func.count(A.id), func.sum(DISEASED))
              .group_by(REGION).all())
    top_rows = (base_query(db, f, REGION.label("r"), A.detected_disease, func.count(A.id))
                  .filter(DISEASED == 1).group_by(REGION, A.detected_disease).all())
    best: dict = {}
    for r, code, n in top_rows:
        if n >= K_ANONYMITY and n > best.get(r, (None, 0))[1]:
            best[r] = (code, n)
    out = []
    for r, n, d in sorted(rows, key=lambda x: -x[1]):
        out.append({"region": r or "unknown", "analyses": masked(n), "diseased": masked(d),
                    "disease_rate": rate(d or 0, n),
                    "top_disease": best.get(r, (None, 0))[0] if n >= K_ANONYMITY else None})
    return out


@cached("seasonality")
def _seasonality(f: Filters, db: Session) -> list:
    mon = extract("month", A.created_at)
    rows = (base_query(db, f, mon.label("mo"), A.detected_disease, func.count(A.id))
              .filter(DISEASED == 1).group_by(mon, A.detected_disease).all())
    return [{"month": int(m), "disease": code, "analyses": masked(n)} for m, code, n in rows]


@cached("confidence")
def _confidence(f: Filters, db: Session) -> dict:
    n = base_query(db, f, func.count(A.id)).scalar() or 0
    sev = base_query(db, f, func.coalesce(A.severity, "none"), func.count(A.id)).group_by(
        func.coalesce(A.severity, "none")).all()
    bins = case(*[(A.confidence < (i + 1) / 10, i) for i in range(9)], else_=9)
    hist = base_query(db, f, bins.label("b"), func.count(A.id)).filter(A.confidence.isnot(None)).group_by(bins).all()
    low = base_query(db, f, func.count(A.id)).filter(A.confidence < LOW_CONFIDENCE).scalar() or 0
    by_bin = {int(b): c for b, c in hist}
    return {
        "alert_levels": [{"level": lvl, "analyses": masked(c)} for lvl, c in sev],
        "histogram": [{"from": i / 10, "to": (i + 1) / 10, "analyses": masked(by_bin.get(i, 0))} for i in range(10)],
        "low_confidence_threshold": LOW_CONFIDENCE,
        "low_confidence_rate": rate(low, n),
    }


@cached("model_quality")
def _model_quality(f: Filters, db: Session) -> dict:
    rows = (base_query(db, f, A.detected_disease, A.plant_type, A.verified_label, A.model_version)
              .filter(A.verified_label.isnot(None)).all())
    confusion: dict = defaultdict(int)
    by_version: dict = defaultdict(lambda: [0, 0])
    agree = 0
    for detected, plant, verified, version in rows:
        predicted = class_code(detected, plant)
        ok = predicted == verified
        agree += ok
        confusion[(predicted, verified)] += 1
        by_version[version or "unknown"][0] += 1
        by_version[version or "unknown"][1] += ok
    labels = sorted({p for p, _ in confusion} | {v for _, v in confusion})
    return {
        "verified": masked(len(rows)),
        "agreement": rate(agree, len(rows)),
        "by_version": [{"model_version": v, "verified": masked(n), "agreement": rate(ok, n)}
                       for v, (n, ok) in sorted(by_version.items())],
        "confusion": {"labels": labels,
                      "cells": [{"predicted": p, "verified": v, "analyses": masked(n)} for (p, v), n in confusion.items()]},
    }


@cached("alerts")
def _alerts(f: Filters, db: Session) -> dict:
    """Emerging alerts, always computed up to today (date filters do not apply)."""
    window = ALERT_RULE["window_days"]
    span = window + ALERT_RULE["baseline_weeks"] * 7
    today = datetime.utcnow()
    since = today - timedelta(days=span)
    f_now = Filters(None, None, f.region, f.plant, f.disease, f.source, f.model_version, f.include_demo)
    recent_from = today - timedelta(days=window)
    is_recent = case((A.created_at >= recent_from, 1), else_=0)
    rows = (base_query(db, f_now, REGION.label("r"), A.detected_disease, func.sum(is_recent), func.count(A.id))
              .filter(A.created_at >= since, DISEASED == 1)
              .group_by(REGION, A.detected_disease).all())
    periods = ALERT_RULE["baseline_weeks"] * 7 / window
    out = []
    for region, code, recent, total in rows:
        recent = int(recent or 0)
        baseline = (int(total) - recent) / periods
        if recent >= ALERT_RULE["min_cases"] and recent > ALERT_RULE["factor"] * baseline:
            out.append({"region": region or "unknown", "disease": code, "recent_cases": recent,
                        "baseline_per_period": round(baseline, 2),
                        "ratio": round(recent / baseline, 2) if baseline else None})
    out.sort(key=lambda a: -a["recent_cases"])
    return {"rule": {k: v for k, v in ALERT_RULE.items()}, "as_of": today.date().isoformat(), "alerts": out}


@cached("dataset")
def _dataset(f: Filters, db: Session) -> list:
    rows = (base_query(db, f, A.detected_disease, A.plant_type, A.verified_label)
              .filter(A.image_path.isnot(None)).all())
    images: dict = defaultdict(int)
    verified: dict = defaultdict(int)
    for detected, plant, label in rows:
        images[class_code(detected, plant)] += 1
        if label:
            verified[label] += 1
    codes = sorted(set(images) | set(verified))
    return [{"class": c, "images": masked(images[c]), "verified": masked(verified[c])} for c in codes]


_regions_cache = None


def _regions_geojson() -> dict:
    global _regions_cache
    if _regions_cache is None:
        with open(geo.REGIONS_PATH, encoding="utf-8") as fh:
            _regions_cache = json.load(fh)
    return _regions_cache


# ---- endpoints ----------------------------------------------
def _endpoint(path: str, compute, summary: str):
    @router.get(path, summary=summary)
    def handler(f: Filters = Depends(filters), db: Session = Depends(get_db), _=Depends(guard)):
        return compute(f, db)
    handler.__name__ = f"green_data_{path.strip('/').replace('-', '_')}"
    return handler


_endpoint("/meta", _meta, "Filter options, period covered, number of analyses")
_endpoint("/overview", _overview, "Volume: analyses, farmers, parcels, area, monthly series")
_endpoint("/plants", _plants, "Analyses and disease rate per plant")
_endpoint("/diseases", _diseases, "Most frequent probable diseases and plant x disease matrix")
_endpoint("/regions", _regions, "Per region of Cameroon (no coordinates)")
_endpoint("/seasonality", _seasonality, "Month x probable disease")
_endpoint("/confidence", _confidence, "Alert levels, confidence histogram, low-confidence rate")
_endpoint("/model-quality", _model_quality, "Agreement with agronomist-verified labels")
_endpoint("/alerts", _alerts, "Emerging alerts (rule included)")
_endpoint("/dataset", _dataset, "Consented images and verified labels per class")


@router.get("/export.csv", summary="Aggregated CSV (region x month x plant x disease)")
def export_csv(f: Filters = Depends(filters), db: Session = Depends(get_db), _=Depends(guard)):
    rows = (base_query(db, f, REGION.label("r"), MONTH.label("m"), A.plant_type, A.detected_disease, func.count(A.id))
              .group_by(REGION, MONTH, A.plant_type, A.detected_disease)
              .order_by(REGION, MONTH).all())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["region", "month", "plant", "result", "analyses"])
    for r, m, plant, code, n in rows:
        w.writerow([r or "unknown", month_key(m), plant or "unknown", code or "healthy",
                    n if n >= K_ANONYMITY else f"<{K_ANONYMITY}"])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="green-data.csv"'})


@router.get("/export.geojson", summary="Aggregates per region as GeoJSON")
def export_geojson(f: Filters = Depends(filters), db: Session = Depends(get_db), _=Depends(guard)):
    stats = {r["region"]: r for r in _regions(f, db)}
    meta = _meta(f, db)
    features = []
    for feat in _regions_geojson()["features"]:
        name = feat["properties"]["region"]
        s = stats.get(name)
        features.append({"type": "Feature", "geometry": feat["geometry"], "properties": {
            "region": name,
            "analyses": s["analyses"]["value"] if s else 0,
            "analyses_masked": s["analyses"]["masked"] if s else False,
            "disease_rate": s["disease_rate"]["value"] if s else None,
            "top_disease": s["top_disease"] if s else None,
        }})
    return Response(json.dumps({
        "type": "FeatureCollection",
        "properties": {"period": meta["period"], "n": meta["n"], "k_anonymity": K_ANONYMITY,
                       "consent_only": True, "note": "AI predictions (probable diseases), not diagnoses.",
                       "attribution": _regions_geojson().get("attribution")},
        "features": features,
    }, ensure_ascii=False), media_type="application/geo+json",
        headers={"Content-Disposition": 'attachment; filename="green-data-regions.geojson"'})
