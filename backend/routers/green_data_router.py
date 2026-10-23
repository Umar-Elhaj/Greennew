# ============================================================
# GREEN App — GREEN Data (aggregated statistics for partners)
#
# Reserved to the roles partner and admin. Privacy rules, applied here
# and nowhere else:
#   - only analyses with consent_dataset = true, from active accounts whose
#     consent is still given, are counted;
#   - demo rows (is_demo) are excluded unless include_demo=true, which is
#     only honoured when DEBUG is on;
#   - a count is published only if it covers >= K_ANONYMITY (5) analyses
#     from >= 5 distinct farmers; otherwise it is masked (null + "masked":
#     true). Complementary cells are masked too (see suppress()), and a rate
#     is masked when its total or either of its two sides is;
#   - no personal data and no coordinates: the finest geography is one of
#     the 10 regions of Cameroon (parcel region, else the user's region;
#     any other text is "unknown"); the period is given by month.
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

from fastapi import APIRouter, Depends, HTTPException, Query
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
CACHE_MAX = 512          # filter sets kept; the cache is emptied beyond
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
    try:
        region = geo.canonical_region(region)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return Filters(date_from, date_to, region, plant, disease, source, model_version, include_demo and DEBUG)


# ---- query helpers ------------------------------------------
A = DiseaseAnalysis
# Only the 10 official regions are published; anything else (legacy free text) is "unknown".
REGION_RAW = func.coalesce(Parcel.region, User.region)
REGION = case((REGION_RAW.in_(geo.REGION_NAMES), REGION_RAW), else_=None)
IS_DISEASED = and_(A.detected_disease.isnot(None), A.detected_disease != "healthy")
DISEASED = case((IS_DISEASED, 1), else_=0)
MONTH = extract("year", A.created_at) * 100 + extract("month", A.created_at)
N = func.count(A.id)
U = func.count(distinct(A.user_id))
N_SICK = func.sum(DISEASED)
U_SICK = func.count(distinct(case((IS_DISEASED, A.user_id), else_=None)))
U_OK = func.count(distinct(case((IS_DISEASED, None), else_=A.user_id)))


def base_query(db: Session, f: Filters, *cols):
    q = (db.query(*cols)
           .select_from(A)
           .join(User, User.id == A.user_id)
           .outerjoin(Parcel, Parcel.id == A.parcel_id)
           # consent on the analysis AND still given by an active account (withdrawal applies to the past)
           .filter(A.consent_dataset == True, User.dataset_consent == True,  # noqa: E712
                   User.is_active == True))  # noqa: E712
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


# ---- disclosure control ---------------------------------------
# A count is published when it covers >= K analyses from >= K distinct
# farmers (primary suppression). A lone hidden cell in any row or column of
# a table would be the difference between a published total and the visible
# cells, so the smallest visible cell of that line is hidden too (secondary
# suppression), until no line has exactly one hidden cell. Zero cells are
# public (they single nobody out) and never used to cover another cell.
def cell(n, u, **keys) -> dict:
    return {**keys, "n": int(n or 0), "u": int(u or 0), "hidden": False}


def suppress(cells: list, dims: tuple = (), keep: bool = False) -> list:
    """Mark c["hidden"]; keep=True also keeps the cells already hidden."""
    for c in cells:
        primary = 0 < c["n"] and (c["n"] < K_ANONYMITY or c["u"] < K_ANONYMITY)
        c["hidden"] = primary or (keep and c["hidden"])
    lines = []
    for d in dims or (None,):
        groups: dict = defaultdict(list)
        for c in cells:
            groups[tuple(c[x] for x in dims if x != d)].append(c)
        lines += groups.values()
    changed = True
    while changed:
        changed = False
        for line in lines:
            if sum(c["hidden"] for c in line) == 1:
                visible = [c for c in line if not c["hidden"] and c["n"] > 0]
                if visible:
                    min(visible, key=lambda c: c["n"])["hidden"] = True
                    changed = True
    return cells


