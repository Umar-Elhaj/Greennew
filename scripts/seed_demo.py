#!/usr/bin/env python3
"""
GREEN — demonstration data for GREEN Data (never mixed with real statistics).

Creates demo farmers (phone +237000xxxxxx, consent given), parcels around the
regional capitals and 12 months of analyses with a plausible pattern:
crops by region, more probable diseases during the two rainy seasons,
model confidence between 0.5 and 0.98, ~10 % of analyses verified by an
agronomist. Every analysis is marked is_demo = true: GREEN Data excludes
them unless "include demo" is ticked, which only exists when DEBUG=true.
No image file is created.

Usage (from the repository root):
  DEBUG=true .venv/bin/python scripts/seed_demo.py              # add (deterministic)
  DEBUG=true .venv/bin/python scripts/seed_demo.py --remove     # delete demo users and their data
Refuses to run against a database when DEBUG is not true, unless --force.
"""

import argparse
import os
import random
import sys
from datetime import UTC, datetime, timedelta

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

DEMO_PHONE_PREFIX = "+237000"

CAPITALS = {  # region -> (lng, lat)
    "Centre": (11.50, 3.85), "Littoral": (9.77, 4.05), "Ouest": (10.42, 5.47), "Nord-Ouest": (10.15, 5.95),
    "Sud-Ouest": (9.24, 4.16), "Sud": (11.15, 2.90), "Est": (13.68, 4.58), "Adamaoua": (13.58, 7.33),
    "Nord": (13.39, 9.30), "Extrême-Nord": (14.32, 10.59),
}
CROPS = {  # region -> weights of (plant)
    "Centre": {"Cassava": 5, "Corn": 4, "Tomato": 1}, "Sud": {"Cassava": 6, "Corn": 3, "Tomato": 1},
    "Est": {"Cassava": 6, "Corn": 4}, "Littoral": {"Cassava": 3, "Corn": 3, "Tomato": 4},
    "Sud-Ouest": {"Cassava": 4, "Corn": 3, "Tomato": 3}, "Ouest": {"Corn": 5, "Tomato": 5},
    "Nord-Ouest": {"Corn": 6, "Tomato": 4}, "Adamaoua": {"Corn": 8, "Cassava": 2},
    "Nord": {"Corn": 9, "Tomato": 1}, "Extrême-Nord": {"Corn": 9, "Tomato": 1},
}
DISEASES = {  # plant -> [(class, weight)] among diseased results
    "Corn": [("Corn_Streak", 4), ("Corn_Leaf_Blight", 3), ("Corn_Brown_Spots", 2), ("Corn_Yellowing", 2),
             ("Corn_Mildew", 1), ("Corn_Stripe", 1)],
    "Tomato": [("Tomato_Blight_Leaf", 5), ("Tomato_Brown_Spots", 4)],
    "Cassava": [("Cassava_Mosaic", 1)],
}
RAINY = {3, 4, 5, 6, 8, 9, 10, 11}


def weighted(rng, items):
    total = sum(w for _, w in items)
    x = rng.uniform(0, total)
    for v, w in items:
        x -= w
        if x <= 0:
            return v
    return items[-1][0]


