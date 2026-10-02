"""
Feature engineering: map the free secondary dataset (Kaggle "Crop Recommendation
Dataset", 2200 rows x {N, P, K, temperature, humidity, ph, rainfall, label}) onto
the FOUR decision inputs this app actually collects from a user:

    1. soil_type          (categorical: laterite / red_loam / alluvial / coastal_sandy / black / coastal_saline)
    2. season             (Kharif / Rabi / Zaid)
    3. rainfall_mm        (numeric, growing-window monthly rainfall in mm)
    4. water_availability (low / medium / high)

IMPORTANT / HONESTY NOTE
------------------------
The secondary dataset has NO soil-type column, NO season column and NO irrigation
column. Two of the four inputs are therefore *derived* with documented, deterministic
rules (below) from the columns the dataset does have. They are engineered proxies,
not ground-truth labels, and the metrics produced by training on them measure how
consistently the model reproduces those rules + the crop label, not how well the
model would score against real surveyed soil/season/irrigation labels.

The primary survey dataset (collected in-app) DOES contain real soil type, real
season, real water source and real crop grown, so the same pipeline can be re-run
on genuinely independent labels (merging step: merge_sources()).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------------------
# Controlled vocabularies (kept in sync with backend/app/constants.py)
# --------------------------------------------------------------------------------------

SOIL_TYPES = ["laterite", "red_loam", "alluvial", "coastal_sandy", "black", "coastal_saline"]
SEASONS = ["Kharif", "Rabi", "Zaid"]
WATER_LEVELS = ["low", "medium", "high"]

# Water retention class of each soil (used only to make the derived water-availability
# proxy not a pure function of rainfall; laterite/black retain more than coastal sand).
SOIL_RETENTION = {
    "laterite": 0.35,
    "red_loam": 0.30,
    "alluvial": 0.40,
    "coastal_sandy": 0.05,
    "black": 0.55,
    "coastal_saline": 0.10,
}

# ---------------------------------------------------------------- derived mapping rules

def derive_soil_type(n: float, p: float, k: float, ph: float) -> str:
    """Rule-based mapping from soil chemistry -> soil type.

    Rules follow commonly documented profiles of the soils of coastal Karnataka /
    peninsular India (see docs/dataset_schema.md for the full rule table and sources):
      * laterite     : acidic (pH < 5.6), leached, K-rich residuum
      * red_loam     : moderately acidic, medium nutrients (the default class)
      * alluvial     : near-neutral, high nitrogen (fertile transported soil)
      * coastal_sandy: near-neutral but very low potassium (leached sand)
      * black        : neutral-alkaline, high K (vertisol / clay-like)
      * coastal_saline: alkaline (pH >= 8.0), low K (saline coastal soils)
    """
    if ph >= 8.0 and k < 40:
        return "coastal_saline"
    if ph >= 7.2 and k >= 55:
        return "black"
    if ph < 5.6 and k >= 40:
        return "laterite"
    if n >= 80 and 6.0 <= ph <= 7.2:
        return "alluvial"
    if ph >= 6.5 and k < 25:
        return "coastal_sandy"
    return "red_loam"


def derive_season(temperature: float, rainfall: float) -> str:
    """Rule-based mapping from (temperature, rainfall) -> Indian cropping season.

      * Kharif : monsoon window  -> rainfall >= 110 mm and temperate (18-33 C)
      * Zaid   : hot dry window  -> temp >= 31 C, or temp >= 26 C with rainfall < 55 mm
      * Rabi   : cool / post-monsoon window -> everything else (temp <= 22 C, or dry+temperate)
    """
    monsoon = rainfall >= 110
    hot = temperature >= 31 or (temperature >= 26 and rainfall < 55)
    cool = temperature <= 22
    if monsoon and not hot:
        return "Kharif"
    if cool:
        return "Rabi"
    if hot:
        return "Zaid"
    if monsoon:
        return "Kharif"
    return "Rabi"


def derive_water_availability(rainfall: float, soil_type: str) -> str:
    """Derived proxy for water availability.

    The secondary dataset has no irrigation column, so water availability is a
    rainfall-band proxy adjusted by the soil's water-retention class:

        effective = rainfall * (1 + retention_bonus)  where retention_bonus = retention * 0.4
        >= 135 mm -> high | 78-135 mm -> medium | < 78 mm -> low

    At inference time this proxy is NOT used: the user picks a real irrigation
    source, which is mapped with IRRIGATION_TO_LEVEL (see constants.py).
    """
    retention = SOIL_RETENTION.get(soil_type, 0.25)
    effective = rainfall * (1.0 + retention * 0.4)
    if effective >= 135:
        return "high"
    if effective >= 78:
        return "medium"
    return "low"


def engineer_row(n: float, p: float, k: float, temperature: float, humidity: float,
                 ph: float, rainfall: float) -> dict:
    soil = derive_soil_type(n, p, k, ph)
    return {
        "soil_type": soil,
        "season": derive_season(temperature, rainfall),
        "rainfall_mm": round(float(rainfall), 2),
        "water_availability": derive_water_availability(rainfall, soil),
    }


REQUIRED_SECONDARY_COLUMNS = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall", "label"]

FEATURE_COLUMNS = ["soil_type", "season", "rainfall_mm", "water_availability"]
TARGET_COLUMN = "crop"
CATEGORICAL_FEATURES = ["soil_type", "season", "water_availability"]
NUMERIC_FEATURES = ["rainfall_mm"]

# The seven agronomic parameters the secondary dataset actually measures.
AGRO_FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]

# --------------------------------------------------------------------------------------
# Knowledge-guided expansion: 4 farmer-answerable inputs -> 7 agronomic parameters
# --------------------------------------------------------------------------------------
# The app asks only questions a farmer can answer without a soil-test lab report. To still
# use everything the secondary dataset knows, each answer is expanded into the seven
# measured parameters using documented TYPICAL profiles for coastal-Karnataka soils and
# seasons. Every number below is a stated assumption, not a measurement.
#
# Soil profiles are indicative mid-points consistent with published soil descriptions
# (KVK Dakshina Kannada: lateritic soils, pH 4.6-5.8, nutrient status low-medium; NRDMS
# Dakshina Kannada natural-resource report: lateritic/red loamy/alluvial/coastal sandy
# distribution; ICAR soil-test interpretation classes for N/P/K).
# Values represent the soil AFTER the standard package-of-practices fertilizer dose is
# applied (managed fertility), because every row of the secondary dataset was produced on a
# managed field. What still differs between soil types is pH, potassium status and texture —
# which is exactly what a farmer's soil-type answer conveys. Using raw depleted soil-test
# values instead was tested and produced rankings that contradict DK agronomy (e.g. rice
# pushed below papaya in a Kharif monsoon profile), so the managed-fertility reading is both
# more representative and more defensible. This choice is stated on the About page.
SOIL_PROFILES = {
    #           pH    N    P    K   (kg/ha, dataset scale; managed fertility)
    "laterite":       (5.3, 60, 50, 55),
    "red_loam":       (6.0, 65, 50, 45),
    "alluvial":       (6.8, 85, 55, 45),
    "coastal_sandy":  (6.6, 50, 45, 25),
    "black":          (7.6, 55, 60, 80),
    "coastal_saline": (8.2, 50, 45, 35),
}

# Season -> typical temperature / relative humidity envelope in the coastal belt.
SEASON_PROFILES = {
    #             temp C, RH %
    "Kharif":  (26.5, 88.0),
    "Rabi":    (21.5, 72.0),
    "Zaid":    (32.0, 55.0),
}

# Irrigation supplement factor applied to the growing-window rainfall: a high-water
# availability profile effectively adds moisture, a rainfed-only profile is at the mercy
# of the rain. This is an index on the dataset's own rainfall scale (0-300 mm), not a
# claim of added millimetres.
WATER_IRRIGATION_FACTOR = {"low": 0.85, "medium": 1.00, "high": 1.15}


def expand_to_agronomic(soil_type: str, season: str, rainfall_mm: float,
                        water_availability: str) -> dict:
    """Expand the 4 collected inputs into the 7 agronomic parameters the model was trained on."""
    ph, n, p, k = SOIL_PROFILES.get(soil_type, SOIL_PROFILES["red_loam"])
    temp, humidity = SEASON_PROFILES.get(season, SEASON_PROFILES["Kharif"])
    factor = WATER_IRRIGATION_FACTOR.get(water_availability, 1.0)
    return {
        "N": float(n),
        "P": float(p),
        "K": float(k),
        "temperature": float(temp),
        "humidity": float(humidity),
        "ph": float(ph),
        "rainfall": float(min(300.0, max(0.0, rainfall_mm * factor))),
    }


def expansion_explanation(soil_type: str, season: str, water_availability: str) -> list[dict]:
    """Human-readable audit trail of the expansion, so the assumption is never hidden."""
    ph, n, p, k = SOIL_PROFILES.get(soil_type, SOIL_PROFILES["red_loam"])
    temp, humidity = SEASON_PROFILES.get(season, SEASON_PROFILES["Kharif"])
    factor = WATER_IRRIGATION_FACTOR.get(water_availability, 1.0)
    return [
        {"input": "soil_type", "value": soil_type,
         "assumed_as": f"pH {ph}, N {n}, P {p}, K {k} (kg/ha, managed fertility)",
         "basis": "Typical profile of this soil after the standard fertilizer dose "
                  "(KVK DK soil description, pH 4.6-5.8 for lateritic soils; ICAR nutrient classes)"},
        {"input": "season", "value": season, "assumed_as": f"{temp} C, {humidity}% RH",
         "basis": "Seasonal climate envelope for the coastal belt"},
        {"input": "rainfall_mm", "value": None, "assumed_as": f"rainfall x {factor}",
         "basis": "Irrigation supplement index for the reported water availability"},
    ]


def load_secondary(path: str) -> pd.DataFrame:
    """Load + validate the secondary CSV and return the *derived* 5-column frame."""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED_SECONDARY_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Secondary dataset is missing required columns: {missing}. "
            f"Expected columns: {REQUIRED_SECONDARY_COLUMNS}"
        )
    df = df[REQUIRED_SECONDARY_COLUMNS].copy()
    df = df.dropna()
    # Cleaning rules applied to the secondary data (see docs/dataset_schema.md):
    #  1. pH outside [3.0, 9.5] is a sensor/entry error -> drop
    #  2. rainfall outside [0, 1000] mm -> drop
    #  3. temperature outside [-5, 50] C -> drop
    df = df[(df["ph"].between(3.0, 9.5)) & (df["rainfall"].between(0, 1000)) &
            (df["temperature"].between(-5, 50))]
    #  4. exact duplicate rows -> drop
    df = df.drop_duplicates()
    #  5. crop label normalised to lower snake_case
    df = df.reset_index(drop=True)
    df["crop"] = df["label"].astype(str).str.strip().str.lower().str.replace(r"\s+", "_", regex=True)
    derived = df.apply(
        lambda r: engineer_row(r["N"], r["P"], r["K"], r["temperature"], r["humidity"], r["ph"], r["rainfall"]),
        axis=1, result_type="expand",
    )
    out = pd.concat([derived, df[["crop", "N", "P", "K", "temperature", "humidity", "ph", "rainfall"]]], axis=1)
    out["source"] = "secondary_kaggle"
    return out


def merge_sources(secondary: pd.DataFrame, primary_rows: list[dict]) -> pd.DataFrame:
    """Merge secondary (2200 rows) with cleaned primary survey rows into ONE schema.

    Unified schema (see docs/dataset_schema.md):
        soil_type | season | rainfall_mm | water_availability | crop | source | sample_weight

    Primary-row cleaning rules (implemented in cleaning.clean_primary_row):
        * consent must be True
        * crop, soil_type, season, water_availability, rainfall_mm required
        * sample_weight: excellent/good -> 1.0, average -> 0.5, poor -> 0.0 (excluded)
    """
    cols = FEATURE_COLUMNS + ["crop", "source", "sample_weight", "N", "P", "K",
                              "temperature", "humidity", "ph", "rainfall"]
    sec = secondary.copy()
    sec["sample_weight"] = 1.0
    # load_secondary() stamps source="secondary_kaggle"; be defensive for hand-built frames
    if "source" in sec.columns:
        sec["source"] = sec["source"].fillna("secondary_kaggle")
    else:
        sec["source"] = "secondary_kaggle"
    frames = [sec.reindex(columns=cols)]
    if primary_rows:
        prim = pd.DataFrame(primary_rows)
        # A primary survey row carries the four REAL observed inputs and no lab chemistry, so
        # the same documented expansion layer used at serving time fills the seven agronomic
        # parameters. The row keeps source='primary_survey', so the assumed values stay
        # traceable and can be replaced by true soil-test values later.
        agro = prim.apply(
            lambda r: expand_to_agronomic(r["soil_type"], r["season"], float(r["rainfall_mm"]),
                                          r["water_availability"]),
            axis=1, result_type="expand")
        for col in AGRO_FEATURES:
            prim[col] = agro[col].to_numpy()
        prim["source"] = prim.get("source", "primary_survey")
        prim["rainfall"] = prim.get("rainfall_mm")
        frames.append(prim.reindex(columns=cols))
    merged = pd.concat(frames, ignore_index=True)
    merged = merged[merged["sample_weight"] > 0]
    return merged.reset_index(drop=True)
