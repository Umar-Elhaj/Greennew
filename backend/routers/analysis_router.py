# ============================================================
# GREEN App — Disease Analysis Router
# Manages the history of disease scans (saved frames + results).
#
# Endpoints:
#   GET    /api/analysis/history         → paginated scan history
#   GET    /api/analysis/{id}            → single analysis + fiche terrain
#   DELETE /api/analysis/{id}            → remove from history
# ============================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from models import User, DiseaseAnalysis
from auth import get_current_user
from i18n import request_lang
from knowledge import fiche_for_analysis
from media import delete_image, media_url

router = APIRouter(prefix="/api/analysis", tags=["Disease Analysis"])


# ---- GET /api/analysis/history -------------------------------
@router.get("/history", summary="Get paginated disease analysis history")
def get_history(
    limit:       int           = Query(default=20, ge=1, le=100),
    offset:      int           = Query(default=0,  ge=0),
    source:      Optional[str] = Query(None, description="Filter by source: camera|upload|drone"),
    result_type: Optional[str] = Query(None, description="Filter by result: disease|healthy"),
    plant_type:  Optional[str] = Query(None, description="Filter by plant: Corn|Tomato|Cassava"),
    db:          Session       = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    Returns a paginated list of the user's past disease analyses,
    ordered newest first. Supports server-side filtering by source,
    result type (disease/healthy), and plant type.

    Used by: dashboard recent table, History page.
    """
    q = db.query(DiseaseAnalysis).filter(DiseaseAnalysis.user_id == current_user.id)

    if source:
        q = q.filter(DiseaseAnalysis.source == source)

    if result_type == "disease":
        q = q.filter(
            DiseaseAnalysis.detected_disease != None,
            DiseaseAnalysis.detected_disease != "healthy",
        )
    elif result_type == "healthy":
        q = q.filter(DiseaseAnalysis.detected_disease == "healthy")

    if plant_type:
        q = q.filter(DiseaseAnalysis.plant_type.ilike(f"%{plant_type}%"))

    total    = q.count()
    analyses = q.order_by(DiseaseAnalysis.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "items": [
            {
                "id":               a.id,
                "disease_name":     a.disease_name,
                "detected_disease": a.detected_disease,
                "plant_type":       a.plant_type,
                "severity":         a.severity,
                "confidence":       a.confidence,
                "source":           a.source,
                "parcel_id":        a.parcel_id,
                "latitude":         a.latitude,
                "longitude":        a.longitude,
                "image_path":       media_url(a.image_path, a.user_id),
                "thumb_path":       media_url(a.image_path, a.user_id, thumb=True),
                "created_at":       a.created_at.isoformat(),
                "has_fiche":        a.fiche_terrain is not None,
            }
            for a in analyses
        ],
    }


# ---- GET /api/analysis/{id} ----------------------------------
@router.get("/{analysis_id}", summary="Get a single analysis with full fiche terrain")
def get_analysis(
    analysis_id:  int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns a single analysis enriched with the complete fiche terrain.
    If the fiche was already saved on creation (Phase 4), it is returned directly.
    Otherwise, it is generated on-the-fly from diseases.json.
    """
    analysis = (
        db.query(DiseaseAnalysis)
          .filter(
              DiseaseAnalysis.id == analysis_id,
              DiseaseAnalysis.user_id == current_user.id
          )
          .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    # Built in the reader's language from the stored prediction
    fiche = fiche_for_analysis(analysis, request_lang(request))

    return {
        "id":               analysis.id,
        "disease_name":     analysis.disease_name,
        "detected_disease": analysis.detected_disease,
        "plant_type":       analysis.plant_type,
        "severity":         analysis.severity,
        "confidence":       analysis.confidence,
        "source":           analysis.source,
        "parcel_id":        analysis.parcel_id,
        "latitude":         analysis.latitude,
        "longitude":        analysis.longitude,
        "notes":            analysis.notes,
        "image_path":       media_url(analysis.image_path, analysis.user_id),
        "thumb_path":       media_url(analysis.image_path, analysis.user_id, thumb=True),
        "created_at":       analysis.created_at.isoformat(),
        "fiche_terrain":    fiche,
    }


# ---- DELETE /api/analysis/{id} -------------------------------
@router.delete("/{analysis_id}", summary="Delete an analysis from history")
def delete_analysis(
    analysis_id:  int,
    db:           Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permanently removes an analysis record and its saved image (if any).
    Only the owner can delete their own analyses.
    """
    analysis = (
        db.query(DiseaseAnalysis)
          .filter(
              DiseaseAnalysis.id == analysis_id,
              DiseaseAnalysis.user_id == current_user.id
          )
          .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    image_path = analysis.image_path
    db.delete(analysis)
    db.commit()
    # Remove image + thumbnail once the row is gone (orphans are listed by media_report.py)
    delete_image(image_path)
    return {"message": "Analysis deleted.", "success": True}


# ---- GET /api/analysis/fiche/{id} ----------------------------
@router.get("/fiche/{analysis_id}", summary="Get only the fiche terrain for an analysis")
def get_fiche(
    analysis_id:  int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns only the fiche terrain (terrain sheet) for a given analysis.
    Used by the History page and the post-scan modal to display the fiche.
    """
    analysis = (
        db.query(DiseaseAnalysis)
          .filter(
              DiseaseAnalysis.id == analysis_id,
              DiseaseAnalysis.user_id == current_user.id
          )
          .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    return fiche_for_analysis(analysis, request_lang(request))
