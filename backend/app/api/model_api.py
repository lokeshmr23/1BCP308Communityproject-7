"""Model endpoints: metrics for the Model Performance page, status, and admin retrain."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from ..cleaning import clean_training_rows
from ..config import Config
from ..db import SessionLocal
from ..ml.registry import registry
from ..ml.train import default_paths, train_and_save
from ..models import Prediction, SurveyEntry
from .utils import audit, auth_required, current_user

bp = Blueprint("model_api", __name__, url_prefix="/api/model")

_RETRAIN = {"running": False, "started_at": None, "finished_at": None, "ok": None,
            "message": "No retrain has been run in this instance yet.", "result": None}
_RETRAIN_LOCK = threading.Lock()


@bp.get("/metrics")
def metrics():
    data = registry.metrics()
    if not data:
        return jsonify({"error": {"code": "metrics_missing",
                                  "message": "metrics.json not found — run `python -m app.ml.train` "
                                             "in the backend directory (or call the retrain endpoint)."}}), 503
    return jsonify(data)


@bp.get("/status")
def status():
    db = SessionLocal()
    try:
        pending = db.query(SurveyEntry).filter(SurveyEntry.status == "pending").count()
        approved = db.query(SurveyEntry).filter(SurveyEntry.status == "approved").count()
        predictions = db.query(Prediction).count()
    finally:
        db.close()
    return jsonify({
        "registry": registry.status(),
        "primary_data": {"approved_survey_rows": approved, "pending_survey_rows": pending,
                         "predictions_logged": predictions},
        "retrain": {k: v for k, v in _RETRAIN.items() if k != "result"},
        "cold_start_note": ("The model is lazy-loaded on the first prediction; the artefact is ~0.7 MB "
                            "and is committed to the repository, because Render's free disk is "
                            "ephemeral."),
    })


@bp.get("/feature-importance")
def feature_importance():
    data = registry.metrics() or {}
    fi = data.get("feature_importance")
    if not fi:
        return jsonify({"error": {"code": "metrics_missing", "message": "Train the model first."}}), 503
    whatif = [
        {"feature": "rainfall", "why": "Driest lever in the app — try 60 vs 220 mm in the Recommend form."},
        {"feature": "humidity", "why": "Season proxy (Kharif 88% RH vs Zaid 55% RH)."},
        {"feature": "K", "why": "Potassium — laterite (K 55) vs coastal sandy (K 18) profiles differ most."},
        {"feature": "P", "why": "Phosphorus — alluvial/red loam profiles carry higher P."},
        {"feature": "N", "why": "Nitrogen — alluvial profile is N 100, laterite N 30."},
    ]
    return jsonify({"feature_importance": fi, "sensitivity_hints": whatif,
                    "global": data.get("best_model", {}).get("metrics", {}),
                    "ablation_note": "See ablation_four_inputs in /api/model/metrics for the "
                                     "4-input-only comparison."})


def _run_retrain(include_surveys: bool, user_id: int | None):
    try:
        primary_rows, dropped = [], []
        if include_surveys:
            db = SessionLocal()
            try:
                approved = [r.to_dict() | {"consent": r.consent, "status": r.status}
                            for r in db.query(SurveyEntry)
                            .filter(SurveyEntry.status == "approved").all()]
            finally:
                db.close()
            primary_rows, dropped = clean_training_rows(approved)

        secondary, out_dir, derived = default_paths()
        m = train_and_save(secondary, out_dir, primary_rows=primary_rows, derived_out=derived)
        registry.load(force=True)
        registry.invalidate_kb_cache()
        with _RETRAIN_LOCK:
            _RETRAIN.update({
                "running": False, "ok": True, "finished_at": datetime.now(timezone.utc).isoformat(),
                "message": (f"Retrained on {m['dataset']['rows_total']} rows "
                            f"({m['dataset']['primary_rows_used']} from the primary survey, "
                            f"{len(dropped)} survey rows excluded by the cleaning rules). "
                            f"Best model: {m['best_model']['label']} "
                            f"(test accuracy {m['best_model']['metrics']['test_accuracy']:.4f})."),
                "result": {
                    "best_model": m["best_model"]["key"],
                    "accuracy": m["best_model"]["metrics"]["test_accuracy"],
                    "cv_macro_f1": m["best_model"]["metrics"]["cv_macro_f1_mean"],
                    "top3_accuracy": m["best_model"]["metrics"]["top3_accuracy"],
                    "rows_total": m["dataset"]["rows_total"],
                    "primary_rows_used": m["dataset"]["primary_rows_used"],
                    "rows_excluded_by_cleaning": len(dropped),
                    "external_check": m["external_check"],
                },
            })
    except Exception as exc:  # pragma: no cover
        with _RETRAIN_LOCK:
            _RETRAIN.update({"running": False, "ok": False,
                             "finished_at": datetime.now(timezone.utc).isoformat(),
                             "message": f"Retrain failed: {exc}", "result": None})


@bp.post("/retrain")
@auth_required(role="admin")
def retrain():
    """Feedback loop: merge approved primary survey rows and retrain all four models.

    Runs in a background thread (a Render free instance has a 30 s request timeout), and
    reports progress through /api/model/retrain/status.

    IMPORTANT: the retrained artefact is written to the container's ephemeral disk. It
    affects THIS running instance only — a redeploy restores the committed model. Download
    /api/model/metrics afterwards if you want to keep the numbers for your report.
    """
    data = request.get_json(silent=True) or {}
    include = bool(data.get("include_primary_surveys", True))
    user = current_user()
    with _RETRAIN_LOCK:
        if _RETRAIN["running"]:
            return jsonify({"error": {"code": "already_running",
                                      "message": "A retrain is already running."}}), 409
        _RETRAIN.update({"running": True, "ok": None, "started_at": datetime.now(timezone.utc).isoformat(),
                         "finished_at": None, "result": None,
                         "message": "Training Decision Tree, Random Forest, KNN and Naive Bayes "
                                    "with a stratified split + 5-fold CV…"})
    threading.Thread(target=_run_retrain, args=(include, user.id), daemon=True).start()
    db = SessionLocal()
    try:
        audit(db, user, "retrain", "model", detail=f"include_primary_surveys={include}")
        db.commit()
    finally:
        db.close()
    return jsonify({"started": True, "status_url": "/api/model/retrain/status",
                    "include_primary_surveys": include,
                    "poll_after_seconds": 5}), 202


@bp.get("/retrain/status")
def retrain_status():
    with _RETRAIN_LOCK:
        return jsonify({k: v for k, v in _RETRAIN.items()})
