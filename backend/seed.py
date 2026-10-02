"""
Seed the app with realistic demo data so it feels alive on first load.

Creates:
  * 2 evaluator/admin accounts + 6 farmer accounts (Dakshina Kannada villages/taluks)
  * 16 prediction-history rows generated through the REAL model (not hand-written scores)
  * 5 of those with outcome feedback (the feedback loop in action)
  * 20 primary survey entries (approved / pending / rejected, one without consent)
  * crop reference rows imported from the built-in cited knowledge base
  * a few audit-log rows

Idempotent: does nothing if users already exist (use --force to wipe and reseed).

Run:  python seed.py            (from backend/)
      python seed.py --force
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app.cleaning import WATER_LEVEL_BY_SOURCE, sample_weight_for
from app.db import Base, SessionLocal, engine, init_db
from app.ml.knowledge import CROPS, MODEL_CROP_LABELS
from app.ml.registry import registry
from app.models import AuditLog, CropReference, Prediction, SurveyEntry, User

random.seed(20260211)   # reproducible demo data

NOW = datetime.now(timezone.utc)

USERS = [
    dict(name="Dr. Kavya Shetty", email="admin@cropadvisor.in", role="admin", password="admin123",
         phone="+91 94800 11223", village="Kadri", taluk="Mangaluru",
         district="Dakshina Kannada"),
    dict(name="External Evaluator", email="evaluator@cropadvisor.in", role="admin", password="evaluator123",
         phone="+91 98860 44556", village="Mangalagangothri", taluk="Mangaluru",
         district="Dakshina Kannada"),
    dict(name="Ravi Naik", email="ravi@example.com", role="farmer", password="farmer123",
         phone="+91 98861 20011", village="Kinnigoli", taluk="Mulki"),
    dict(name="Lakshmi Bhat", email="lakshmi@example.com", role="farmer", password="farmer123",
         phone="+91 98862 30022", village="Shirthady", taluk="Moodabidri"),
    dict(name="Ganesh Gowda", email="ganesh@example.com", role="farmer", password="farmer123",
         phone="+91 98863 40033", village="Kabaka", taluk="Puttur"),
    dict(name="Shobha Rai", email="shobha@example.com", role="farmer", password="farmer123",
         phone="+91 98864 50044", village="Bellare", taluk="Sullia"),
    dict(name="Mohammed Iqbal", email="iqbal@example.com", role="farmer", password="farmer123",
         phone="+91 98865 60055", village="Vittal", taluk="Bantwal"),
    dict(name="Sumathi Hegde", email="sumathi@example.com", role="farmer", password="farmer123",
         phone="+91 98866 70066", village="Ujire", taluk="Belthangady"),
]

# (soil, season, rainfall mm, water source, taluk, village) — realistic DK combinations
PREDICTION_INPUTS = [
    ("laterite", "Kharif", 240, "rainfed", "Mulki", "Kinnigoli"),
    ("laterite", "Kharif", 260, "rainfed", "Puttur", "Kabaka"),
    ("laterite", "Rabi", 70, "borewell", "Puttur", "Kabaka"),
    ("alluvial", "Kharif", 220, "canal", "Bantwal", "Vittal"),
    ("alluvial", "Zaid", 30, "canal", "Bantwal", "Vittal"),
    ("coastal_sandy", "Kharif", 250, "rainfed", "Mulki", "Kinnigoli"),
    ("laterite", "Kharif", 230, "rainfed", "Sullia", "Bellare"),
    ("laterite", "Rabi", 65, "open_well", "Sullia", "Bellare"),
    ("red_loam", "Kharif", 200, "borewell", "Belthangady", "Ujire"),
    ("laterite", "Kharif", 235, "rainfed", "Moodabidri", "Shirthady"),
    ("coastal_sandy", "Zaid", 35, "borewell", "Mangaluru", "Kadri"),
    ("laterite", "Rabi", 80, "borewell", "Belthangady", "Ujire"),
    ("alluvial", "Kharif", 215, "river_lift", "Bantwal", "Sajipa"),
    ("red_loam", "Rabi", 75, "open_well", "Moodabidri", "Shirthady"),
    ("laterite", "Zaid", 40, "tank", "Puttur", "Nettanige"),
    ("coastal_saline", "Kharif", 245, "rainfed", "Ullal", "Someshwara"),
]

FEEDBACK = ["good", "excellent", "average", "good", "excellent"]

# Primary survey rows: (crop, season, soil, rainfall, water_source, yield_outcome, area)
SURVEYS = [
    ("rice", "Kharif", "laterite", 255, "rainfed", "good", 1.8),
    ("rice", "Kharif", "alluvial", 230, "canal", "excellent", 2.4),
    ("arecanut", "Kharif", "laterite", 260, "rainfed", "good", 1.2),
    ("coconut", "Kharif", "coastal_sandy", 245, "rainfed", "average", 0.9),
    ("banana", "Kharif", "alluvial", 225, "borewell", "good", 1.1),
    ("blackgram", "Rabi", "laterite", 70, "borewell", "good", 0.8),
    ("cowpea", "Rabi", "laterite", 65, "open_well", "average", 0.6),
    ("horsegram", "Rabi", "laterite", 60, "rainfed", "good", 0.5),
    ("groundnut", "Zaid", "coastal_sandy", 35, "borewell", "average", 0.7),
    ("watermelon", "Zaid", "coastal_sandy", 30, "borewell", "excellent", 0.6),
    ("cashew", "Kharif", "laterite", 250, "rainfed", "good", 1.5),
    ("black_pepper", "Kharif", "laterite", 265, "rainfed", "good", 0.4),
    ("ginger", "Kharif", "laterite", 270, "rainfed", "average", 0.35),
    ("maize", "Rabi", "red_loam", 85, "borewell", "good", 1.0),
    ("jackfruit", "Kharif", "laterite", 240, "rainfed", "excellent", 0.8),
    ("rice", "Rabi", "alluvial", 80, "canal", "poor", 1.3),
    ("turmeric", "Kharif", "laterite", 258, "rainfed", "good", 0.45),
    ("cocoa", "Kharif", "laterite", 252, "rainfed", "average", 0.5),
    ("coconut", "Zaid", "coastal_sandy", 40, "tank", "good", 1.4),
    ("cowpea", "Zaid", "red_loam", 45, "open_well", "good", 0.5),
]
# per-row admin decisions: mostly approved, a few pending, one rejected, one without consent
SURVEY_STATUS = (["approved"] * 15) + ["pending", "pending", "approved", "rejected", "pending"]


def _wipe():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_users(db) -> dict[str, User]:
    users: dict[str, User] = {}
    for spec in USERS:
        user = User(name=spec["name"], email=spec["email"], role=spec["role"],
                    password_hash=generate_password_hash(spec["password"]),
                    phone=spec.get("phone"), village=spec.get("village"), taluk=spec.get("taluk"),
                    district=spec.get("district", "Dakshina Kannada"))
        db.add(user)
        users[spec["email"]] = user
    db.commit()
    return users


def seed_crop_reference(db) -> int:
    created = 0
    for key, kb in CROPS.items():
        if db.query(CropReference).filter(CropReference.crop_key == key).first():
            continue
        db.add(CropReference(
            crop_key=key, name=kb["en_name"], name_kn=kb.get("kn"), category=kb["category"],
            seasons_json=json.dumps(kb["seasons"]), soils_json=json.dumps(kb["soils"]),
            water_need=kb["water_need"], rainfall_min=kb["rainfall_monthly"][0],
            rainfall_max=kb["rainfall_monthly"][1], ph_min=kb["ph"][0], ph_max=kb["ph"][1],
            temp_min=kb["temp"][0], temp_max=kb["temp"][1], total_water_mm=kb["total_water_mm"],
            duration_days=kb.get("duration_days"), dk_local=bool(kb.get("dk_local")),
            in_model_label_space=key in MODEL_CROP_LABELS, note=kb.get("note"),
            source=kb.get("source"), source_url=kb.get("source_url"),
        ))
        created += 1
    db.commit()
    return created


def seed_predictions(db, users: dict[str, User]) -> list[Prediction]:
    farmers = [u for u in users.values() if u.role == "farmer"]
    rows: list[Prediction] = []
    for i, (soil, season, rainfall, source, taluk, village) in enumerate(PREDICTION_INPUTS):
        user = farmers[i % len(farmers)]
        result = registry.predict(soil_type=soil, season=season, rainfall_mm=rainfall,
                                  water_availability=WATER_LEVEL_BY_SOURCE[source],
                                  regional_tuning=True, db=db)
        top = result["recommendations"][0]
        created = NOW - timedelta(days=(len(PREDICTION_INPUTS) - i) * 3 - random.randint(0, 2),
                                  hours=random.randint(0, 20))
        row = Prediction(
            user_id=user.id, soil_type=soil, season=season, rainfall_mm=rainfall,
            water_availability=WATER_LEVEL_BY_SOURCE[source], irrigation_source=source,
            taluk=taluk, regional_tuning=True, top_crop=top["crop"],
            top_confidence=top["confidence"],
            results_json=json.dumps({"recommendations": result["recommendations"],
                                     "regional_advisory": result["regional_advisory"],
                                     "confidence_note": result["confidence_note"],
                                     "expansion_audit": result["expansion_audit"]}),
            model_key=result["model"]["key"], model_version=result["model"]["version"],
            created_at=created, updated_at=created,
            notes=random.choice([None, "Asked for advice before the monsoon sowing.",
                                 "Compared with the KVK advisory.", None,
                                 "Small plot trial planned."]),
        )
        db.add(row)
        db.flush()
        # outcome feedback on the first few rows (feedback loop demo)
        if i < len(FEEDBACK):
            row.actual_crop = top["crop"]
            row.yield_outcome = FEEDBACK[i]
            row.followed_advice = "yes" if i % 3 else "partly"
            row.feedback_notes = random.choice([
                "Yield was close to what the advice suggested.",
                "Followed the recommendation fully; monsoon was normal this year.",
                "Only partly followed it — cost of seed was high.",
            ])
            row.feedback_at = created + timedelta(days=45)
        rows.append(row)
    db.commit()
    _ = village
    return rows


def seed_surveys(db, users: dict[str, User]) -> list[SurveyEntry]:
    farmers = [u for u in users.values() if u.role == "farmer"]
    admin = next(u for u in users.values() if u.role == "admin")
    rows: list[SurveyEntry] = []
    for i, (crop, season, soil, rainfall, source, outcome, area) in enumerate(SURVEYS):
        farmer = farmers[i % len(farmers)]
        created = NOW - timedelta(days=(len(SURVEYS) - i) * 2 + random.randint(0, 3))
        status = SURVEY_STATUS[i] if i < len(SURVEY_STATUS) else "approved"
        consent = not (i == 17)          # one row deliberately lacks consent -> cleaning rule 1
        row = SurveyEntry(
            user_id=farmer.id, farmer_name=farmer.name, village=farmer.village or "Not recorded",
            taluk=farmer.taluk or "Mangaluru", phone=farmer.phone, soil_type=soil, season=season,
            rainfall_mm=float(rainfall), water_source=source,
            water_availability=WATER_LEVEL_BY_SOURCE[source], crop_grown=crop,
            yield_outcome=outcome, area_acres=area,
            notes=random.choice([None, "Recorded with KVK staff during a field visit.",
                                 "Own observation, plot near the river.", None,
                                 "Rain was late this year."]),
            consent=consent, status=status if consent else "pending",
            sample_weight=sample_weight_for(outcome), created_at=created, updated_at=created,
        )
        if status in ("approved", "rejected") and consent:
            row.reviewed_by = admin.id
            row.reviewed_at = created + timedelta(days=3)
            row.review_note = ("Verified with the farmer over phone." if status == "approved"
                               else "Rainfall figure looks like an annual total; ask for resubmission.")
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def seed_audit(db, users: dict[str, User], n_predictions: int, n_surveys: int) -> None:
    admin = next(u for u in users.values() if u.role == "admin")
    db.add_all([
        AuditLog(user_id=admin.id, action="seed", entity="system",
                 detail=f"Seeded {n_predictions} predictions, {n_surveys} survey rows, "
                        f"{len(CROPS)} crop reference rows",
                 created_at=NOW - timedelta(days=30)),
        AuditLog(user_id=admin.id, action="review:approved", entity="survey", entity_id="1",
                 detail="Verified with the farmer over phone.", created_at=NOW - timedelta(days=12)),
        AuditLog(user_id=admin.id, action="import", entity="crop_reference",
                 detail=f"{len(CROPS)} rows imported from the built-in knowledge base",
                 created_at=NOW - timedelta(days=29)),
    ])
    db.commit()


def main(force: bool = False) -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).count()
        if existing and not force:
            print(f"Database already has {existing} users — nothing to do. Use --force to reseed.")
            return 0
        if force and existing:
            db.close()
            print("Wiping existing tables (--force)…")
            _wipe()
            db = SessionLocal()

        print("Seeding users…")
        users = seed_users(db)
        print(f"  {len(users)} users (2 evaluator/admin + 6 farmers)")

        print("Importing crop reference data from the built-in knowledge base…")
        crops = seed_crop_reference(db)
        print(f"  {crops} crop reference rows")

        print("Generating prediction history through the real model…")
        preds = seed_predictions(db, users)
        print(f"  {len(preds)} predictions ({len(FEEDBACK)} with outcome feedback)")

        print("Adding primary survey entries…")
        surveys = seed_surveys(db, users)
        approved = sum(1 for s in surveys if s.status == "approved")
        print(f"  {len(surveys)} survey rows ({approved} approved, "
              f"{sum(1 for s in surveys if s.status == 'pending')} pending, "
              f"{sum(1 for s in surveys if s.status == 'rejected')} rejected)")

        seed_audit(db, users, len(preds), len(surveys))

        print("\nDemo logins")
        print("  Evaluator / admin : admin@cropadvisor.in / admin123")
        print("  Second admin      : evaluator@cropadvisor.in / evaluator123")
        print("  Farmer            : ravi@example.com / farmer123")
        print("\nSeed complete.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Crop Advisor demo database")
    parser.add_argument("--force", action="store_true", help="drop and recreate all tables first")
    args = parser.parse_args()
    sys.exit(main(force=args.force))
