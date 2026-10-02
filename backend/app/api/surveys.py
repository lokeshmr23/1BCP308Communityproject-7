"""Primary dataset survey CRUD + admin review workflow (approve / reject / merge preview)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from ..cleaning import (CLEANING_RULES, clean_training_rows, sample_weight_for,
                        validate_survey_payload)
from ..db import SessionLocal
from ..models import SurveyEntry
from .utils import (audit, auth_required, bad_request, body, current_user, not_found,
                    pagination, require_fields)

bp = Blueprint("surveys", __name__, url_prefix="/api/surveys")


@bp.get("")
@auth_required()
def list_surveys():
    user = current_user()
    limit, offset = pagination(20)
    db = SessionLocal()
    try:
        q = db.query(SurveyEntry)
        scope = request.args.get("scope", "mine")
        if user.role == "admin" and scope == "all":
            pass
        else:
            q = q.filter(SurveyEntry.user_id == user.id)
        if request.args.get("status"):
            q = q.filter(SurveyEntry.status == request.args["status"])
        if request.args.get("taluk"):
            q = q.filter(SurveyEntry.taluk == request.args["taluk"])
        if request.args.get("crop"):
            q = q.filter(SurveyEntry.crop_grown == request.args["crop"])
        if request.args.get("search"):
            like = f"%{request.args['search']}%"
            q = q.filter(SurveyEntry.village.ilike(like) | SurveyEntry.farmer_name.ilike(like))
        total = q.count()
        rows = q.order_by(SurveyEntry.created_at.desc()).offset(offset).limit(limit).all()
        return jsonify({
            "total": total, "limit": limit, "offset": offset, "scope": scope,
            "counts": {
                "pending": db.query(SurveyEntry).filter(SurveyEntry.status == "pending").count()
                if user.role == "admin" else None,
                "approved": db.query(SurveyEntry).filter(SurveyEntry.status == "approved").count(),
                "rejected": db.query(SurveyEntry).filter(SurveyEntry.status == "rejected").count(),
            },
            "items": [r.to_dict() for r in rows],
        })
    finally:
        db.close()


@bp.post("")
@auth_required()
def create_survey():
    data = body()
    user = current_user()
    require_fields(data, ["farmer_name", "village", "taluk", "soil_type", "season",
                          "rainfall_mm", "water_source", "crop_grown", "yield_outcome"])
    norm, errors = validate_survey_payload(data)
    if errors:
        bad_request("The survey entry did not pass the data-cleaning rules", details=errors,
                    code="cleaning_rules_failed")

    db = SessionLocal()
    try:
        dup = (db.query(SurveyEntry)
               .filter(SurveyEntry.user_id == user.id, SurveyEntry.village == norm["village"],
                       SurveyEntry.season == norm["season"], SurveyEntry.crop_grown == norm["crop_grown"],
                       SurveyEntry.rainfall_mm == norm["rainfall_mm"]).first())
        if dup and not data.get("force"):
            return jsonify({"duplicate_of": dup.id, "item": dup.to_dict(),
                            "message": "An identical entry already exists for this village/season/crop "
                                       "(cleaning rule 6). Resubmit with force=true to keep both."}), 409

        row = SurveyEntry(user_id=user.id, **norm,
                          sample_weight=sample_weight_for(norm["yield_outcome"]),
                          status="approved" if user.role == "admin" and data.get("approve_now") else "pending")
        db.add(row)
        db.commit()
        audit(db, user, "create", "survey", row.id,
              detail=f"{norm['village']}/{norm['crop_grown']} ({norm['yield_outcome']})")
        db.commit()
        return jsonify({
            "item": row.to_dict(),
            "message": ("Survey saved and auto-approved (admin submission)." if row.status == "approved"
                        else "Survey saved as pending review. An admin/evaluator will approve it before "
                             "it is merged into the training data."),
            "rules_applied": [r for r in CLEANING_RULES if r["id"] in (1, 2, 3, 4, 5, 6, 10)],
        }), 201
    finally:
        db.close()


def _get_row(db, user, row_id: int) -> SurveyEntry:
    row = db.get(SurveyEntry, row_id)
    if not row:
        not_found("Survey entry not found")
    if user.role != "admin" and row.user_id != user.id:
        not_found("Survey entry not found")
    return row


@bp.get("/<int:row_id>")
@auth_required()
def get_survey(row_id: int):
    user = current_user()
    db = SessionLocal()
    try:
        return jsonify({"item": _get_row(db, user, row_id).to_dict()})
    finally:
        db.close()


@bp.put("/<int:row_id>")
@bp.patch("/<int:row_id>")
@auth_required()
def update_survey(row_id: int):
    data = body()
    user = current_user()
    db = SessionLocal()
    try:
        row = _get_row(db, user, row_id)
        merged = {**row.to_dict(), **data}
        norm, errors = validate_survey_payload(merged)
        if errors:
            bad_request("The updated entry did not pass the data-cleaning rules", details=errors,
                        code="cleaning_rules_failed")
        for field, value in norm.items():
            setattr(row, field, value)
        row.sample_weight = sample_weight_for(norm["yield_outcome"])
        # an edited row must be re-reviewed: the data it was approved on has changed
        if user.role != "admin":
            row.status = "pending"
        audit(db, user, "update", "survey", row.id)
        db.commit()
        return jsonify({"item": row.to_dict(),
                        "message": "Survey updated" + ("" if user.role == "admin"
                                                       else " and sent back for review")})
    finally:
        db.close()


@bp.delete("/<int:row_id>")
@auth_required()
def delete_survey(row_id: int):
    user = current_user()
    db = SessionLocal()
    try:
        row = _get_row(db, user, row_id)
        audit(db, user, "delete", "survey", row.id)
        db.delete(row)
        db.commit()
        return jsonify({"deleted": row_id, "message": "Survey entry deleted"})
    finally:
        db.close()


@bp.post("/<int:row_id>/review")
@auth_required(role="admin")
def review_survey(row_id: int):
    data = body()
    decision = (data.get("status") or "").lower()
    if decision not in ("approved", "rejected", "pending"):
        bad_request("status must be approved, rejected or pending", code="invalid_status")
    user = current_user()
    db = SessionLocal()
    try:
        row = db.get(SurveyEntry, row_id)
        if not row:
            not_found("Survey entry not found")
        row.status = decision
        row.reviewed_by = user.id
        row.reviewed_at = datetime.now(timezone.utc)
        row.review_note = data.get("review_note")
        audit(db, user, f"review:{decision}", "survey", row.id, detail=row.review_note)
        db.commit()
        return jsonify({"item": row.to_dict(), "message": f"Survey {decision}"})
    finally:
        db.close()


@bp.get("/review-queue")
@auth_required(role="admin")
def review_queue():
    limit, offset = pagination(20)
    db = SessionLocal()
    try:
        q = db.query(SurveyEntry).filter(SurveyEntry.status == "pending")
        rows = q.order_by(SurveyEntry.created_at.asc()).offset(offset).limit(limit).all()
        return jsonify({"total": q.count(), "items": [r.to_dict() for r in rows]})
    finally:
        db.close()


@bp.get("/export")
@auth_required()
def export_surveys():
    user = current_user()
    db = SessionLocal()
    try:
        q = db.query(SurveyEntry)
        if not (user.role == "admin" and request.args.get("scope") == "all"):
            q = q.filter(SurveyEntry.user_id == user.id)
        rows = q.order_by(SurveyEntry.id).all()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "created_at", "farmer_name", "village", "taluk", "soil_type", "season",
                    "rainfall_mm", "water_source", "water_availability", "crop_grown", "yield_outcome",
                    "area_acres", "consent", "status", "sample_weight", "notes"])
        for r in rows:
            w.writerow([r.id, r.created_at, r.farmer_name, r.village, r.taluk, r.soil_type,
                        r.season, r.rainfall_mm, r.water_source, r.water_availability, r.crop_grown,
                        r.yield_outcome, r.area_acres, r.consent, r.status, r.sample_weight, r.notes])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=primary_survey_data.csv"})
    finally:
        db.close()


@bp.get("/cleaning-report")
@auth_required(role="admin")
def cleaning_report():
    """Show exactly which approved rows would be merged, and which get dropped, and why."""
    db = SessionLocal()
    try:
        approved = [r.to_dict() | {"status": r.status, "consent": r.consent}
                    for r in db.query(SurveyEntry).filter(SurveyEntry.status == "approved").all()]
        accepted, dropped = clean_training_rows(approved)
        return jsonify({
            "approved_rows": len(approved),
            "rows_merging_now": len(accepted),
            "rows_dropped": len(dropped),
            "rules": CLEANING_RULES,
            "accepted_preview": accepted[:25],
            "dropped": dropped[:25],
            "note": ("Rows with a 'poor' yield outcome are deliberately excluded from training: a crop "
                     "that failed is not evidence that the crop suits that soil/season/water profile. "
                     "Rows with an 'average' outcome enter with sample_weight 0.5."),
        })
    finally:
        db.close()
