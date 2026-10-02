"""Unit tests for the data-cleaning rules and the mapping / expansion feature layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cleaning import (CLEANING_RULES, clean_training_rows, sample_weight_for,
                          validate_survey_payload)
from app.ml import features as F


# ------------------------------------------------------------------ cleaning rules
def _row(**over):
    base = {"id": 1, "consent": True, "status": "approved", "soil_type": "laterite",
            "season": "Kharif", "water_source": "rainfed", "water_availability": "low",
            "rainfall_mm": 240, "crop_grown": "rice", "yield_outcome": "good",
            "farmer_name": "A", "village": "V", "area_acres": 1.0}
    base.update(over)
    return base


def test_rule_count_is_documented():
    assert len(CLEANING_RULES) == 10
    assert [r["id"] for r in CLEANING_RULES] == list(range(1, 11))


@pytest.mark.parametrize("outcome,weight", [("excellent", 1.0), ("good", 1.0),
                                            ("average", 0.5), ("poor", 0.0)])
def test_sample_weight_from_yield_outcome(outcome, weight):
    assert sample_weight_for(outcome) == weight


def test_rule1_consent_is_a_hard_gate():
    _, errors = validate_survey_payload({"consent": False})
    assert any("consent_required" in e for e in errors)


def test_rules2_to5_validation_messages():
    _, errors = validate_survey_payload({
        "consent": True, "soil_type": "moon", "season": "Kharif", "water_source": "canal",
        "crop_grown": "", "yield_outcome": "good", "farmer_name": "", "village": "V",
        "taluk": "Puttur", "rainfall_mm": 2000, "area_acres": 500})
    joined = " ".join(errors)
    assert "invalid_vocabulary" in joined          # soil + missing crop
    assert "missing_required" in joined            # farmer_name
    assert "rainfall_out_of_range" in joined
    assert "area_out_of_range" in joined


def test_valid_payload_normalises_crop_and_derives_water_level():
    norm, errors = validate_survey_payload({
        "consent": True, "farmer_name": " A ", "village": " V ", "taluk": "Puttur",
        "soil_type": "laterite", "season": "Kharif", "rainfall_mm": "240",
        "water_source": "borewell", "crop_grown": "Black Pepper", "yield_outcome": "good"})
    assert errors == []
    assert norm["crop_grown"] == "black_pepper"
    assert norm["water_availability"] == "medium"
    assert norm["rainfall_mm"] == 240.0
    assert norm["farmer_name"] == "A"


def test_rule6_duplicates_are_collapsed_keeping_the_latest():
    rows = [_row(id=1, rainfall_mm=240), _row(id=2, rainfall_mm=240)]
    accepted, dropped = clean_training_rows(rows)
    assert len(accepted) == 1 and accepted[0]["id"] == 2
    assert [d["reason"] for d in dropped] == ["duplicate"]
    assert dropped[0]["rule_id"] == 6


def test_rule7_poor_yield_is_excluded_from_training():
    accepted, dropped = clean_training_rows([_row(yield_outcome="poor")])
    assert accepted == []
    assert dropped[0]["reason"] == "excluded_poor_yield" and dropped[0]["rule_id"] == 7


def test_rule8_average_yield_enters_with_half_weight():
    accepted, _ = clean_training_rows([_row(yield_outcome="average")])
    assert accepted[0]["sample_weight"] == 0.5
    assert "partial_confidence(0.5)" in accepted[0]["rules_applied"]


def test_rule10_unapproved_rows_are_not_merged():
    accepted, dropped = clean_training_rows([_row(status="pending")])
    assert accepted == [] and dropped[0]["reason"] == "not_approved"


def test_cleaning_report_is_lossless():
    rows = [_row(id=1), _row(id=2, village="W", yield_outcome="poor"),
            _row(id=3, village="X", consent=False), _row(id=4, village="Y", status="pending")]
    accepted, dropped = clean_training_rows(rows)
    assert len(accepted) + len(dropped) == len(rows)
    assert {d["reason"] for d in dropped} == {"excluded_poor_yield", "consent_required", "not_approved"}


# ------------------------------------------------------------------ derived mapping rules
@pytest.mark.parametrize("n,p,k,ph,expected", [
    (30, 45, 60, 5.3, "laterite"),
    (60, 50, 45, 6.0, "red_loam"),
    (100, 55, 45, 6.8, "alluvial"),
    (35, 40, 18, 6.6, "coastal_sandy"),
    (50, 60, 90, 7.8, "black"),
    (40, 45, 30, 8.3, "coastal_saline"),
])
def test_derive_soil_type(n, p, k, ph, expected):
    assert F.derive_soil_type(n, p, k, ph) == expected


@pytest.mark.parametrize("temp,rainfall,expected", [
    (26.5, 240, "Kharif"),      # monsoon
    (21.5, 70, "Rabi"),         # cool post-monsoon
    (32.0, 40, "Zaid"),         # hot and dry
    (27.0, 45, "Zaid"),         # hot with very little rain
    (28.0, 90, "Rabi"),         # dry but not hot -> rabi window
])
def test_derive_season(temp, rainfall, expected):
    assert F.derive_season(temp, rainfall) == expected


def test_derive_water_availability_bands_and_soil_effect():
    """Bands are documented in docs/dataset_schema.md:
    effective = rainfall x (1 + retention x 0.4); >=135 high, 78-135 medium, <78 low."""
    assert F.derive_water_availability(200, "laterite") == "high"
    assert F.derive_water_availability(60, "red_loam") == "low"
    assert F.derive_water_availability(80, "red_loam") == "medium"
    # the same rain retains less on leached coastal sand than on alluvial valley soil
    assert F.derive_water_availability(70, "coastal_sandy") == "low"
    assert F.derive_water_availability(70, "alluvial") == "medium"


def test_only_the_four_documented_inputs_are_collected():
    assert F.FEATURE_COLUMNS == ["soil_type", "season", "rainfall_mm", "water_availability"]
    assert F.AGRO_FEATURES == ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]


def test_expansion_produces_the_seven_model_parameters():
    agro = F.expand_to_agronomic("laterite", "Kharif", 240, "high")
    assert set(agro) == set(F.AGRO_FEATURES)
    assert agro["ph"] == pytest.approx(5.3)           # laterite is acidic
    assert agro["humidity"] == pytest.approx(88.0)    # Kharif in the coastal belt
    assert agro["rainfall"] == pytest.approx(min(300.0, 240 * F.WATER_IRRIGATION_FACTOR["high"]))
    # the model input is clamped to the dataset's own scale
    assert F.expand_to_agronomic("laterite", "Kharif", 1000, "high")["rainfall"] == 300.0


def test_expansion_is_monotonic_in_water_availability():
    low = F.expand_to_agronomic("laterite", "Rabi", 100, "low")["rainfall"]
    high = F.expand_to_agronomic("laterite", "Rabi", 100, "high")["rainfall"]
    assert low < high


def test_expansion_audit_is_transparent():
    audit = F.expansion_explanation("coastal_sandy", "Zaid", "high")
    assert len(audit) == 3
    assert {e["input"] for e in audit} == {"soil_type", "season", "rainfall_mm"}
    assert all(e["basis"] for e in audit)


def test_load_secondary_applies_cleaning_and_mapping():
    csv = Path(__file__).resolve().parent.parent / "backend/data/secondary/crop_recommendation.csv"
    df = F.load_secondary(str(csv))
    # 2200 raw rows; the documented cleaning rules drop a couple of out-of-range/duplicate rows
    assert 2190 <= len(df) <= 2200
    assert set(F.FEATURE_COLUMNS).issubset(df.columns)
    assert df["crop"].nunique() == 22
    assert df["source"].unique().tolist() == ["secondary_kaggle"]
    # sample_weight is assigned by merge_sources() (secondary rows count as full-weight)
    assert "sample_weight" not in df.columns
    assert set(df["soil_type"].unique()) <= set(F.SOIL_PROFILES)
    assert set(df["season"].unique()) <= {"Kharif", "Rabi", "Zaid"}
    assert set(df["water_availability"].unique()) <= {"low", "medium", "high"}


def test_load_secondary_rejects_a_wrong_schema(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b,c\n1,2,3\n")
    with pytest.raises(ValueError, match="missing required columns"):
        F.load_secondary(str(bad))


def test_merge_sources_adds_expanded_columns_for_primary_rows():
    import pandas as pd
    secondary = pd.DataFrame([{
        "soil_type": "laterite", "season": "Kharif", "rainfall_mm": 240.0,
        "water_availability": "high", "crop": "rice", "N": 60, "P": 50, "K": 55,
        "temperature": 26.5, "humidity": 88.0, "ph": 5.3, "rainfall": 276.0}])
    primary = [{"soil_type": "alluvial", "season": "Rabi", "rainfall_mm": 90.0,
                "water_availability": "medium", "crop": "rice", "sample_weight": 0.5}]
    merged = F.merge_sources(secondary, primary)
    assert len(merged) == 2
    assert merged[merged["source"] == "secondary_kaggle"]["sample_weight"].tolist() == [1.0]
    prim = merged[merged["source"] == "primary_survey"].iloc[0]
    assert prim["N"] == F.SOIL_PROFILES["alluvial"][1]     # expansion filled the chemistry
    assert prim["sample_weight"] == 0.5