def shown(c: Optional[dict]) -> dict:
    if c is None:
        return {"value": 0, "masked": False}
    return {"value": None, "masked": True} if c["hidden"] else {"value": c["n"], "masked": False}


def masked(n, u) -> dict:
    """A single published count (no table around it)."""
    return shown(suppress([cell(n, u)])[0])


def rate(part: Optional[dict], rest: Optional[dict], total: dict) -> dict:
    """part / total, published only when the total and both sides are."""
    if total["hidden"] or total["n"] == 0 or any(c and c["hidden"] for c in (part, rest)):
        return {"value": None, "masked": True}
    return {"value": round((part["n"] if part else 0) / total["n"], 4), "masked": False}


def split_table(rows: list, key: str) -> dict:
    """rows: (key, n, u, n_part, u_part, u_rest). Totals per key, the two
    sides of each total (part / rest) and the part rate, all suppressed
    together: a hidden total hides its sides, a hidden side hides the other."""
    totals = suppress([cell(n, u, **{key: k}) for k, n, u, *_ in rows], (key,))
    sides = []
    for k, n, _u, n_part, u_part, u_rest in rows:
        n_part = int(n_part or 0)
        sides.append(cell(n_part, u_part, **{key: k, "side": "part"}))
        sides.append(cell(int(n) - n_part, u_rest, **{key: k, "side": "rest"}))
    suppress(sides, (key, "side"))
    for i, t in enumerate(totals):
        if t["hidden"]:
            for c in sides[2 * i:2 * i + 2]:
                c["hidden"] = c["n"] > 0
    suppress(sides, (key, "side"), keep=True)
    out = {}
    for i, t in enumerate(totals):
        part, rest = sides[2 * i], sides[2 * i + 1]
        out[t[key]] = {"total": t, "part": part, "rest": rest, "rate": rate(part, rest, t)}
    return out


def cached(name: str):
    """Cache the endpoint result for CACHE_TTL_S, per filter set."""
    def deco(fn):
        def wrapper(f: Filters, db: Session):
            key = (name, astuple(f))
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < CACHE_TTL_S:
                return hit[1]
            value = fn(f, db)
            if len(_cache) > CACHE_MAX:
                _cache.clear()
            _cache[key] = (time.time(), value)
            return value
        return wrapper
    return deco


def month_key(v) -> str:
    v = int(v)
    return f"{v // 100:04d}-{v % 100:02d}"


# ---- computations (cached) ----------------------------------
def _public_values(db: Session, f: Filters, col) -> list:
    """Filter options: only values seen in >= K analyses from >= K farmers."""
    rows = base_query(db, f, col, N, U).group_by(col).all()
    return sorted(v for v, n, u in rows if v and n >= K_ANONYMITY and u >= K_ANONYMITY)


@cached("meta")
def _meta(f: Filters, db: Session) -> dict:
    n, u, first, last = base_query(db, f, N, U, func.min(A.created_at), func.max(A.created_at)).one()
    total = masked(n, u)
    # the period is given by month, and only when the total itself is published
    period = ({"from": first.strftime("%Y-%m"), "to": last.strftime("%Y-%m")}
              if not total["masked"] and first else {"from": None, "to": None})
    return {
        "n": total, "k_anonymity": K_ANONYMITY, "period": period,
        "regions": list(geo.REGION_NAMES),
        "plants": _public_values(db, f, A.plant_type),
        "diseases": [d for d in _public_values(db, f, A.detected_disease) if d != "healthy"],
        "sources": _public_values(db, f, A.source),
        "model_versions": _public_values(db, f, A.model_version),
        "demo_available": DEBUG,
        "include_demo": f.include_demo,
    }


