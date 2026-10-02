"""Dataset endpoints: secondary dataset explorer, unified schema, cleaning rules, merge preview."""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from flask import Blueprint, Response, jsonify, request

from ..cleaning import CLEANING_RULES, clean_training_rows
from ..config import DERIVED_CSV, SECONDARY_CSV
from ..db import SessionLocal
from ..ml.features import (AGRO_FEATURES, FEATURE_COLUMNS, SEASON_PROFILES, SOIL_PROFILES,
                           WATER_IRRIGATION_FACTOR)
from ..models import SurveyEntry
from .utils import auth_required, pagination

bp = Blueprint("dataset", __name__, url_prefix="/api/dataset")

_cache: dict = {}


def _derived_df() -> pd.DataFrame:
    path = str(DERIVED_CSV)
    if not os.path.exists(path):
        from ..ml.train import default_paths, train_and_save
        secondary, out_dir, derived = default_paths()
        train_and_save(secondary, out_dir, derived_out=derived)
    mtime = os.path.getmtime(path)
    if _cache.get("mtime") != mtime:
        _cache["df"] = pd.read_csv(path)
        _cache["mtime"] = mtime
    return _cache["df"]


def _dist(series: pd.Series, top: int | None = None) -> list[dict]:
    counts = series.value_counts()
    if top:
        counts = counts.head(top)
    return [{"value": str(k), "count": int(v)} for k, v in counts.items()]


@bp.get("/secondary/summary")
def secondary_summary():
    df = _derived_df()
    rainfall = df["rainfall"].astype(float)
    hist, edges = np.histogram(rainfall, bins=12, range=(0, 320))
    return jsonify({
        "source": {
            "name": "Kaggle — Crop Recommendation Dataset (atharvaingle)",
            "url": "https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset",
            "license_note": "Publicly available for academic use; downloaded via a public mirror "
                            "and stored in backend/data/secondary/crop_recommendation.csv",
            "about": "2200 rows x 8 columns (N, P, K, temperature, humidity, ph, rainfall, label), "
                     "22 crop classes with exactly 100 rows each. Collected for a crop-suitability "
                     "classification exercise; it is synthetic/curated rather than a field survey.",
        },
        "rows": int(len(df)),
        "columns": [
            {"name": "N", "meaning": "soil nitrogen (kg/ha)"},
            {"name": "P", "meaning": "soil phosphorus (kg/ha)"},
            {"name": "K", "meaning": "soil potassium (kg/ha)"},
            {"name": "temperature", "meaning": "mean growing-period temperature (C)"},
            {"name": "humidity", "meaning": "relative humidity (%)"},
            {"name": "ph", "meaning": "soil pH"},
            {"name": "rainfall", "meaning": "growing-window rainfall (mm, dataset scale 20-299)"},
            {"name": "label", "meaning": "crop name (22 classes)"},
        ],
        "derived_columns": FEATURE_COLUMNS,
        "class_distribution": _dist(df["crop"]),
        "derived_distributions": {
            "soil_type": _dist(df["soil_type"]),
            "season": _dist(df["season"]),
            "water_availability": _dist(df["water_availability"]),
        },
        "rainfall_histogram": {
            "bins": [round(float(e), 1) for e in edges],
            "counts": [int(c) for c in hist],
            "note": ("The dataset tops out at 299 mm per period. A monsoon month in Dakshina Kannada "
                     "routinely exceeds this (the district's normal annual rainfall is ~4,000 mm), so "
                     "high-rainfall behaviour is an extrapolation — see honest limitations."),
        },
        "numeric_stats": json.loads(df[AGRO_FEATURES].describe().round(2).to_json()),
        "cleaning_rules": [
            {"rule": "pH outside [3.0, 9.5]", "action": "drop"},
            {"rule": "rainfall outside [0, 1000] mm", "action": "drop"},
            {"rule": "temperature outside [-5, 50] C", "action": "drop"},
            {"rule": "duplicate rows", "action": "drop"},
            {"rule": "label text", "action": "trim, lowercase, snake_case"},
        ],
    })


