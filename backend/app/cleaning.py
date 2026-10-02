"""
Primary-data cleaning rules.

Every rule below is deterministic, logged, and surfaced in the UI
(Dataset Explorer -> "Primary data cleaning rules") so a KVK officer can see exactly what
happens to the row they submitted. Rules run when a survey is submitted (validation) and
again when training data is assembled (assembly-time cleaning).

 | # | Rule                                              | Action |
 |---|---------------------------------------------------|--------|
 | 1 | Consent checkbox not ticked                       | reject row (`consent_required`) |
 | 2 | Missing soil_type / season / water_source / crop  | reject row (`missing_required`) |
 | 3 | rainfall_mm outside 0-1000                        | reject row (`rainfall_out_of_range`) |
 | 4 | area_acres <= 0 or > 100                          | reject row (`area_out_of_range`) |
 | 5 | Unknown controlled-vocabulary value               | reject row (`invalid_vocabulary`) |
 | 6 | Duplicate submission (same farmer, village,    | collapse to the latest accepted row |
 |   | season, crop and rainfall)                        | (`duplicate`) |
 | 7 | yield_outcome == 'poor'                           | excluded from training (`excluded_poor_yield`) |
 | 8 | yield_outcome == 'average'                        | sample_weight 0.5 (`partial_confidence`) |
 | 9 | yield_outcome in (good, excellent)                | sample_weight 1.0 |
 |10 | Review status != approved                         | not merged until an admin approves it |
"""

from __future__ import annotations

from . import constants

VALID_SOIL = {s["value"] for s in constants.SOIL_TYPES}
VALID_SEASON = {s["value"] for s in constants.SEASONS}
VALID_WATER_SOURCE = {s["value"] for s in constants.IRRIGATION_SOURCES}
VALID_YIELD = {y["value"]: y for y in constants.YIELD_OUTCOMES}
WATER_LEVEL_BY_SOURCE = {s["value"]: s["level"] for s in constants.IRRIGATION_SOURCES}

RAINFALL_MIN, RAINFALL_MAX = 0.0, 1000.0
AREA_MIN, AREA_MAX = 0.01, 100.0

CLEANING_RULES = [
    {"id": 1, "rule": "Consent checkbox must be ticked", "action": "reject: consent_required"},
    {"id": 2, "rule": "soil_type, season, water_source, crop_grown and yield_outcome required",
     "action": "reject: missing_required"},
    {"id": 3, "rule": f"0 <= rainfall_mm <= {RAINFALL_MAX:g}", "action": "reject: rainfall_out_of_range"},
    {"id": 4, "rule": f"{AREA_MIN} <= area_acres <= {AREA_MAX:g} (when provided)",
     "action": "reject: area_out_of_range"},
    {"id": 5, "rule": "values must come from the app's controlled vocabularies",
     "action": "reject: invalid_vocabulary"},
    {"id": 6, "rule": "same farmer + village + season + crop + rainfall submitted twice",
     "action": "collapse to the latest accepted row: duplicate"},
    {"id": 7, "rule": "yield_outcome == poor (crop choice did not work here)",
     "action": "excluded from training: excluded_poor_yield"},
    {"id": 8, "rule": "yield_outcome == average", "action": "sample_weight 0.5: partial_confidence"},
    {"id": 9, "rule": "yield_outcome in (good, excellent)", "action": "sample_weight 1.0"},
    {"id": 10, "rule": "survey review status must be 'approved'",
     "action": "rows stay pending until an admin/evaluator approves them"},
]


