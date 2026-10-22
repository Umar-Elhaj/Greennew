# ============================================================
# GREEN App — Missions (GREEN Map grid + rover path)
#
# A mission freezes the grid and serpentine path computed for a parcel
# (geo.build_grid). Analyses sent with mission_id + cell_index feed the
# per-cell heatmap. Contract for the rover: docs/rover_mission_contract.md
#
#   POST   /api/missions/preview          → grid + path, not saved
#   POST   /api/missions                  → create (status draft)
#   GET    /api/missions?parcel_id=       → list (summaries)
#   GET    /api/missions/{id}             → full mission + progress
#   PATCH  /api/missions/{id}             → name / status
#   DELETE /api/missions/{id}             → delete (analyses keep their image, lose the link)
#   GET    /api/missions/{id}/waypoints   → ordered waypoints for the rover
#   GET    /api/missions/{id}/export.geojson → cells + path + parcel
#   GET    /api/missions/{id}/heatmap     → per-cell aggregates (filters)
# ============================================================

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import geo
from auth import get_current_user
from database import get_db
from models import DiseaseAnalysis, Mission, Parcel, User

router = APIRouter(prefix="/api/missions", tags=["Missions"])

STATUSES = ("draft", "ready", "running", "done")
ALERT_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class MissionIn(BaseModel):
    parcel_id:   int
    cell_size_m: float = Field(5, ge=1, le=50)
    speed_mps:   float = Field(0.5, gt=0, le=5)
    start:       Optional[LatLng] = None
    name:        Optional[str] = Field(None, max_length=255)


class MissionPatch(BaseModel):
    name:   Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, pattern="^(draft|ready|running|done)$")


# ---- helpers -------------------------------------------------
def _parcel(db: Session, user: User, parcel_id: int) -> Parcel:
    p = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.user_id == user.id,
                                Parcel.is_active == True).first()  # noqa: E712
    if not p:
        raise HTTPException(status_code=404, detail="Parcel not found.")
    if not p.geometry:
        raise HTTPException(status_code=422, detail="This parcel has no outline: draw it on the map first.")
    return p