@cached("overview")
def _overview(f: Filters, db: Session) -> dict:
    total = split_table([("all", *base_query(db, f, N, U, N_SICK, U_SICK, U_OK).one())], "k")["all"]
    t = total["total"]
    parcels, parcel_users = base_query(db, f, func.count(distinct(Parcel.id)), func.count(distinct(Parcel.user_id))).one()
    area_rows = base_query(db, f, distinct(Parcel.id), Parcel.area_ha).filter(Parcel.id.isnot(None)).all()
    parcels_c = masked(parcels, parcel_users)
    series_rows = (base_query(db, f, MONTH.label("m"), N, U, N_SICK, U_SICK, U_OK)
                     .group_by(MONTH).order_by(MONTH).all())
    series = split_table(series_rows, "month")
    return {
        "analyses": shown(t),
        "farmers": masked(t["u"], t["u"]) if not t["hidden"] else {"value": None, "masked": True},
        "parcels": parcels_c,
        "area_ha": ({"value": round(sum(a or 0 for _, a in area_rows), 2), "masked": False}
                    if not parcels_c["masked"] and parcels else {"value": None, "masked": True}),
        "disease_rate": total["rate"],
        "series": [{"month": month_key(m), "analyses": shown(s["total"]),
                    "farmers": ({"value": None, "masked": True} if s["total"]["hidden"]
                                else masked(s["total"]["u"], s["total"]["u"])),
                    "disease_rate": s["rate"]}
                   for m, s in series.items()],
    }


@cached("plants")
def _plants(f: Filters, db: Session) -> list:
    rows = (base_query(db, f, A.plant_type, N, U, N_SICK, U_SICK, U_OK)
              .group_by(A.plant_type).order_by(N.desc()).all())
    rows = [(p or "unknown", *rest) for p, *rest in rows]
    return [{"plant": p, "analyses": shown(s["total"]), "diseased": shown(s["part"]), "healthy": shown(s["rest"]),
             "disease_rate": s["rate"]} for p, s in split_table(rows, "plant").items()]


@cached("diseases")
def _diseases(f: Filters, db: Session) -> dict:
    code = func.coalesce(A.detected_disease, "healthy")
    cells = suppress([cell(n, u, plant=p or "unknown", disease=d)
                      for p, d, n, u in base_query(db, f, A.plant_type, code, N, U).group_by(A.plant_type, code).all()],
                     ("plant", "disease"))
    totals = suppress([cell(n, u, disease=d) for d, n, u in base_query(db, f, code, N, U).group_by(code).all()],
                      ("disease",))
    top = sorted((t for t in totals if t["disease"] != "healthy"), key=lambda t: -t["n"])
    return {
        "top": [{"disease": t["disease"], "analyses": shown(t)} for t in top if not t["hidden"]]
               + [{"disease": t["disease"], "analyses": shown(t)} for t in top if t["hidden"]],
        "matrix": {"plants": sorted({c["plant"] for c in cells}), "diseases": sorted(t["disease"] for t in totals),
                   "cells": [{"plant": c["plant"], "disease": c["disease"], "analyses": shown(c)} for c in cells]},
    }


@cached("regions")
def _regions(f: Filters, db: Session) -> list:
    rows = base_query(db, f, REGION.label("r"), N, U, N_SICK, U_SICK, U_OK).group_by(REGION).all()
    rows = [(r or "unknown", *rest) for r, *rest in sorted(rows, key=lambda x: -x[1])]
    table = split_table(rows, "region")
    by_disease = (base_query(db, f, REGION.label("r"), A.detected_disease, N, U)
                    .filter(IS_DISEASED).group_by(REGION, A.detected_disease).all())
    best: dict = {}
    for r, code, n, u in by_disease:
        r = r or "unknown"
        if n >= K_ANONYMITY and u >= K_ANONYMITY and n > best.get(r, (None, 0))[1]:
            best[r] = (code, n)
    return [{"region": r, "analyses": shown(s["total"]), "diseased": shown(s["part"]), "disease_rate": s["rate"],
             "top_disease": best.get(r, (None, 0))[0] if not s["total"]["hidden"] else None}
            for r, s in table.items()]


