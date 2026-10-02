"""Prediction history: full CRUD + the outcome feedback loop."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from ..cleaning import WATER_LEVEL_BY_SOURCE, sample_weight_for, validate_survey_payload
from ..db import SessionLocal
from ..ml.registry import registry
from ..models import Prediction, SurveyEntry
from .utils import (audit, auth_required, bad_request, body, current_user, not_found,
                    pagination, require_fields)

bp = Blueprint("history", __name__, url_prefix="/api/history")

WRITE_FIELDS = ("notes", "actual_crop", "yield_outcome", "followed_advice")


@bp.get("")
@auth_required()
def list_history():
    user = current_user()
    limit, offset = pagination(20)
    db = SessionLocal()
    try:
        q = db.query(Prediction)
        scope = request.args.get("scope", "mine")
        if user.role == "admin" and scope == "all":
            pass
        else:
            q = q.filter(Prediction.user_id == user.id)
        if request.args.get("crop"):
            q = q.filter(Prediction.top_crop == request.args["crop"])
        if request.args.get("season"):
            q = q.filter(Prediction.season == request.args["season"])
        if request.args.get("with_feedback") == "1":
            q = q.filter(Prediction.actual_crop.isnot(None))
        total = q.count()
        rows = q.order_by(Prediction.created_at.desc()).offset(offset).limit(limit).all()
        return jsonify({"total": total, "limit": limit, "offset": offset, "scope": scope,
                        "items": [r.to_dict() for r in rows]})
    finally:
        db.close()


@bp.get("/summary")
@auth_required()
def history_summary():
    """Small aggregate block used by the dashboard and the history page header."""
    user = current_user()
    db = SessionLocal()
    try:
        q = db.query(Prediction)
        if not (user.role == "admin" and request.args.get("scope") == "all"):
            q = q.filter(Prediction.user_id == user.id)
        rows = q.all()
        by_crop: dict[str, int] = {}
        for r in rows:
            by_crop[r.top_crop] = by_crop.get(r.top_crop, 0) + 1
        outcomes = {}
        for r in rows:
            if r.yield_outcome:
                outcomes[r.yield_outcome] = outcomes.get(r.yield_outcome, 0) + 1
        return jsonify({
            "total": len(rows),
            "with_feedback": sum(1 for r in rows if r.actual_crop),
            "advice_followed": sum(1 for r in rows if r.followed_advice == "yes"),
            "top_crops": sorted([{"crop": k, "count": v} for k, v in by_crop.items()],
                                key=lambda d: -d["count"])[:8],
            "outcomes": outcomes,
            "avg_confidence": round(sum(r.top_confidence for r in rows) / len(rows), 4) if rows else None,
        })
    finally:
        db.close()


@bp.get("/export")
@auth_required()
def export_history():
    user = current_user()
    db = SessionLocal()
    try:
        q = db.query(Prediction)
        if not (user.role == "admin" and request.args.get("scope") == "all"):
            q = q.filter(Prediction.user_id == user.id)
        rows = q.order_by(Prediction.created_at.desc()).all()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "created_at", "soil_type", "season", "rainfall_mm", "water_availability",
                    "irrigation_source", "taluk", "top_crop", "top_confidence", "model_key",
                    "actual_crop", "yield_outcome", "followed_advice", "notes"])
        for r in rows:
            w.writerow([r.id, r.created_at, r.soil_type, r.season, r.rainfall_mm,
                        r.water_availability, r.irrigation_source, r.taluk, r.top_crop,
                        r.top_confidence, r.model_key, r.actual_crop, r.yield_outcome,
                        r.followed_advice, r.notes])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=prediction_history.csv"})
    finally:
        db.close()


def _get_row(db, user, row_id: int) -> Prediction:
    row = db.get(Prediction, row_id)
    if not row:
        not_found("Prediction not found")
    if user.role != "admin" and row.user_id != user.id:
        not_found("Prediction not found")      # do not leak other users' rows
    return row


@bp.get("/<int:row_id>")
@auth_required()
def get_one(row_id: int):
    user = current_user()
    db = SessionLocal()
    try:
        return jsonify({"item": _get_row(db, user, row_id).to_dict()})
    finally:
        db.close()


@bp.post("")
@auth_required()
def create_from_payload():
    """Save a recommendation by re-running it server-side (never trust client numbers)."""
    data = body()
    user = current_user()
    require_fields(data, ["soil_type", "season", "rainfall_mm", "water_availability"])
    db = SessionLocal()
    try:
        result = registry.predict(
            soil_type=data["soil_type"], season=data["season"], rainfall_mm=float(data["rainfall_mm"]),
            water_availability=data["water_availability"],
            regional_tuning=bool(data.get("regional_tuning", True)), db=db)
        top = result["recommendations"][0]
        row = Prediction(
            user_id=user.id, soil_type=data["soil_type"], season=data["season"],
            rainfall_mm=float(data["rainfall_mm"]), water_availability=data["water_availability"],
            irrigation_source=data.get("irrigation_source"), taluk=data.get("taluk"),
            regional_tuning=bool(data.get("regional_tuning", True)), top_crop=top["crop"],
            top_confidence=top["confidence"],
            results_json=json.dumps({"recommendations": result["recommendations"],
                                     "regional_advisory": result["regional_advisory"],
                                     "confidence_note": result["confidence_note"],
                                     "expansion_audit": result["expansion_audit"]}),
            model_key=result["model"]["key"], model_version=result["model"]["version"],
            notes=data.get("notes"))
        db.add(row)
        db.commit()
        return jsonify({"item": row.to_dict(), "recommendation": result}), 201
    finally:
        db.close()


@bp.patch("/<int:row_id>")
@auth_required()
def update_row(row_id: int):
    data = body()
    user = current_user()
    db = SessionLocal()
    try:
        row = _get_row(db, user, row_id)
        for field in WRITE_FIELDS:
            if field in data:
                setattr(row, field, data[field] or None)
        if row.yield_outcome and not row.feedback_at:
            row.feedback_at = datetime.now(timezone.utc)
        audit(db, user, "update", "prediction", row.id)
        db.commit()
        return jsonify({"item": row.to_dict()})
    finally:
        db.close()


@bp.delete("/<int:row_id>")
@auth_required()
def delete_row(row_id: int):
    user = current_user()
    db = SessionLocal()
    try:
        row = _get_row(db, user, row_id)
        audit(db, user, "delete", "prediction", row.id, detail=f"top_crop={row.top_crop}")
        db.delete(row)
        db.commit()
        return jsonify({"deleted": row_id, "message": "Prediction deleted"})
    finally:
        db.close()


@bp.post("/<int:row_id>/feedback")
@auth_required()
def submit_feedback(row_id: int):
    """FEEDBACK LOOP.

    A farmer reports what they actually grew and how it turned out. The prediction row is
    updated, and - when the consent box is ticked - the same observation is written into the
    primary survey table so the next retrain can learn from it.
    """
    data = body()
    user = current_user()
    db = SessionLocal()
    try:
        row = _get_row(db, user, row_id)
        row.actual_crop = (data.get("actual_crop") or row.top_crop).strip().lower().replace(" ", "_")
        row.yield_outcome = data.get("yield_outcome")
        row.followed_advice = data.get("followed_advice")
        row.feedback_notes = data.get("feedback_notes")
        row.feedback_at = datetime.now(timezone.utc)
        if row.yield_outcome not in ("poor", "average", "good", "excellent"):
            bad_request("yield_outcome must be one of: poor, average, good, excellent",
                        code="invalid_yield_outcome")

        created_survey = None
        if data.get("add_to_dataset"):
            payload = {
                "farmer_name": user.name, "village": data.get("village") or user.village or "Not recorded",
                "taluk": data.get("taluk") or row.taluk or user.taluk or "Mangaluru",
                "phone": user.phone, "soil_type": row.soil_type, "season": row.season,
                "rainfall_mm": row.rainfall_mm,
                "water_source": row.irrigation_source or ("rainfed" if row.water_availability == "low"
                                                          else "borewell" if row.water_availability == "medium"
                                                          else "canal"),
                "crop_grown": row.actual_crop, "yield_outcome": row.yield_outcome,
                "area_acres": data.get("area_acres"), "notes": data.get("feedback_notes"),
                "consent": bool(data.get("consent")),
            }
            norm, errors = validate_survey_payload(payload)
            if errors:
                bad_request("Could not add this outcome to the primary dataset", details=errors,
                            code="survey_rejected")
            survey = SurveyEntry(user_id=user.id, **norm,
                                 sample_weight=sample_weight_for(norm["yield_outcome"]),
                                 status="pending")
            db.add(survey)
            db.flush()
            created_survey = survey.to_dict()

        audit(db, user, "feedback", "prediction", row.id,
              detail=f"actual={row.actual_crop}, outcome={row.yield_outcome}")
        db.commit()
        return jsonify({
            "item": row.to_dict(),
            "created_survey": created_survey,
            "loop_message": ("Thanks — this outcome is now recorded. "
                             + ("An admin/evaluator will review the survey row before it is merged "
                                "into the training set." if created_survey else
                                "Tick the consent box to also contribute it to the primary dataset.")),
        }), 201
    finally:
        db.close()
