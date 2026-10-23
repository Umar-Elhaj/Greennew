# ============================================================
# GREEN App — Parcel Router (GREEN Map)
#
# Parcels are GeoJSON Polygons in WGS84 ([lng, lat]). The server
# validates the outline (geo.validate_polygon) and computes area,
# perimeter, centroid and region; values sent by the client for those
# fields are ignored when a geometry is given.
#
# Offline support (frontend/js/parcel-store.js):
#   - POST with the same `client_id` twice returns the existing parcel;
#   - PUT with `base_updated_at` older than the server version answers
#     409 with the server parcel ("the server wins"; the client keeps its
#     edit as a draft).
#
# Endpoints:
#   GET    /api/parcels               → list the user's parcels (+ analysis stats)
#   POST   /api/parcels               → create (idempotent with client_id)
#   GET    /api/parcels/geo/analyses  → all geolocated analyses (map overlay)
#   GET    /api/parcels/{id}          → one parcel
#   PUT    /api/parcels/{id}          → update (conflict check)
#   DELETE /api/parcels/{id}          → soft delete (is_active = False)
#   GET    /api/parcels/{id}/analyses → analyses linked to the parcel
# ============================================================

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

import geo
from auth import get_current_user
from database import get_db
from i18n import request_lang, translate
from media import media_url
from models import DiseaseAnalysis, Parcel, User

router = APIRouter(prefix="/api/parcels", tags=["Parcels"])


# ---- Request schemas ----------------------------------------

class ParcelCreate(BaseModel):
    name:        str            = Field(min_length=1, max_length=255)
    crop_type:   Optional[str]  = Field(None, max_length=100)
    area_ha:     Optional[float]= Field(None, ge=0)      # only used without geometry
    region:      Optional[str]  = Field(None, max_length=100)
    description: Optional[str]  = Field(None, max_length=2000)
    sowing_date: Optional[date] = None
    geometry:    Optional[dict] = None   # GeoJSON Polygon, [lng, lat]
    latitude:    Optional[float]= Field(None, ge=-90, le=90)
    longitude:   Optional[float]= Field(None, ge=-180, le=180)
    client_id:   Optional[str]  = Field(None, min_length=8, max_length=36)

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: Optional[str]) -> Optional[str]:
        return geo.canonical_region(v)


class ParcelUpdate(BaseModel):
    name:        Optional[str]  = Field(None, min_length=1, max_length=255)
    crop_type:   Optional[str]  = Field(None, max_length=100)
    area_ha:     Optional[float]= Field(None, ge=0)
    region:      Optional[str]  = Field(None, max_length=100)
    description: Optional[str]  = Field(None, max_length=2000)
    sowing_date: Optional[date] = None
    geometry:    Optional[dict] = None
    latitude:    Optional[float]= Field(None, ge=-90, le=90)
    longitude:   Optional[float]= Field(None, ge=-180, le=180)
    is_active:   Optional[bool] = None
    # Version the client edited (its last known updated_at): older than the
    # server's → 409 conflict
    base_updated_at: Optional[datetime] = None

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: Optional[str]) -> Optional[str]:
        return geo.canonical_region(v)


# ---- Helpers -------------------------------------------------

def _parcel_dict(p: Parcel, stats: Optional[dict] = None) -> dict:
    d = {
        "id":          p.id,
        "client_id":   p.client_id,
        "name":        p.name,
        "crop_type":   p.crop_type,
        "area_ha":     p.area_ha,
        "perimeter_m": p.perimeter_m,
        "region":      p.region,
        "description": p.description,
        "sowing_date": p.sowing_date.isoformat() if p.sowing_date else None,
        "geometry":    p.geometry,
        "latitude":    p.latitude,
        "longitude":   p.longitude,
        "is_active":   p.is_active,
        "created_at":  p.created_at.isoformat(),
        "updated_at":  p.updated_at.isoformat() if p.updated_at else None,
    }
    if stats is not None:
        d.update(stats)
    return d


def _apply_geometry(data: dict) -> None:
    """Validate the geometry in `data` and fill area, perimeter, centre, region."""
    try:
        data["geometry"] = geo.validate_polygon(data["geometry"])
    except geo.GeometryError as e:
        raise HTTPException(status_code=422, detail=str(e))
    m = geo.measures(data["geometry"])
    data["area_ha"] = round(m["area_ha"], 4)
    data["perimeter_m"] = round(m["perimeter_m"], 1)
    data["latitude"] = round(m["latitude"], 7)
    data["longitude"] = round(m["longitude"], 7)
    if not data.get("region"):
        data["region"] = geo.region_of(m["longitude"], m["latitude"])


def _owned(db: Session, user: User, parcel_id: int) -> Parcel:
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.user_id == user.id).first()
    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel not found.")
    return parcel


def _analysis_stats(db: Session, user: User) -> dict:
    rows = (
        db.query(DiseaseAnalysis.parcel_id, func.count(DiseaseAnalysis.id), func.max(DiseaseAnalysis.created_at))
          .filter(DiseaseAnalysis.user_id == user.id, DiseaseAnalysis.parcel_id.isnot(None))
          .group_by(DiseaseAnalysis.parcel_id)
          .all()
    )
    return {pid: {"analyses_count": n, "last_analysis_at": last.isoformat() if last else None}
            for pid, n, last in rows}