@cached("seasonality")
def _seasonality(f: Filters, db: Session) -> list:
    mon = extract("month", A.created_at)
    rows = (base_query(db, f, mon.label("mo"), A.detected_disease, N, U)
              .filter(IS_DISEASED).group_by(mon, A.detected_disease).all())
    cells = suppress([cell(n, u, month=int(m), disease=code) for m, code, n, u in rows], ("month", "disease"))
    return [{"month": c["month"], "disease": c["disease"], "analyses": shown(c)} for c in cells]


@cached("confidence")
def _confidence(f: Filters, db: Session) -> dict:
    level = func.coalesce(A.severity, "none")
    levels = suppress([cell(n, u, level=lvl) for lvl, n, u in base_query(db, f, level, N, U).group_by(level).all()],
                      ("level",))
    bins = case(*[(A.confidence < (i + 1) / 10, i) for i in range(9)], else_=9)
    hist = suppress([cell(n, u, bin=int(b)) for b, n, u in
                     base_query(db, f, bins.label("b"), N, U).filter(A.confidence.isnot(None)).group_by(bins).all()],
                    ("bin",))
    by_bin = {c["bin"]: c for c in hist}
    is_low = A.confidence < LOW_CONFIDENCE
    low = split_table([("all", *base_query(db, f, N, U, func.sum(case((is_low, 1), else_=0)),
                                           func.count(distinct(case((is_low, A.user_id), else_=None))),
                                           func.count(distinct(case((is_low, None), else_=A.user_id)))).one())], "k")
    return {
        "alert_levels": [{"level": c["level"], "analyses": shown(c)} for c in levels],
        "histogram": [{"from": i / 10, "to": (i + 1) / 10, "analyses": shown(by_bin.get(i))} for i in range(10)],
        "low_confidence_threshold": LOW_CONFIDENCE,
        "low_confidence_rate": low["all"]["rate"],
    }


