"""Crop reference data: full CRUD (admin writes) that also feeds the recommendation rules."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from .. import constants
from ..db import SessionLocal
from ..ml.knowledge import CROPS, MODEL_CROP_LABELS, kb_summary
from ..ml.registry import registry
from ..models import CropReference
from .utils import (audit, auth_required, bad_request, body, current_user, not_found,
                    pagination, require_fields)

bp = Blueprint("crops", __name__, url_prefix="/api/crops")

VALID_WATER = {w["value"] for w in constants.WATER_LEVELS}
VALID_SEASON = {s["value"] for s in constants.SEASONS}
VALID_SOIL = {s["value"] for s in constants.SOIL_TYPES}


def _validate(data: dict, partial: bool = False) -> dict:
    out: dict = {}
    if not partial:
        require_fields(data, ["crop_key", "name"])
    if "crop_key" in data:
        out["crop_key"] = str(data["crop_key"]).strip().lower().replace(" ", "_")
    if "name" in data:
        out["name"] = data["name"].strip()
    for field in ("name_kn", "category", "water_need", "total_water_mm", "note", "source", "source_url"):
        if field in data:
            out[field] = data[field]
    if "water_need" in data and data["water_need"] not in VALID_WATER:
        bad_request(f"water_need must be one of {sorted(VALID_WATER)}", code="invalid_water_need")
    for field, key in (("seasons", "seasons_json"), ("soils", "soils_json")):
        if field in data:
            values = data[field]
            if not isinstance(values, list):
                bad_request(f"{field} must be a list", code=f"invalid_{field}")
            if field == "seasons":
                bad = [v for v in values if v not in VALID_SEASON]
                if bad:
                    bad_request(f"invalid seasons: {bad} (allowed: {sorted(VALID_SEASON)})",
                                code="invalid_seasons")
            out[key] = json.dumps(values)
    if "soils" in data:
        bad = [v for v in data["soils"] if v not in VALID_SOIL]
        if bad:
            bad_request(f"invalid soils: {bad} (allowed: {sorted(VALID_SOIL)})", code="invalid_soils")
    for field in ("dk_local", "in_model_label_space", "is_active"):
        if field in data:
            out[field] = bool(data[field])
    for field in ("rainfall_min", "rainfall_max", "ph_min", "ph_max", "temp_min", "temp_max"):
        if field in data:
            try:
                out[field] = float(data[field])
            except (TypeError, ValueError):
                bad_request(f"{field} must be a number", code="invalid_number")
    if "duration_days" in data and data["duration_days"] is not None:
        try:
            out["duration_days"] = int(data["duration_days"])
        except (TypeError, ValueError):
            bad_request("duration_days must be an integer", code="invalid_number")
    if out.get("rainfall_min") is not None and out.get("rainfall_max") is not None:
        if out["rainfall_min"] >= out["rainfall_max"]:
            bad_request("rainfall_min must be smaller than rainfall_max", code="invalid_range")
    return out


@bp.get("")
def list_crops():
    limit, offset = pagination(100)
    db = SessionLocal()
    try:
        q = db.query(CropReference)
        if request.args.get("category"):
            q = q.filter(CropReference.category == request.args["category"])
        if request.args.get("dk_local") == "1":
            q = q.filter(CropReference.dk_local.is_(True))
        if request.args.get("search"):
            like = f"%{request.args['search']}%"
            q = q.filter(CropReference.name.ilike(like) | CropReference.crop_key.ilike(like))
        total = q.count()
        rows = q.order_by(CropReference.name).offset(offset).limit(limit).all()
        if total == 0:
            # Empty state: offer to import the built-in knowledge base.
            return jsonify({"total": 0, "items": [], "hint":
                            "No crop reference rows yet. POST /api/crops/import-defaults "
                            "(admin) to load the built-in, cited knowledge base.",
                            "builtin_count": len(CROPS)})
        return jsonify({"total": total, "limit": limit, "offset": offset,
                        "items": [r.to_dict() for r in rows]})
    finally:
        db.close()


@bp.post("")
@auth_required(role="admin")
def create_crop():
    data = _validate(body())
    user = current_user()
    db = SessionLocal()
    try:
        if db.query(CropReference).filter(CropReference.crop_key == data["crop_key"]).first():
            bad_request("A crop with this crop_key already exists", code="duplicate_crop_key")
        row = CropReference(**data)
        row.in_model_label_space = data.get("crop_key") in MODEL_CROP_LABELS \
            if "in_model_label_space" not in data else data["in_model_label_space"]
        db.add(row)
        db.commit()
        registry.invalidate_kb_cache()
        audit(db, user, "create", "crop_reference", row.id, detail=row.crop_key)
        db.commit()
        return jsonify({"item": row.to_dict(),
                        "note": "This entry now overrides the built-in knowledge base for the "
                                "rule-fit part of the recommendation score."}), 201
    finally:
        db.close()


@bp.get("/<int:crop_id>")
def get_crop(crop_id: int):
    db = SessionLocal()
    try:
        row = db.get(CropReference, crop_id)
        if not row:
            not_found("Crop reference not found")
        return jsonify({"item": row.to_dict()})
    finally:
        db.close()


@bp.put("/<int:crop_id>")
@bp.patch("/<int:crop_id>")
@auth_required(role="admin")
def update_crop(crop_id: int):
    data = _validate(body(), partial=True)
    user = current_user()
    db = SessionLocal()
    try:
        row = db.get(CropReference, crop_id)
        if not row:
            not_found("Crop reference not found")
        for k, v in data.items():
            setattr(row, k, v)
        db.commit()
        registry.invalidate_kb_cache()
        audit(db, user, "update", "crop_reference", row.id, detail=row.crop_key)
        db.commit()
        return jsonify({"item": row.to_dict()})
    finally:
        db.close()


@bp.delete("/<int:crop_id>")
@auth_required(role="admin")
def delete_crop(crop_id: int):
    user = current_user()
    db = SessionLocal()
    try:
        row = db.get(CropReference, crop_id)
        if not row:
            not_found("Crop reference not found")
        key = row.crop_key
        db.delete(row)
        db.commit()
        registry.invalidate_kb_cache()
        audit(db, user, "delete", "crop_reference", crop_id, detail=key)
        db.commit()
        return jsonify({"deleted": crop_id, "message":
                        f"Crop '{key}' deleted — the built-in knowledge base entry applies again."})
    finally:
        db.close()


@bp.post("/import-defaults")
@auth_required(role="admin")
def import_defaults():
    """Copy the built-in cited knowledge base into the editable table (idempotent)."""
    user = current_user()
    db = SessionLocal()
    try:
        created = 0
        for key, kb in CROPS.items():
            if db.query(CropReference).filter(CropReference.crop_key == key).first():
                continue
            row = CropReference(
                crop_key=key, name=kb["en_name"], name_kn=kb.get("kn"), category=kb["category"],
                seasons_json=json.dumps(kb["seasons"]), soils_json=json.dumps(kb["soils"]),
                water_need=kb["water_need"], rainfall_min=kb["rainfall_monthly"][0],
                rainfall_max=kb["rainfall_monthly"][1], ph_min=kb["ph"][0], ph_max=kb["ph"][1],
                temp_min=kb["temp"][0], temp_max=kb["temp"][1], total_water_mm=kb["total_water_mm"],
                duration_days=kb.get("duration_days"), dk_local=bool(kb.get("dk_local")),
                in_model_label_space=key in MODEL_CROP_LABELS, note=kb.get("note"),
                source=kb.get("source"), source_url=kb.get("source_url"),
            )
            db.add(row)
            created += 1
        db.commit()
        registry.invalidate_kb_cache()
        audit(db, user, "import", "crop_reference", detail=f"{created} rows")
        db.commit()
        return jsonify({"created": created, "total_builtin": len(CROPS),
                        "message": f"Imported {created} crop rows from the built-in knowledge base."})
    finally:
        db.close()