def seed(db, farmers_per_region: int, analyses_per_farmer: int, rng) -> tuple:
    from auth import hash_password
    from models import DiseaseAnalysis, Parcel, User

    users = parcels = analyses = 0
    now = datetime.now(UTC).replace(tzinfo=None)   # naive UTC like the rest of the schema
    password = hash_password(os.urandom(16).hex())   # demo accounts cannot sign in
    for r_i, (region, (lng, lat)) in enumerate(CAPITALS.items()):
        for f_i in range(farmers_per_region):
            phone = f"{DEMO_PHONE_PREFIX}{r_i:02d}{f_i:04d}"
            if db.query(User).filter(User.phone == phone).first():
                continue
            u = User(first_name="Démo", last_name=f"{region} {f_i + 1}", phone=phone, password_hash=password,
                     region=region, dataset_consent=True, role="farmer")
            db.add(u)
            db.flush()
            users += 1
            plng, plat = lng + rng.uniform(-0.3, 0.3), lat + rng.uniform(-0.3, 0.3)
            d = 0.0009
            ring = [[plng, plat], [plng + d, plat], [plng + d, plat + d], [plng, plat + d], [plng, plat]]
            plant_default = weighted(rng, list(CROPS[region].items()))
            p = Parcel(user_id=u.id, name=f"Démo {region} {f_i + 1}", region=region, crop_type=plant_default,
                       area_ha=round(rng.uniform(0.5, 6), 2), geometry={"type": "Polygon", "coordinates": [ring]},
                       latitude=plat + d / 2, longitude=plng + d / 2)
            db.add(p)
            db.flush()
            parcels += 1
            for _ in range(analyses_per_farmer):
                when = now - timedelta(days=rng.uniform(0, 365))
                plant = weighted(rng, list(CROPS[region].items()))
                p_disease = 0.55 if when.month in RAINY else 0.25
                conf = round(rng.uniform(0.5, 0.98), 4)
                if rng.random() < p_disease:
                    code = weighted(rng, DISEASES[plant])
                    detected, sev = code, "high" if conf >= 0.8 else "medium" if conf >= 0.55 else "low"
                else:
                    code, detected, sev = f"{plant}_Healthy" if plant != "Cassava" else "Cassava_Mosaic", "healthy", "none"
                    if plant == "Cassava":
                        code = None   # no healthy cassava class in the model: label unknown
                verified = None
                if code and rng.random() < 0.1:
                    verified = code if rng.random() < 0.85 else weighted(rng, DISEASES[plant])
                db.add(DiseaseAnalysis(
                    user_id=u.id, parcel_id=p.id, source=rng.choice(["camera", "upload", "rover"]),
                    detected_disease=detected, disease_name=detected, plant_type=plant, confidence=conf,
                    severity=sev, predictions=[], model_version="efficientnet-v1", consent_dataset=True,
                    is_demo=True, created_at=when, verified_label=verified,
                    verified_at=when + timedelta(days=2) if verified else None,
                ))
                analyses += 1
    db.commit()
    return users, parcels, analyses


def remove(db) -> tuple:
    from models import DiseaseAnalysis, Mission, Parcel, User

    ids = [u.id for u in db.query(User).filter(User.phone.like(f"{DEMO_PHONE_PREFIX}%")).all()]
    if not ids:
        return 0, 0
    n = db.query(DiseaseAnalysis).filter(DiseaseAnalysis.is_demo == True,  # noqa: E712
                                         DiseaseAnalysis.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(Mission).filter(Mission.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(Parcel).filter(Parcel.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return len(ids), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true", help="delete the demo users and their data")
    ap.add_argument("--farmers-per-region", type=int, default=6)
    ap.add_argument("--analyses-per-farmer", type=int, default=40)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--force", action="store_true", help="run even when DEBUG is not true")
    args = ap.parse_args()
    if os.getenv("DEBUG", "").lower() not in ("1", "true", "yes") and not args.force:
        print("Refusing to run without DEBUG=true (use --force on purpose).")
        return 2

    from config import DATABASE_URL
    from database import IS_SQLITE, SessionLocal, engine
    import models  # noqa: F401

    if IS_SQLITE:
        from schema_check import migrate_sqlite
        migrate_sqlite(engine)
    from db_url import mask_database_url
    print(f"database: {mask_database_url(DATABASE_URL).split('@')[-1]}")
    db = SessionLocal()
    try:
        if args.remove:
            users, analyses = remove(db)
            print(f"removed {users} demo users and {analyses} demo analyses")
        else:
            users, parcels, analyses = seed(db, args.farmers_per_region, args.analyses_per_farmer,
                                            random.Random(args.seed))  # noqa: S311 (deterministic demo data)
            print(f"added {users} demo users, {parcels} parcels, {analyses} analyses (is_demo = true)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
