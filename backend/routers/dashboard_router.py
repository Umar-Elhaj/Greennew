# ============================================================
# GREEN App — Dashboard Router
# Endpoints:
#   GET /api/dashboard/stats          → KPI counts for the dashboard cards
#   GET /api/dashboard/disease-trends → Weekly detection data for the chart
# ============================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from database import get_db
from models import User, Parcel, DiseaseAnalysis, ChatSession
from auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# ---- GET /api/dashboard/stats --------------------------------
@router.get("/stats", summary="Get KPI counts for the dashboard")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns summary counts used by the 4 KPI cards:
    - parcels        : active parcels the user has mapped
    - analyses       : total disease scans performed
    - diseases       : positive disease detections (non-healthy)
    - chat_sessions  : total GreenBot conversations
    Also returns week-over-week change for each metric.
    """
    uid = current_user.id
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # ---- Current totals ----
    parcels       = db.query(func.count(Parcel.id)).filter(
                        Parcel.user_id == uid, Parcel.is_active == True
                    ).scalar() or 0

    analyses      = db.query(func.count(DiseaseAnalysis.id)).filter(
                        DiseaseAnalysis.user_id == uid
                    ).scalar() or 0

    diseases      = db.query(func.count(DiseaseAnalysis.id)).filter(
                        DiseaseAnalysis.user_id == uid,
                        DiseaseAnalysis.detected_disease != None,
                        DiseaseAnalysis.detected_disease != "healthy"
                    ).scalar() or 0

    healthy       = db.query(func.count(DiseaseAnalysis.id)).filter(
                        DiseaseAnalysis.user_id == uid,
                        DiseaseAnalysis.detected_disease == "healthy"
                    ).scalar() or 0

    chat_sessions = db.query(func.count(ChatSession.id)).filter(
                        ChatSession.user_id == uid
                    ).scalar() or 0

    # ---- New this week (for change indicators) ----
    new_analyses_wk  = db.query(func.count(DiseaseAnalysis.id)).filter(
                           DiseaseAnalysis.user_id == uid,
                           DiseaseAnalysis.created_at >= week_ago
                       ).scalar() or 0

    new_diseases_wk  = db.query(func.count(DiseaseAnalysis.id)).filter(
                           DiseaseAnalysis.user_id == uid,
                           DiseaseAnalysis.detected_disease != None,
                           DiseaseAnalysis.detected_disease != "healthy",
                           DiseaseAnalysis.created_at >= week_ago
                       ).scalar() or 0

    new_healthy_wk   = db.query(func.count(DiseaseAnalysis.id)).filter(
                           DiseaseAnalysis.user_id == uid,
                           DiseaseAnalysis.detected_disease == "healthy",
                           DiseaseAnalysis.created_at >= week_ago
                       ).scalar() or 0

    new_chats_wk     = db.query(func.count(ChatSession.id)).filter(
                           ChatSession.user_id == uid,
                           ChatSession.created_at >= week_ago
                       ).scalar() or 0

    return {
        "parcels":              parcels,
        "analyses":             analyses,
        "diseases":             diseases,
        "healthy":              healthy,
        "chat_sessions":        chat_sessions,
        # Week-over-week additions (used for change pills in UI)
        "new_analyses_week":    new_analyses_wk,
        "new_diseases_week":    new_diseases_wk,
        "new_healthy_week":     new_healthy_wk,
        "new_chats_week":       new_chats_wk,
    }


# ---- GET /api/dashboard/disease-trends -----------------------
@router.get("/disease-trends", summary="Weekly disease detection data for the chart")
def get_disease_trends(
    days: int = Query(default=30, ge=7, le=365, description="Look-back window in days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns weekly aggregated counts of disease detections vs healthy results
    for the last `days` days. Used to render the bar chart on the dashboard.

    Response shape (week_starts are ISO dates; the client formats them
    in the user's language):
    {
      "week_starts": ["2026-09-24", "2026-10-01", ...],
      "detections":  [3, 1, 5, 2],
      "healthy":     [10, 8, 14, 7]
    }
    """
    uid   = current_user.id
    since = datetime.utcnow() - timedelta(days=days)

    # Fetch all analyses in the window
    analyses = (
        db.query(DiseaseAnalysis)
          .filter(
              DiseaseAnalysis.user_id == uid,
              DiseaseAnalysis.created_at >= since
          )
          .order_by(DiseaseAnalysis.created_at.asc())
          .all()
    )

    # Build weekly buckets (ISO week number relative to `since`)
    num_weeks = max(1, days // 7)
    buckets = []
    for i in range(num_weeks):
        week_start = since + timedelta(weeks=i)
        week_end   = week_start + timedelta(weeks=1)
        detections = sum(
            1 for a in analyses
            if week_start <= a.created_at < week_end
            and a.detected_disease
            and a.detected_disease != "healthy"
        )
        healthy = sum(
            1 for a in analyses
            if week_start <= a.created_at < week_end
            and (not a.detected_disease or a.detected_disease == "healthy")
        )
        buckets.append({
            "week_start": week_start.date().isoformat(),
            "detections": detections,
            "healthy":    healthy,
        })

    return {
        "week_starts": [b["week_start"] for b in buckets],
        "detections": [b["detections"] for b in buckets],
        "healthy":    [b["healthy"]    for b in buckets],
        "period_days": days,
        "total_analyses": len(analyses),
    }


# ---- GET /api/dashboard/recent-activity ----------------------
@router.get("/recent-activity", summary="Latest 5 analyses for the activity feed")
def get_recent_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the 5 most recent analyses with their key fields.
    Used by the 'Recent Analyses' table at the bottom of the dashboard.
    """
    analyses = (
        db.query(DiseaseAnalysis)
          .filter(DiseaseAnalysis.user_id == current_user.id)
          .order_by(DiseaseAnalysis.created_at.desc())
          .limit(5)
          .all()
    )

    return [
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
            "created_at":       a.created_at.isoformat(),
        }
        for a in analyses
    ]


# ---- GET /api/dashboard/progress ------------------------------
@router.get("/progress", summary="The user's own monthly history (My progress page)")
def get_progress(
    months: int = Query(default=6, ge=2, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Per calendar month (oldest first): number of analyses, probable diseases,
    healthy results; per plant over the period; most frequent probable
    disease. Compared only with the user's own past: no invented averages.
    """
    now = datetime.utcnow()
    # first day of the oldest month in the window
    y, m = now.year, now.month - (months - 1)
    while m <= 0:
        m += 12
        y -= 1
    start = datetime(y, m, 1)

    rows = (
        db.query(DiseaseAnalysis.created_at, DiseaseAnalysis.detected_disease, DiseaseAnalysis.plant_type,
                 DiseaseAnalysis.parcel_id)
          .filter(DiseaseAnalysis.user_id == current_user.id, DiseaseAnalysis.created_at >= start)
          .all()
    )

    keys = []
    yy, mm = y, m
    for _ in range(months):
        keys.append(f"{yy:04d}-{mm:02d}")
        mm += 1
        if mm > 12:
            mm, yy = 1, yy + 1
    monthly = {k: {"month": k, "analyses": 0, "diseases": 0, "healthy": 0} for k in keys}
    plants: dict = {}
    disease_counts: dict = {}
    parcels = set()

    for created_at, detected, plant, parcel_id in rows:
        k = f"{created_at.year:04d}-{created_at.month:02d}"
        if k not in monthly:
            continue
        diseased = bool(detected) and detected != "healthy"
        monthly[k]["analyses"] += 1
        monthly[k]["diseases" if diseased else "healthy"] += 1
        p = plants.setdefault(plant or "unknown", {"plant": plant, "analyses": 0, "diseases": 0})
        p["analyses"] += 1
        p["diseases"] += int(diseased)
        if diseased:
            disease_counts[detected] = disease_counts.get(detected, 0) + 1
        if parcel_id:
            parcels.add(parcel_id)

    top = max(disease_counts.items(), key=lambda kv: kv[1]) if disease_counts else None
    return {
        "months": [monthly[k] for k in keys],
        "plants": sorted(plants.values(), key=lambda p: -p["analyses"]),
        "top_disease": {"code": top[0], "count": top[1]} if top else None,
        "parcels_analysed": len(parcels),
        "total": len(rows),
    }