def validate_survey_payload(payload: dict) -> tuple[dict, list[str]]:
    """Rule 1-5. Returns (normalised_payload, errors). Safe to call from the API layer."""
    errors: list[str] = []

    if payload.get("consent") is not True:
        errors.append("consent_required: the data-sharing consent box must be ticked.")

    soil = payload.get("soil_type")
    season = payload.get("season")
    water_source = payload.get("water_source")
    crop = (payload.get("crop_grown") or "").strip().lower().replace(" ", "_")
    outcome = payload.get("yield_outcome")

    if soil not in VALID_SOIL:
        errors.append(f"invalid_vocabulary: soil_type must be one of {sorted(VALID_SOIL)}")
    if season not in VALID_SEASON:
        errors.append(f"invalid_vocabulary: season must be one of {sorted(VALID_SEASON)}")
    if water_source not in VALID_WATER_SOURCE:
        errors.append(f"invalid_vocabulary: water_source must be one of {sorted(VALID_WATER_SOURCE)}")
    if outcome not in VALID_YIELD:
        errors.append(f"invalid_vocabulary: yield_outcome must be one of {sorted(VALID_YIELD)}")
    if not crop:
        errors.append("missing_required: crop_grown is required")
    for field in ("farmer_name", "village", "taluk"):
        if not (payload.get(field) or "").strip():
            errors.append(f"missing_required: {field} is required")

    try:
        rainfall = float(payload.get("rainfall_mm"))
        if not (RAINFALL_MIN <= rainfall <= RAINFALL_MAX):
            errors.append(f"rainfall_out_of_range: rainfall_mm must be between "
                          f"{RAINFALL_MIN:g} and {RAINFALL_MAX:g} (got {rainfall:g})")
    except (TypeError, ValueError):
        rainfall = None
        errors.append("missing_required: rainfall_mm must be a number")

    area = payload.get("area_acres")
    if area in (None, ""):
        area = None
    else:
        try:
            area = float(area)
            if not (AREA_MIN <= area <= AREA_MAX):
                errors.append(f"area_out_of_range: area_acres must be between "
                              f"{AREA_MIN:g} and {AREA_MAX:g}")
        except (TypeError, ValueError):
            errors.append("invalid_vocabulary: area_acres must be a number or empty")

    normalised = {
        "farmer_name": (payload.get("farmer_name") or "").strip(),
        "village": (payload.get("village") or "").strip(),
        "taluk": (payload.get("taluk") or "").strip(),
        "phone": (payload.get("phone") or "").strip() or None,
        "soil_type": soil,
        "season": season,
        "rainfall_mm": rainfall,
        "water_source": water_source,
        "water_availability": WATER_LEVEL_BY_SOURCE.get(water_source, "medium"),
        "crop_grown": crop,
        "yield_outcome": outcome,
        "area_acres": area,
        "notes": (payload.get("notes") or "").strip() or None,
        "consent": bool(payload.get("consent")),
    }
    return normalised, errors


def sample_weight_for(outcome: str) -> float:
    """Rules 7-9: how much a row counts during training."""
    return float(VALID_YIELD.get(outcome, {}).get("sample_weight", 0.0))


def clean_training_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Assembly-time cleaning (rules 6-10).

    `rows` are dicts of approved survey entries. Returns (accepted, dropped) where each
    dropped entry carries the rule id and reason, so the cleaning is auditable.
    """
    accepted: dict[tuple, dict] = {}
    dropped: list[dict] = []

    for row in sorted(rows, key=lambda r: r.get("id") or 0):
        rules_hit: list[str] = []
        if not row.get("consent"):
            dropped.append({**row, "rule_id": 1, "reason": "consent_required"}); continue
        if row.get("status") != "approved":
            dropped.append({**row, "rule_id": 10, "reason": "not_approved"}); continue
        if not all(row.get(f) not in (None, "") for f in
                   ("soil_type", "season", "water_source", "crop_grown", "rainfall_mm")):
            dropped.append({**row, "rule_id": 2, "reason": "missing_required"}); continue
        if not (RAINFALL_MIN <= float(row["rainfall_mm"]) <= RAINFALL_MAX):
            dropped.append({**row, "rule_id": 3, "reason": "rainfall_out_of_range"}); continue
        area = row.get("area_acres")
        if area is not None and not (AREA_MIN <= float(area) <= AREA_MAX):
            dropped.append({**row, "rule_id": 4, "reason": "area_out_of_range"}); continue
        if (row["soil_type"] not in VALID_SOIL or row["season"] not in VALID_SEASON
                or row["water_source"] not in VALID_WATER_SOURCE
                or row["yield_outcome"] not in VALID_YIELD):
            dropped.append({**row, "rule_id": 5, "reason": "invalid_vocabulary"}); continue

        weight = sample_weight_for(row["yield_outcome"])
        if weight == 0.0:
            dropped.append({**row, "rule_id": 7, "reason": "excluded_poor_yield"}); continue
        if weight < 1.0:
            rules_hit.append("partial_confidence(0.5)")

        key = (row.get("farmer_name"), row.get("village"), row["season"],
               row["crop_grown"], round(float(row["rainfall_mm"]), 1))
        trained = {
            "id": row.get("id"),
            "soil_type": row["soil_type"],
            "season": row["season"],
            "rainfall_mm": float(row["rainfall_mm"]),
            "water_availability": row.get("water_availability")
            or WATER_LEVEL_BY_SOURCE.get(row["water_source"], "medium"),
            "crop": row["crop_grown"],
            "source": "primary_survey",
            "sample_weight": weight,
            "rules_applied": rules_hit,
        }
        if key in accepted:
            dropped.append({**row, "rule_id": 6, "reason": "duplicate"})
        accepted[key] = trained

    return list(accepted.values()), dropped