@bp.get("/secondary/rows")
def secondary_rows():
    df = _derived_df()
    limit, offset = pagination(25)
    for field, column in (("crop", "crop"), ("season", "season"),
                          ("soil_type", "soil_type"), ("water", "water_availability")):
        if request.args.get(field):
            df = df[df[column] == request.args[field]]
    if request.args.get("min_rainfall"):
        df = df[df["rainfall"] >= float(request.args["min_rainfall"])]
    if request.args.get("max_rainfall"):
        df = df[df["rainfall"] <= float(request.args["max_rainfall"])]
    if request.args.get("search"):
        df = df[df["crop"].str.contains(request.args["search"], case=False, na=False)]

    total = len(df)
    page = df.iloc[offset:offset + limit]
    return jsonify({
        "total": total, "limit": limit, "offset": offset,
        "rows": page.round(2).to_dict(orient="records"),
        "filters": {"crops": sorted(_derived_df()["crop"].unique().tolist()),
                    "seasons": sorted(_derived_df()["season"].unique().tolist()),
                    "soils": sorted(_derived_df()["soil_type"].unique().tolist()),
                    "water_levels": sorted(_derived_df()["water_availability"].unique().tolist())},
    })


@bp.get("/secondary/export")
def secondary_export():
    df = _derived_df()
    return Response(df.to_csv(index=False), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=derived_secondary_dataset.csv"})


@bp.get("/schema")
def schema():
    """The unified schema, the merge procedure and every mapping rule in one payload."""
    return jsonify({
        "secondary": {
            "file": "backend/data/secondary/crop_recommendation.csv",
            "rows": 2200,
            "columns": ["N", "P", "K", "temperature", "humidity", "ph", "rainfall", "label"],
        },
        "primary": {
            "table": "survey_entries",
            "fields": [
                {"name": "farmer_name", "type": "text", "required": True},
                {"name": "village", "type": "text", "required": True},
                {"name": "taluk", "type": "text", "required": True, "vocabulary": "Dakshina Kannada taluks"},
                {"name": "soil_type", "type": "enum", "required": True, "note": "REAL field observation"},
                {"name": "season", "type": "enum", "required": True, "note": "REAL field observation"},
                {"name": "rainfall_mm", "type": "float", "required": True, "range": "0-1000"},
                {"name": "water_source", "type": "enum", "required": True, "note": "REAL irrigation source"},
                {"name": "water_availability", "type": "enum", "derived": "from water_source"},
                {"name": "crop_grown", "type": "text", "required": True, "role": "label"},
                {"name": "yield_outcome", "type": "enum", "required": True, "role": "sample weight"},
                {"name": "area_acres", "type": "float", "required": False},
                {"name": "consent", "type": "boolean", "required": True, "note": "hard gate"},
                {"name": "status", "type": "enum", "values": ["pending", "approved", "rejected"]},
                {"name": "sample_weight", "type": "float", "derived": "yield_outcome"},
            ],
        },
        "unified_schema": {
            "columns": ["soil_type", "season", "rainfall_mm", "water_availability", "crop",
                        "source", "sample_weight"],
            "source_values": ["secondary_kaggle", "primary_survey"],
            "note": ("Both sources are reduced to the same five decision columns. Secondary rows get "
                     "sample_weight = 1.0 and their soil_type/season/water_availability are DERIVED; "
                     "primary rows carry real observations and a weight from yield_outcome."),
        },
        "mapping_rules": {
            "soil_type": {
                "method": "rule-based derivation from pH and N/P/K of the secondary row",
                "rules": [
                    "pH >= 8.0 and K < 40 -> coastal_saline",
                    "pH >= 7.2 and K >= 55 -> black",
                    "pH < 5.6 and K >= 40 -> laterite",
                    "N >= 80 and 6.0 <= pH <= 7.2 -> alluvial",
                    "pH >= 6.5 and K < 25 -> coastal_sandy",
                    "otherwise -> red_loam",
                ],
                "honesty": "No soil-type ground truth exists in the secondary dataset.",
            },
            "season": {
                "method": "rule-based derivation from temperature and rainfall",
                "rules": [
                    "rainfall >= 110 and not hot -> Kharif",
                    "temperature <= 22 -> Rabi",
                    "temperature >= 31, or >= 26 with rainfall < 55 -> Zaid",
                    "otherwise: rainfall >= 110 -> Kharif else Rabi",
                ],
                "honesty": "No season column exists in the secondary dataset.",
            },
            "water_availability": {
                "method": "rainfall-band proxy adjusted by the soil's water-retention class",
                "formula": "effective = rainfall * (1 + retention * 0.4); >=135 high, 78-135 medium, <78 low",
                "irrigation_sources": {"rainfed": "low", "open_well": "medium", "borewell": "medium",
                                       "drip_micro": "medium", "tank": "high", "canal": "high",
                                       "river_lift": "high"},
                "honesty": "At inference the user's real irrigation source is used instead — the proxy "
                           "exists only so the secondary data can be used at all.",
            },
            "rainfall_mm": {"method": "used directly (the one column that maps 1:1)"},
        },
        "expansion_rules": {
            "why": "The trained model uses seven measured parameters; the app collects four inputs.",
            "soil_profiles": {k: {"ph": v[0], "N": v[1], "P": v[2], "K": v[3]}
                              for k, v in SOIL_PROFILES.items()},
            "season_profiles": {k: {"temperature_c": v[0], "humidity_pct": v[1]}
                                for k, v in SEASON_PROFILES.items()},
            "water_irrigation_factor": WATER_IRRIGATION_FACTOR,
        },
        "cleaning_rules": {
            "primary": CLEANING_RULES,
            "secondary": [
                {"rule": "pH outside [3.0, 9.5]", "action": "drop"},
                {"rule": "rainfall outside [0, 1000] mm", "action": "drop"},
                {"rule": "temperature outside [-5, 50] C", "action": "drop"},
                {"rule": "exact duplicates", "action": "drop"},
            ],
        },
        "feedback_loop": [
            "1. A signed-in user opens My History and reports the crop actually grown + the yield outcome.",
            "2. With consent ticked, POST /api/history/<id>/feedback also writes a row into survey_entries.",
            "3. An admin/evaluator approves it (POST /api/surveys/<id>/review).",
            "4. POST /api/model/retrain merges approved rows (cleaned + weighted) and retrains all four models.",
            "5. /api/model/metrics then reports primary_rows_used > 0, plus an external-check block.",
        ],
    })


@bp.get("/merged/preview")
@auth_required()
def merged_preview():
    """Head of the merged training frame (secondary + cleaned approved primary rows)."""
    df = _derived_df()
    db = SessionLocal()
    try:
        approved = [r.to_dict() | {"consent": r.consent, "status": r.status}
                    for r in db.query(SurveyEntry).filter(SurveyEntry.status == "approved").all()]
    finally:
        db.close()
    accepted, dropped = clean_training_rows(approved)
    rows = [{"soil_type": r["soil_type"], "season": r["season"], "rainfall_mm": r["rainfall_mm"],
             "water_availability": r["water_availability"], "crop": r["crop"],
             "source": "primary_survey", "sample_weight": r["sample_weight"]}
            for r in accepted]
    secondary_head = [{"soil_type": r["soil_type"], "season": r["season"], "rainfall_mm": r["rainfall_mm"],
                       "water_availability": r["water_availability"], "crop": r["crop"],
                       "source": "secondary_kaggle", "sample_weight": 1.0}
                      for r in df.head(10).to_dict(orient="records")]
    return jsonify({
        "secondary_rows": int(len(df)),
        "approved_primary_rows": len(approved),
        "primary_rows_merging": len(accepted),
        "primary_rows_dropped": len(dropped),
        "dropped_detail": dropped[:20],
        "preview_primary": rows[:25],
        "preview_secondary": secondary_head,
        "unified_columns": ["soil_type", "season", "rainfall_mm", "water_availability", "crop",
                            "source", "sample_weight"],
    })