@cached("model_quality")
def _model_quality(f: Filters, db: Session) -> dict:
    rows = (base_query(db, f, A.detected_disease, A.plant_type, A.verified_label, A.model_version, A.user_id)
              .filter(A.verified_label.isnot(None)).all())
    confusion: dict = defaultdict(lambda: [0, set()])
    by_version: dict = defaultdict(lambda: [0, set(), 0, set(), set()])   # n, users, agree, users agree, users disagree
    for detected, plant, verified, version, uid in rows:
        predicted = class_code(detected, plant)
        ok = predicted == verified
        confusion[(predicted, verified)][0] += 1
        confusion[(predicted, verified)][1].add(uid)
        v = by_version[version or "unknown"]
        v[0] += 1
        v[1].add(uid)
        v[2] += ok
        (v[3] if ok else v[4]).add(uid)
    versions = split_table([(k, n, len(us), a, len(ua), len(ud)) for k, (n, us, a, ua, ud) in sorted(by_version.items())],
                           "model_version")
    users = set().union(*(v[1] for v in by_version.values())) if by_version else set()
    total = split_table([("all", len(rows), len(users), sum(v[2] for v in by_version.values()),
                          len(set().union(*(v[3] for v in by_version.values())) if by_version else set()),
                          len(set().union(*(v[4] for v in by_version.values())) if by_version else set()))], "k")["all"]
    cells = suppress([cell(n, len(us), predicted=p, verified=v) for (p, v), (n, us) in confusion.items()],
                     ("predicted", "verified"))
    labels = sorted({c["predicted"] for c in cells} | {c["verified"] for c in cells})
    return {
        "verified": shown(total["total"]),
        "agreement": total["rate"],
        "by_version": [{"model_version": k, "verified": shown(s["total"]), "agreement": s["rate"]}
                       for k, s in versions.items()],
        "confusion": {"labels": labels,
                      "cells": [{"predicted": c["predicted"], "verified": c["verified"], "analyses": shown(c)}
                                for c in cells]},
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
    is_recent = A.created_at >= recent_from
    rows = (base_query(db, f_now, REGION.label("r"), A.detected_disease, func.sum(case((is_recent, 1), else_=0)),
                       func.count(distinct(case((is_recent, A.user_id), else_=None))), N)
              .filter(A.created_at >= since, IS_DISEASED)
              .group_by(REGION, A.detected_disease).all())
    periods = ALERT_RULE["baseline_weeks"] * 7 / window
    out = []
    for region, code, recent, recent_users, total in rows:
        recent = int(recent or 0)
        before = int(total) - recent
        baseline = before / periods
        if (recent >= max(ALERT_RULE["min_cases"], K_ANONYMITY) and recent_users >= K_ANONYMITY
                and recent > ALERT_RULE["factor"] * baseline):
            # a baseline from 1-4 cases would publish those cases: it is masked
            small = 0 < before < K_ANONYMITY
            out.append({"region": region or "unknown", "disease": code, "recent_cases": recent,
                        "baseline_per_period": None if small else round(baseline, 2),
                        "baseline_masked": small,
                        "ratio": round(recent / baseline, 2) if baseline and not small else None})
    out.sort(key=lambda a: -a["recent_cases"])
    return {"rule": dict(ALERT_RULE), "as_of": today.date().isoformat(), "alerts": out}


@cached("dataset")
def _dataset(f: Filters, db: Session) -> list:
    rows = (base_query(db, f, A.detected_disease, A.plant_type, A.verified_label, A.user_id)
              .filter(A.image_path.isnot(None)).all())
    images: dict = defaultdict(lambda: [0, set()])
    verified: dict = defaultdict(lambda: [0, set()])
    for detected, plant, label, uid in rows:
        c = images[class_code(detected, plant)]
        c[0] += 1
        c[1].add(uid)
        if label:
            verified[label][0] += 1
            verified[label][1].add(uid)
    codes = sorted(set(images) | set(verified))
    img = {c["cls"]: c for c in suppress([cell(n, len(us), cls=k) for k, (n, us) in images.items()], ("cls",))}
    ver = {c["cls"]: c for c in suppress([cell(n, len(us), cls=k) for k, (n, us) in verified.items()], ("cls",))}
    return [{"class": c, "images": shown(img.get(c)), "verified": shown(ver.get(c))} for c in codes]


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
    code = func.coalesce(A.detected_disease, "healthy")
    rows = (base_query(db, f, REGION.label("r"), MONTH.label("m"), A.plant_type, code, N, U)
              .group_by(REGION, MONTH, A.plant_type, code).all())
    cells = suppress([cell(n, u, region=r or "unknown", month=month_key(m), plant=p or "unknown", result=c)
                      for r, m, p, c, n, u in rows], ("region", "month", "plant", "result"))
    cells.sort(key=lambda c: (c["region"], c["month"], c["plant"], c["result"]))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["region", "month", "plant", "result", "analyses"])
    for c in cells:
        w.writerow([c["region"], c["month"], c["plant"], c["result"], "masked" if c["hidden"] else c["n"]])
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
        "properties": {"period": meta["period"], "n": meta["n"]["value"], "n_masked": meta["n"]["masked"],
                       "k_anonymity": K_ANONYMITY, "consent_only": True,
                       "note": "AI predictions (probable diseases), not diagnoses. Counts below 5 analyses "
                               "or 5 farmers, and the cells that would reveal them, are masked.",
                       "attribution": _regions_geojson().get("attribution")},
        "features": features,
    }, ensure_ascii=False), media_type="application/geo+json",
        headers={"Content-Disposition": 'attachment; filename="green-data-regions.geojson"'})