# ---- GET /api/parcels ----------------------------------------
@router.get("", summary="List the user's active parcels")
def list_parcels(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    parcels = (
        db.query(Parcel)
          .filter(Parcel.user_id == current_user.id, Parcel.is_active == True)  # noqa: E712
          .order_by(Parcel.created_at.desc())
          .all()
    )
    stats = _analysis_stats(db, current_user)
    empty = {"analyses_count": 0, "last_analysis_at": None}
    return [_parcel_dict(p, stats.get(p.id, empty)) for p in parcels]


# ---- POST /api/parcels ---------------------------------------
@router.post("", summary="Create a parcel (idempotent with client_id)", status_code=201)
def create_parcel(
    payload:      ParcelCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    if payload.client_id:
        existing = db.query(Parcel).filter(
            Parcel.user_id == current_user.id, Parcel.client_id == payload.client_id,
        ).first()
        if existing:
            return JSONResponse(_parcel_dict(existing), status_code=200)

    data = payload.model_dump()
    if data.get("geometry") is not None:
        _apply_geometry(data)
    elif data.get("latitude") is not None and data.get("longitude") is not None and not data.get("region"):
        data["region"] = geo.region_of(data["longitude"], data["latitude"])

    parcel = Parcel(user_id=current_user.id, is_active=True, **data)
    db.add(parcel)
    db.commit()
    db.refresh(parcel)
    return _parcel_dict(parcel)


# ---- GET /api/parcels/geo/analyses ---------------------------
# Declared before /{parcel_id}: otherwise "geo" is parsed as an id (422).
@router.get("/geo/analyses", summary="All geolocated analyses (map overlay)")
def get_all_geolocated_analyses(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    analyses = (
        db.query(DiseaseAnalysis)
          .filter(
              DiseaseAnalysis.user_id   == current_user.id,
              DiseaseAnalysis.latitude.isnot(None),
              DiseaseAnalysis.longitude.isnot(None),
          )
          .order_by(DiseaseAnalysis.created_at.desc())
          .limit(5000)
          .all()
    )
    return [_analysis_point(a) for a in analyses]


def _analysis_point(a: DiseaseAnalysis) -> dict:
    return {
        "id":               a.id,
        "detected_disease": a.detected_disease,
        "plant_type":       a.plant_type,
        "severity":         a.severity,
        "confidence":       a.confidence,
        "source":           a.source,
        "latitude":         a.latitude,
        "longitude":        a.longitude,
        "parcel_id":        a.parcel_id,
        "mission_id":       a.mission_id,
        "cell_index":       a.cell_index,
        "thumb_path":       media_url(a.image_path, a.user_id, thumb=True),
        "created_at":       a.created_at.isoformat(),
    }


# ---- GET /api/parcels/{id} -----------------------------------
@router.get("/{parcel_id}", summary="Get one parcel")
def get_parcel(
    parcel_id:    int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return _parcel_dict(_owned(db, current_user, parcel_id))


# ---- PUT /api/parcels/{id} -----------------------------------
@router.put("/{parcel_id}", summary="Update a parcel (409 if the server version is newer)")
def update_parcel(
    parcel_id:    int,
    payload:      ParcelUpdate,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    parcel = _owned(db, current_user, parcel_id)

    base = payload.base_updated_at
    if base is not None:
        base = base.replace(tzinfo=None)
        if parcel.updated_at and parcel.updated_at > base + timedelta(seconds=1):
            msg = "This parcel was changed elsewhere in the meantime: the server version is kept."
            return JSONResponse(
                {"detail": translate(msg, request_lang(request)), "parcel": _parcel_dict(parcel)},
                status_code=409,
            )

    data = payload.model_dump(exclude_unset=True, exclude={"base_updated_at"})
    if data.get("geometry") is not None:
        _apply_geometry(data)
    for field, value in data.items():
        if value is None and field in ("name", "is_active"):
            continue
        setattr(parcel, field, value)

    db.commit()
    db.refresh(parcel)
    return _parcel_dict(parcel)


# ---- DELETE /api/parcels/{id} --------------------------------
@router.delete("/{parcel_id}", summary="Soft-delete a parcel")
def delete_parcel(
    parcel_id:    int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    """Marks the parcel inactive so the analyses that reference it stay in history."""
    parcel = _owned(db, current_user, parcel_id)
    parcel.is_active = False
    db.commit()
    return {"success": True, "message": "Parcel deleted."}


# ---- GET /api/parcels/{id}/analyses -------------------------
@router.get("/{parcel_id}/analyses", summary="Analyses linked to a parcel")
def get_parcel_analyses(
    parcel_id:    int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    _owned(db, current_user, parcel_id)
    analyses = (
        db.query(DiseaseAnalysis)
          .filter(DiseaseAnalysis.parcel_id == parcel_id, DiseaseAnalysis.user_id == current_user.id)
          .order_by(DiseaseAnalysis.created_at.desc())
          .all()
    )
    return [_analysis_point(a) for a in analyses]
