"""Dashboard summary + /health for uptime checks on Render."""

from __future__ import annotations

import os
import time

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from ..config import Config
from ..db import SessionLocal, engine
from ..ml.knowledge import MODEL_CROP_LABELS
from ..ml.registry import registry
from ..models import CropReference, Prediction, SurveyEntry, User
from .utils import auth_required, current_user

bp = Blueprint("summary", __name__)
BOOT_TIME = time.time()

# District reference figures, quoted from the sources cited on the About page.
DISTRICT_REFERENCE = {
    "district": "Dakshina Kannada, Karnataka",
    "rainfall_normal_annual_mm": 4040,
    "rainfall_2023_actual_mm": 3318.3,
    "rainfall_note": "Normal rainfall ~4040 mm; heavy June-September monsoon (KVK Dakshina Kannada).",
    "dominant_soils": "red lateritic (~60%), laterite, alluvial, coastal sandy",
    "soil_ph_range": "4.6 - 5.8",
    "major_crops": ["Paddy/Rice", "Arecanut", "Coconut", "Cashew", "Black pepper", "Cocoa",
                    "Banana", "Rubber"],
    "crop_areas_2022_23": {"paddy_ha": 48689, "arecanut_ha": 35409, "coconut_ha": 18467},
    "paddy_productivity_kg_ha": 2735,
    "sources": ["https://www.kvkdk.org/district_profile.html",
                "https://kvkdk.org/reports/annual_report/2023.pdf",
                "https://www.kscst.org.in/nrdms_files/dnrdms_files/02_dakshina_kannada/"],
}


@bp.get("/api/summary")
@auth_required()
def summary():
    user = current_user()
    db = SessionLocal()
    try:
        is_admin = user.role == "admin"
        scope_all = is_admin and request.args.get("scope", "all") == "all"

        pq = db.query(Prediction) if scope_all else db.query(Prediction).filter(Prediction.user_id == user.id)
        sq = db.query(SurveyEntry) if scope_all else db.query(SurveyEntry).filter(SurveyEntry.user_id == user.id)
        predictions = pq.order_by(Prediction.created_at.desc()).all()
        surveys_count = sq.count()

        by_crop: dict[str, int] = {}
        for p in predictions:
            by_crop[p.top_crop] = by_crop.get(p.top_crop, 0) + 1
        by_season: dict[str, int] = {}
        for p in predictions:
            by_season[p.season] = by_season.get(p.season, 0) + 1

        latest = db.query(Prediction).order_by(Prediction.created_at.desc()).limit(5).all()
        latest_surveys = db.query(SurveyEntry).order_by(SurveyEntry.created_at.desc()).limit(5).all()
        metrics = registry.metrics() or {}

        return jsonify({
            "scope": "all users" if scope_all else "my activity",
            "role": user.role,
            "cards": {
                "predictions": len(predictions),
                "predictions_with_feedback": sum(1 for p in predictions if p.actual_crop),
                "survey_entries": surveys_count,
                "approved_survey_rows": sq.filter(SurveyEntry.status == "approved").count(),
                "pending_review": (db.query(SurveyEntry).filter(SurveyEntry.status == "pending").count()
                                   if is_admin else None),
                "farmers": db.query(User).filter(User.role == "farmer").count() if is_admin else None,
                "crop_reference_rows": db.query(CropReference).count(),
                "secondary_dataset_rows": metrics.get("dataset", {}).get("secondary_rows_used", 2200),
                "primary_rows_in_training": metrics.get("dataset", {}).get("primary_rows_used", 0),
                "model_crops": len(MODEL_CROP_LABELS),
            },
            "model": {
                "key": metrics.get("best_model", {}).get("key"),
                "label": metrics.get("best_model", {}).get("label"),
                "test_accuracy": metrics.get("best_model", {}).get("metrics", {}).get("test_accuracy"),
                "top3_accuracy": metrics.get("best_model", {}).get("metrics", {}).get("top3_accuracy"),
                "cv_macro_f1": metrics.get("best_model", {}).get("metrics", {}).get("cv_macro_f1_mean"),
                "trained_at": metrics.get("trained_at"),
                "model_size_kb": metrics.get("artifacts", {}).get("model_size_kb"),
                "ablation_accuracy": metrics.get("ablation_four_inputs", {}).get("best", {}).get("test_accuracy"),
            },
            "top_crops": sorted([{"crop": k, "count": v} for k, v in by_crop.items()],
                                key=lambda d: -d["count"])[:8],
            "by_season": [{"season": k, "count": v} for k, v in by_season.items()],
            "recent_predictions": [p.to_dict() for p in latest],
            "recent_surveys": [s.to_dict() for s in latest_surveys],
            "district_reference": DISTRICT_REFERENCE,
        })
    finally:
        db.close()


@bp.get("/health")
def health():
    """Uptime/health probe for Render. Never touches the model unless it is already loaded."""
    db_ok, db_error = True, None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok, db_error = False, str(exc)
    status = registry.status()
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "app": Config.APP_NAME,
        "version": Config.APP_VERSION,
        "environment": os.getenv("RENDER") and "render" or os.getenv("FLASK_ENV", "development"),
        "uptime_seconds": round(time.time() - BOOT_TIME, 1),
        "database": {"connected": db_ok, "error": db_error,
                     "engine": engine.dialect.name,
                     "persistent": engine.dialect.name != "sqlite"},
        "model": {"loaded": status["loaded"], "lazy": True, "key": status["model_key"],
                  "version": status["model_version"], "trained_at": status["trained_at"],
                  "size_kb": status["model_size_kb"]},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }), (200 if db_ok else 503)
