"""Dashboard endpoints: progress aggregates on a fixed data set."""

from datetime import datetime, timedelta

from database import SessionLocal
from models import DiseaseAnalysis


def _add(user_id, when, detected, plant):
    db = SessionLocal()
    db.add(DiseaseAnalysis(user_id=user_id, created_at=when, detected_disease=detected, plant_type=plant,
                           confidence=0.9, source="upload"))
    db.commit()
    db.close()


def test_progress_monthly_aggregates(client, user, other_user):
    uid = user["user"]["id"]
    now = datetime.utcnow().replace(day=15)
    last_month = (now.replace(day=1) - timedelta(days=1)).replace(day=10)
    _add(uid, now, "Corn_Streak", "Corn")
    _add(uid, now, "healthy", "Corn")
    _add(uid, now, "Corn_Streak", "Corn")
    _add(uid, last_month, "Tomato_Blight_Leaf", "Tomato")
    _add(uid, now - timedelta(days=400), "Corn_Streak", "Corn")          # outside the window
    _add(other_user["user"]["id"], now, "Corn_Streak", "Corn")            # someone else

    r = client.get("/api/dashboard/progress?months=3", headers=user["headers"]).json()
    assert [m["analyses"] for m in r["months"]] == [0, 1, 3]
    assert r["months"][-1] == {"month": f"{now:%Y-%m}", "analyses": 3, "diseases": 2, "healthy": 1}
    assert r["top_disease"] == {"code": "Corn_Streak", "count": 2}
    assert r["total"] == 4
    corn = next(p for p in r["plants"] if p["plant"] == "Corn")
    assert corn == {"plant": "Corn", "analyses": 3, "diseases": 2}


def test_progress_empty(client, user):
    r = client.get("/api/dashboard/progress", headers=user["headers"]).json()
    assert r["total"] == 0 and len(r["months"]) == 6 and r["top_disease"] is None
