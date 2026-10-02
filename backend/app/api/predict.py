"""Recommendation endpoints: metadata for the form, the REST predict endpoint, and saving."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from .. import constants
from ..cleaning import CLEANING_RULES, WATER_LEVEL_BY_SOURCE
from ..config import Config
from ..db import SessionLocal
from ..ml.features import (SOIL_PROFILES, SEASON_PROFILES, WATER_IRRIGATION_FACTOR,
                           expand_to_agronomic)
from ..ml.knowledge import CROPS, MODEL_CROP_LABELS, kb_summary
from ..ml.registry import registry
from ..models import Prediction
from .utils import (ApiError, audit, optional_auth, auth_required, bad_request, body,
                    current_user)

bp = Blueprint("predict", __name__)

VALID_SOIL = {s["value"] for s in constants.SOIL_TYPES}
VALID_SEASON = {s["value"] for s in constants.SEASONS}
VALID_WATER = {w["value"] for w in constants.WATER_LEVELS}
VALID_SOURCES = {s["value"] for s in constants.IRRIGATION_SOURCES}


@bp.get("/api/meta")
def meta():
    """Everything the Recommend form needs, in one call."""
    return jsonify({
        "app_name": Config.APP_NAME,
        "district": Config.DISTRICT,
        "version": Config.APP_VERSION,
        "soil_types": constants.SOIL_TYPES,
        "seasons": constants.SEASONS,
        "water_levels": constants.WATER_LEVELS,
        "irrigation_sources": constants.IRRIGATION_SOURCES,
        "taluks": constants.TALUKS,
        "yield_outcomes": constants.YIELD_OUTCOMES,
        "rainfall_presets": constants.RAINFALL_PRESETS,
        "model_crops": [{"value": c, "label": CROPS[c]["en_name"], "label_kn": CROPS[c]["kn"]}
                        for c in MODEL_CROP_LABELS],
        "crop_reference_count": len(CROPS),
        "blend": {"model_exponent": 0.55, "rule_exponent": 0.45,
                  "formula": "score = model_probability^0.55 x agronomic_rule_fit^0.45 "
                             "(x1.05 prior for crops grown in DK when regional tuning is on)",
                  "note": "geometric blend, so a poor agronomic rule fit cannot be outvoted "
                          "by a high model probability"},
    })


@bp.get("/api/expansion-rules")
def expansion_rules():
    """Publish the input-expansion assumptions (transparency requirement)."""
    return jsonify({
        "why": ("The model is trained on seven measured agronomic parameters; the app collects four "
                "farmer-answerable inputs and expands them using the documented typical profiles below. "
                "These are stated assumptions, not measurements."),
        "soil_profiles": {
            k: {"ph": v[0], "N": v[1], "P": v[2], "K": v[3],
                "retention": SOIL_PROFILES.get(k, (0, 0, 0, 0))[0] and None}
            for k, v in SOIL_PROFILES.items()
        },
        "season_profiles": {k: {"temperature_c": v[0], "humidity_pct": v[1]}
                            for k, v in SEASON_PROFILES.items()},
        "water_irrigation_factor": WATER_IRRIGATION_FACTOR,
        "note": "rainfall used by the model = reported rainfall x irrigation factor, clamped to [0, 300] mm",
    })


def _validate_payload(data: dict) -> dict:
    soil = data.get("soil_type")
    season = data.get("season")
    water = data.get("water_availability")
    source = data.get("irrigation_source")

    # If the user picks an irrigation source, it defines water availability (single source of truth).
    if source:
        if source not in VALID_SOURCES:
            bad_request(f"irrigation_source must be one of {sorted(VALID_SOURCES)}",
                        code="invalid_irrigation_source")
        water = WATER_LEVEL_BY_SOURCE[source]
    if soil not in VALID_SOIL:
        bad_request(f"soil_type must be one of {sorted(VALID_SOIL)}", code="invalid_soil_type")
    if season not in VALID_SEASON:
        bad_request(f"season must be one of {sorted(VALID_SEASON)}", code="invalid_season")
    if water not in VALID_WATER:
        bad_request(f"water_availability must be one of {sorted(VALID_WATER)}",
                    code="invalid_water_availability")
    try:
        rainfall = float(data.get("rainfall_mm"))
    except (TypeError, ValueError):
        bad_request("rainfall_mm must be a number (growing-window rainfall in millimetres)",
                    code="invalid_rainfall")
    if not (0 <= rainfall <= 1000):
        bad_request("rainfall_mm must be between 0 and 1000 for this model; if you meant annual "
                    "district rainfall (~3900 mm in DK), enter the growing-window figure instead "
                    "(e.g. 220 mm for a monsoon month).", code="rainfall_out_of_range")

    try:
        top_k = int(data.get("top_k", 3))
    except (TypeError, ValueError):
        top_k = 3
    return {"soil_type": soil, "season": season, "rainfall_mm": rainfall,
            "water_availability": water, "irrigation_source": source,
            "regional_tuning": bool(data.get("regional_tuning", True)),
            "top_k": min(5, max(1, top_k)), "taluk": data.get("taluk"),
            "save": bool(data.get("save", False)), "notes": data.get("notes")}


@bp.post("/api/predict")
@optional_auth
def predict():
    """REST endpoint: returns the top-3 crops with confidence, reasons and advisories.

    Anonymous calls are allowed (handy for evaluators and for curl); saving the result to
    history requires a signed-in user.
    """
    payload = _validate_payload(body())
    user = current_user(optional=True)
    db = SessionLocal()
    try:
        result = registry.predict(
            soil_type=payload["soil_type"], season=payload["season"],
            rainfall_mm=payload["rainfall_mm"], water_availability=payload["water_availability"],
            regional_tuning=payload["regional_tuning"], top_k=payload["top_k"], db=db,
        )
        result["expanded_parameters_full"] = expand_to_agronomic(
            payload["soil_type"], payload["season"], payload["rainfall_mm"],
            payload["water_availability"])
        saved = None
        if payload["save"]:
            if not user:
                bad_request("Sign in to save a recommendation to your history",
                            code="login_required_to_save")
            top = result["recommendations"][0] if result["recommendations"] else None
            if not top:
                bad_request("The model returned no recommendation for this input",
                            code="no_recommendation")
            row = Prediction(
                user_id=user.id, soil_type=payload["soil_type"], season=payload["season"],
                rainfall_mm=payload["rainfall_mm"], water_availability=payload["water_availability"],
                irrigation_source=payload["irrigation_source"], taluk=payload["taluk"],
                regional_tuning=payload["regional_tuning"], top_crop=top["crop"],
                top_confidence=top["confidence"],
                results_json=json.dumps({"recommendations": result["recommendations"],
                                         "regional_advisory": result["regional_advisory"],
                                         "confidence_note": result["confidence_note"],
                                         "expansion_audit": result["expansion_audit"]}),
                model_key=result["model"]["key"], model_version=result["model"]["version"],
                notes=payload["notes"],
            )
            db.add(row)
            db.commit()
            saved = row.to_dict()
        result["saved"] = saved
        return jsonify(result)
    finally:
        db.close()


@bp.get("/api/crops/reference")
def crop_reference_public():
    """Read-only crop knowledge base (full CRUD lives under /api/crops with an admin token)."""
    crops = [kb_summary(c) for c in sorted(CROPS)]
    return jsonify({"count": len(crops), "crops": crops,
                    "kb_only_note": ("Crops marked kb_only=true are not in the secondary dataset's "
                                     "22 classes; they can only ever be a knowledge-base advisory, "
                                     "never a machine-learning prediction.")})


@bp.get("/api/cleaning-rules")
def cleaning_rules():
    return jsonify({"primary_data_rules": CLEANING_RULES,
                    "secondary_data_rules": [
                        {"rule": "pH outside [3.0, 9.5]", "action": "drop row"},
                        {"rule": "rainfall outside [0, 1000] mm", "action": "drop row"},
                        {"rule": "temperature outside [-5, 50] C", "action": "drop row"},
                        {"rule": "exact duplicate rows", "action": "drop"},
                        {"rule": "crop label text", "action": "trim + lowercase + snake_case"},
                    ],
                    "mapping_rules_doc": "docs/dataset_schema.md"})