def owned_mission(db: Session, user: User, mission_id: int) -> Mission:
    m = db.query(Mission).filter(Mission.id == mission_id, Mission.user_id == user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return m


def _compute(parcel: Parcel, body: MissionIn) -> dict:
    try:
        start = (body.start.lng, body.start.lat) if body.start else None
        return geo.build_grid(parcel.geometry, body.cell_size_m, start=start, speed_mps=body.speed_mps)
    except geo.GeometryError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _progress(db: Session, m: Mission) -> dict:
    analysed = (db.query(func.count(func.distinct(DiseaseAnalysis.cell_index)))
                  .filter(DiseaseAnalysis.mission_id == m.id, DiseaseAnalysis.cell_index.isnot(None))
                  .scalar() or 0)
    return {"analysed_cells": analysed, "total_cells": m.cells_total,
            "ratio": round(analysed / m.cells_total, 4) if m.cells_total else 0}


def _summary(m: Mission, progress: Optional[dict] = None) -> dict:
    d = {
        "id": m.id, "parcel_id": m.parcel_id, "name": m.name, "status": m.status,
        "cell_size_m": m.cell_size_m, "speed_mps": m.speed_mps, "angle_deg": m.angle_deg,
        "start": {"lat": m.start_lat, "lng": m.start_lng} if m.start_lat is not None else None,
        "cells_total": m.cells_total, "distance_m": m.distance_m, "duration_s": m.duration_s,
        "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(),
    }
    if progress is not None:
        d["progress"] = progress
    return d


# ---- endpoints -----------------------------------------------
@router.post("/preview", summary="Grid and path for a parcel, without saving")
def preview_mission(body: MissionIn, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    grid = _compute(_parcel(db, current_user, body.parcel_id), body)
    return {"parcel_id": body.parcel_id, **grid, "cells_total": len(grid["cells"])}


@router.post("", summary="Freeze a grid and path as a mission", status_code=201)
def create_mission(body: MissionIn, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    parcel = _parcel(db, current_user, body.parcel_id)
    grid = _compute(parcel, body)
    m = Mission(
        user_id=current_user.id, parcel_id=parcel.id, name=body.name, status="draft",
        cell_size_m=body.cell_size_m, speed_mps=body.speed_mps,
        start_lat=body.start.lat if body.start else None, start_lng=body.start.lng if body.start else None,
        angle_deg=grid["angle_deg"], cells_total=len(grid["cells"]), distance_m=grid["distance_m"],
        duration_s=grid["duration_s"], grid=grid["cells"], waypoints=grid["waypoints"],
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {**_summary(m, _progress(db, m)), "grid": m.grid, "waypoints": m.waypoints}


@router.get("", summary="List missions (summaries)")
def list_missions(parcel_id: Optional[int] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    q = db.query(Mission).filter(Mission.user_id == current_user.id)
    if parcel_id is not None:
        q = q.filter(Mission.parcel_id == parcel_id)
    return [_summary(m, _progress(db, m)) for m in q.order_by(Mission.created_at.desc()).all()]


@router.get("/{mission_id}", summary="Full mission with grid, waypoints and progress")
def get_mission(mission_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    m = owned_mission(db, current_user, mission_id)
    return {**_summary(m, _progress(db, m)), "grid": m.grid, "waypoints": m.waypoints}


@router.patch("/{mission_id}", summary="Rename or change the status of a mission")
def patch_mission(mission_id: int, body: MissionPatch, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    m = owned_mission(db, current_user, mission_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return _summary(m, _progress(db, m))


@router.delete("/{mission_id}", summary="Delete a mission")
def delete_mission(mission_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    m = owned_mission(db, current_user, mission_id)
    db.query(DiseaseAnalysis).filter(DiseaseAnalysis.mission_id == m.id).update(
        {DiseaseAnalysis.mission_id: None, DiseaseAnalysis.cell_index: None}, synchronize_session=False)
    db.delete(m)
    db.commit()
    return {"success": True}


@router.get("/{mission_id}/waypoints", summary="Ordered waypoints for the rover")
def get_waypoints(mission_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    m = owned_mission(db, current_user, mission_id)
    return {
        "mission_id": m.id, "parcel_id": m.parcel_id, "cell_size_m": m.cell_size_m,
        "speed_mps": m.speed_mps, "cells_total": m.cells_total, "distance_m": m.distance_m,
        "crs": "EPSG:4326", "waypoints": m.waypoints,
    }


@router.get("/{mission_id}/export.geojson", summary="Cells, path and parcel as GeoJSON")
def export_geojson(mission_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    m = owned_mission(db, current_user, mission_id)
    parcel = db.get(Parcel, m.parcel_id)
    features = [{"type": "Feature", "geometry": parcel.geometry,
                 "properties": {"kind": "parcel", "parcel_id": parcel.id, "name": parcel.name}}]
    features += [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [c["polygon"]]},
                  "properties": {"kind": "cell", "cell_index": c["index"], "row": c["row"], "col": c["col"]}}
                 for c in m.grid]
    features.append({"type": "Feature",
                     "geometry": {"type": "LineString", "coordinates": [[w["lng"], w["lat"]] for w in m.waypoints]},
                     "properties": {"kind": "path", "distance_m": m.distance_m}})
    return JSONResponse(
        {"type": "FeatureCollection", "properties": _summary(m), "features": features},
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="green-mission-{m.id}.geojson"'},
    )


@router.get("/{mission_id}/heatmap", summary="Per-cell aggregates of the mission's analyses")
def get_heatmap(
    mission_id: int,
    disease: Optional[str] = Query(None, description="Only analyses of this class code"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    For each cell with at least one analysis: number of analyses, probable
    diseases, disease rate, highest alert level, dominant probable disease,
    last analysis and the ids of the latest analyses. Cells without analyses
    are absent (the client shows them as not analysed).
    """
    m = owned_mission(db, current_user, mission_id)
    q = db.query(DiseaseAnalysis).filter(DiseaseAnalysis.mission_id == m.id, DiseaseAnalysis.user_id == current_user.id,
                                         DiseaseAnalysis.cell_index.isnot(None))
    if disease:
        q = q.filter(DiseaseAnalysis.detected_disease == disease)
    if date_from:
        q = q.filter(DiseaseAnalysis.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(DiseaseAnalysis.created_at < datetime.combine(date_to, datetime.min.time()) + timedelta(days=1))

    cells: dict = {}
    for a in q.order_by(DiseaseAnalysis.created_at.desc()).all():
        c = cells.setdefault(a.cell_index, {"index": a.cell_index, "analyses": 0, "diseased": 0,
                                            "max_alert": "none", "_diseases": Counter(),
                                            "last_at": None, "analysis_ids": []})
        diseased = bool(a.detected_disease) and a.detected_disease != "healthy"
        c["analyses"] += 1
        if diseased:
            c["diseased"] += 1
            c["_diseases"][a.detected_disease] += 1
            level = a.severity if a.severity in ALERT_ORDER else "low"
            if ALERT_ORDER[level] > ALERT_ORDER[c["max_alert"]]:
                c["max_alert"] = level
        c["last_at"] = c["last_at"] or a.created_at.isoformat()
        if len(c["analysis_ids"]) < 6:
            c["analysis_ids"].append(a.id)

    out = []
    for c in sorted(cells.values(), key=lambda x: x["index"]):
        counts = c.pop("_diseases")
        c["rate"] = round(c["diseased"] / c["analyses"], 4)
        c["dominant"] = counts.most_common(1)[0][0] if counts else None
        out.append(c)
    diseases = sorted({c["dominant"] for c in out if c["dominant"]})
    return {"mission": _summary(m, _progress(db, m)), "cells": out, "diseases": diseases,
            "filters": {"disease": disease, "date_from": date_from, "date_to": date_to}}
