"""
Crop knowledge base + agronomic rule scoring + natural-language reason generation.

WHY THIS FILE EXISTS
--------------------
The ML model alone can only output a class label and a probability. For a farmer or a
KVK officer, "rice — 0.72" is useless without an agronomic *why*. This module holds a
small, curated, cited knowledge base for every crop the system can output, and turns
each recommendation into (a) a transparent rule-fit score and (b) a short reason that is
assembled from those stored facts (never invented at request time).

SCALE NOTE
----------
`rainfall_monthly` is on the SAME scale as the secondary dataset's `rainfall` column
(growing-window monthly rainfall in mm, roughly 20-300 mm). `total_water_mm` is the
published seasonal crop water requirement, quoted from the source, and is used only in
the explanation text.

SOURCES (compiled, indicative — always confirm locally with the KVK):
  [1] TNAU Crop Production Guide / Agritech Portal (agritech.tnau.ac.in) - climate and
      water requirement tables per crop.
  [2] ICAR / KVK Dakshina Kannada district profile (kvkdk.org) - DK rainfall, soils,
      crop areas (paddy 48,689 ha; arecanut 35,409 ha; coconut 18,467 ha in 2022-23).
  [3] Kaggle "Crop Recommendation Dataset" (atharvaingle) - the secondary dataset, whose
      2200 rows define the modelled label space of 22 crops.
"""

from __future__ import annotations

import math
from typing import Any

MODEL_CROP_LABELS = [
    "apple", "banana", "blackgram", "chickpea", "coconut", "coffee", "cotton", "grapes",
    "jute", "kidneybeans", "lentil", "maize", "mango", "mothbeans", "mungbean",
    "muskmelon", "orange", "papaya", "pigeonpeas", "pomegranate", "rice", "watermelon",
]

DK_NOTE = "Cultivated in Dakshina Kannada"
SOURCE_KVK = "KVK Dakshina Kannada district profile / annual report (kvkdk.org)"
SOURCE_TNAU = "TNAU Agritech Portal & Crop Production Guide (agritech.tnau.ac.in)"
SOURCE_KC = "ICAR / package-of-practices, indicative range"

# fmt: off
CROPS: dict[str, dict[str, Any]] = {
    "rice": dict(
        kn="ಭತ್ತ", en_name="Rice / Paddy", category="cereal",
        seasons=["Kharif", "Rabi"], soils=["laterite", "alluvial", "red_loam", "coastal_saline"],
        water_need="high", rainfall_monthly=(100, 300), total_water_mm="1200-1400 mm for transplanted rice",
        ph=(5.0, 7.5), temp=(20, 36), duration_days=110, dk_local=True,
        note="Largest food crop of Dakshina Kannada (48,689 ha in 2022-23).",
        source=SOURCE_KVK, source_url="https://www.kvkdk.org/district_profile.html"),
    "maize": dict(
        kn="ಮೆಕ್ಕೆಜೋಳ", en_name="Maize", category="cereal",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["red_loam", "laterite", "alluvial", "black"],
        water_need="medium", rainfall_monthly=(55, 200), total_water_mm="500-800 mm per season",
        ph=(5.5, 7.5), temp=(18, 33), duration_days=100, dk_local=True,
        note="Grown as a rainfed kharif crop and as a rabi/summer crop in the district's uplands.",
        source=SOURCE_KC, source_url=None),
    "finger_millet": dict(
        kn="ರಾಗಿ", en_name="Finger millet (Ragi)", category="cereal",
        seasons=["Kharif", "Rabi"], soils=["laterite", "red_loam"], water_need="low",
        rainfall_monthly=(40, 150), total_water_mm="330-400 mm per season",
        ph=(5.0, 7.0), temp=(20, 32), duration_days=105, dk_local=True,
        note="Drought-hardy millet; district acreage is modest but rising under the State Millet Mission.",
        source=SOURCE_KC, source_url=None,
        kb_only=True,
    ),
    "blackgram": dict(
        kn="ಉದ್ದು", en_name="Black gram (Uddina bele)", category="pulse",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["alluvial", "black", "red_loam", "laterite"],
        water_need="low", rainfall_monthly=(25, 120), total_water_mm="250-350 mm per season",
        ph=(6.0, 8.0), temp=(25, 35), duration_days=70, dk_local=True,
        note="Sown in rabi and summer in paddy fallows of the coastal belt.",
        source=SOURCE_KVK, source_url="https://www.kvkdk.org/district_profile.html"),
    "mungbean": dict(
        kn="ಹೆಸರು", en_name="Green gram (Hesaru)", category="pulse",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["alluvial", "black", "red_loam"],
        water_need="low", rainfall_monthly=(20, 120), total_water_mm="200-300 mm per season",
        ph=(6.0, 8.0), temp=(25, 35), duration_days=65, dk_local=True,
        note="Short-duration pulse used in paddy-fallow rotations and as an intercrop.",
        source=SOURCE_KC, source_url=None),
    "cowpea": dict(
        kn="ಅಲಸಂದೆ", en_name="Cowpea (Alsande)", category="pulse",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["laterite", "red_loam", "alluvial", "coastal_sandy"],
        water_need="low", rainfall_monthly=(30, 140), total_water_mm="300-400 mm per season",
        ph=(5.5, 8.0), temp=(20, 35), duration_days=70, dk_local=True,
        note="Popular vegetable pulse in coastal kitchen gardens and paddy bunds.",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "horsegram": dict(
        kn="ಹುರಳಿ", en_name="Horse gram (Hurali)", category="pulse",
        seasons=["Rabi", "Zaid"], soils=["laterite", "red_loam"], water_need="low",
        rainfall_monthly=(20, 90), total_water_mm="200-300 mm per season",
        ph=(5.5, 7.5), temp=(20, 33), duration_days=90, dk_local=True,
        note="Grown on residual moisture in paddy fallows after the monsoon.",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "chickpea": dict(
        kn="ಕಡಲೆ", en_name="Chickpea (Kadale)", category="pulse",
        seasons=["Rabi"], soils=["black", "red_loam", "alluvial"], water_need="low",
        rainfall_monthly=(20, 100), total_water_mm="250-350 mm per season",
        ph=(6.0, 8.0), temp=(15, 30), duration_days=95, dk_local=False,
        note="Rabi pulse; marginal in high-rainfall coastal DK — better in the eastern dry taluks.",
        source=SOURCE_KC, source_url=None),
    "pigeonpeas": dict(
        kn="ತೊಗರಿ", en_name="Pigeon pea (Togari)", category="pulse",
        seasons=["Kharif"], soils=["black", "red_loam", "alluvial"], water_need="low",
        rainfall_monthly=(50, 180), total_water_mm="400-600 mm per season",
        ph=(5.5, 8.0), temp=(20, 33), duration_days=150, dk_local=False,
        note="Long-duration kharif pulse, mostly a Deccan crop; limited in coastal DK.",
        source=SOURCE_KC, source_url=None),
    "lentil": dict(
        kn="ಮಸೂರ", en_name="Lentil", category="pulse",
        seasons=["Rabi"], soils=["black", "alluvial", "red_loam"], water_need="low",
        rainfall_monthly=(20, 90), total_water_mm="250-350 mm per season",
        ph=(6.0, 8.0), temp=(15, 28), duration_days=100, dk_local=False,
        note="Cool-season pulse; not a mainstream crop in coastal Karnataka.",
        source=SOURCE_KC, source_url=None),
    "kidneybeans": dict(
        kn="ರಾಜ್ಮಾ", en_name="Kidney beans (Rajma)", category="pulse",
        seasons=["Kharif"], soils=["red_loam", "alluvial"], water_need="medium",
        rainfall_monthly=(60, 180), total_water_mm="400-500 mm per season",
        ph=(5.5, 7.5), temp=(15, 27), duration_days=110, dk_local=False,
        note="Hilly temperate-zone pulse; rarely grown in the coastal plains.",
        source=SOURCE_KC, source_url=None),
    "mothbeans": dict(
        kn="ಮಠ್ ಬೀನ್ಸ್", en_name="Moth bean", category="pulse",
        seasons=["Kharif"], soils=["coastal_sandy", "red_loam", "black"], water_need="low",
        rainfall_monthly=(20, 70), total_water_mm="200-250 mm per season",
        ph=(6.0, 8.5), temp=(25, 38), duration_days=70, dk_local=False,
        note="Extreme drought tolerance; a arid-zone crop, not typical of high-rainfall DK.",
        source=SOURCE_KC, source_url=None),
    "coconut": dict(
        kn="ತೆಂಗು", en_name="Coconut", category="plantation",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["coastal_sandy", "laterite", "red_loam", "alluvial"],
        water_need="medium", rainfall_monthly=(60, 250), total_water_mm="annual rainfall 1000-3000 mm; weekly irrigation Nov-Feb",
        ph=(5.0, 8.0), temp=(20, 35), duration_days=1460, dk_local=True,
        note="18,467 ha in Dakshina Kannada (2022-23); backbone of the coastal homestead garden.",
        source=SOURCE_KVK, source_url="https://www.kvkdk.org/district_profile.html"),
    "arecanut": dict(
        kn="ಅಡಿಕೆ", en_name="Arecanut (Adike)", category="plantation",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["laterite", "red_loam", "alluvial"],
        water_need="high", rainfall_monthly=(60, 300), total_water_mm="annual rainfall 750-4500 mm; sensitive to moisture deficit",
        ph=(5.0, 7.5), temp=(15, 38), duration_days=1825, dk_local=True,
        note="Second-largest crop of the district (35,409 ha in 2022-23); thrives on lateritic soils.",
        source=SOURCE_TNAU, source_url="https://agritech.tnau.ac.in/horticulture/horti_plantation%20crops_arecanut.html",
        kb_only=True,
    ),
    "cashew": dict(
        kn="ಗೋಡಂಬಿ", en_name="Cashew", category="plantation",
        seasons=["Kharif", "Rabi"], soils=["laterite", "coastal_sandy", "red_loam"], water_need="low",
        rainfall_monthly=(40, 200), total_water_mm="annual rainfall 500-3500 mm (rainfed)",
        ph=(5.0, 7.5), temp=(20, 36), duration_days=1095, dk_local=True,
        note="Traditional coastal plantation crop of DK, tolerant of poor lateritic soils.",
        source=SOURCE_TNAU, source_url=None, kb_only=True),
    "black_pepper": dict(
        kn="ಕಾಳುಮೆಣಸು", en_name="Black pepper", category="spice",
        seasons=["Kharif", "Rabi"], soils=["laterite", "red_loam"], water_need="high",
        rainfall_monthly=(100, 300), total_water_mm="annual rainfall 1250-4000 mm",
        ph=(5.5, 7.0), temp=(20, 32), duration_days=730, dk_local=True,
        note="Grown as a climber on arecanut and coconut in the district's mixed gardens.",
        source=SOURCE_TNAU, source_url=None, kb_only=True),
    "cocoa": dict(
        kn="ಕೋಕೋ", en_name="Cocoa", category="plantation",
        seasons=["Kharif", "Rabi"], soils=["laterite", "alluvial", "red_loam"], water_need="high",
        rainfall_monthly=(80, 250), total_water_mm="annual rainfall 1250-3000 mm",
        ph=(6.0, 7.5), temp=(20, 32), duration_days=1095, dk_local=True,
        note="Helps offset arecanut price risk; promoted as an intercrop in DK plantations.",
        source=SOURCE_TNAU, source_url=None, kb_only=True),
    "rubber": dict(
        kn="ರಬ್ಬರ್", en_name="Rubber", category="plantation",
        seasons=["Kharif"], soils=["laterite", "red_loam"], water_need="high",
        rainfall_monthly=(150, 300), total_water_mm="annual rainfall > 2000 mm",
        ph=(4.5, 6.5), temp=(20, 34), duration_days=2190, dk_local=True,
        note="Confined to the humid eastern belt of the district (Sullia / Belthangady side).",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "jackfruit": dict(
        kn="ಹಲಸು", en_name="Jackfruit", category="fruit",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["laterite", "red_loam", "alluvial"], water_need="medium",
        rainfall_monthly=(60, 250), total_water_mm="annual rainfall 1000-2400 mm",
        ph=(5.5, 7.5), temp=(20, 35), duration_days=1460, dk_local=True,
        note="Household and commercial crop; strong local processing demand (halasina hannu value chain).",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "banana": dict(
        kn="ಬಾಳೆ", en_name="Banana", category="fruit",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["alluvial", "red_loam", "laterite"], water_need="high",
        rainfall_monthly=(80, 250), total_water_mm="1500-2500 mm per crop cycle (irrigated)",
        ph=(6.0, 7.5), temp=(20, 35), duration_days=330, dk_local=True,
        note="Grown across the coastal belt with assured irrigation; high water demand.",
        source=SOURCE_TNAU, source_url=None),
    "mango": dict(
        kn="ಮಾವು", en_name="Mango", category="fruit",
        seasons=["Zaid", "Kharif"], soils=["laterite", "red_loam", "alluvial"], water_need="low",
        rainfall_monthly=(30, 200), total_water_mm="annual rainfall 750-2500 mm; dry spell at flowering is desirable",
        ph=(5.5, 7.5), temp=(20, 38), duration_days=1460, dk_local=True,
        note="Homestead and commercial orchard crop; flower induction needs a dry spell.",
        source=SOURCE_TNAU, source_url=None),
    "papaya": dict(
        kn="ಪಪ್ಪಾಯಿ", en_name="Papaya", category="fruit",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["alluvial", "red_loam", "coastal_sandy"], water_need="medium",
        rainfall_monthly=(60, 200), total_water_mm="1200-1500 mm per cycle; very sensitive to waterlogging",
        ph=(6.0, 7.5), temp=(22, 35), duration_days=270, dk_local=True,
        note="Short-cycle fruit suited to well-drained coastal soils; drains must be cut in the monsoon.",
        source=SOURCE_TNAU, source_url=None),
    "watermelon": dict(
        kn="ಕಲ್ಲಂಗಡಿ", en_name="Watermelon", category="fruit",
        seasons=["Zaid"], soils=["coastal_sandy", "alluvial", "red_loam"], water_need="medium",
        rainfall_monthly=(25, 120), total_water_mm="400-600 mm per crop (drip)",
        ph=(5.5, 7.5), temp=(24, 38), duration_days=95, dk_local=True,
        note="Summer (Zaid) cash crop on river-bank sandy soils; summer paddy-fallow rotation.",
        source=SOURCE_KC, source_url=None),
    "muskmelon": dict(
        kn="ಕರ್ಬೂಜ", en_name="Muskmelon", category="fruit",
        seasons=["Zaid"], soils=["coastal_sandy", "alluvial"], water_need="medium",
        rainfall_monthly=(25, 100), total_water_mm="350-550 mm per crop (drip)",
        ph=(6.0, 7.5), temp=(24, 38), duration_days=90, dk_local=True,
        note="Summer melon; needs dry weather at ripening, so Zaid is the only suitable window.",
        source=SOURCE_KC, source_url=None),
    "pineapple": dict(
        kn="ಅನಾನಸ್", en_name="Pineapple", category="fruit",
        seasons=["Kharif", "Rabi"], soils=["laterite", "red_loam"], water_need="medium",
        rainfall_monthly=(80, 250), total_water_mm="annual rainfall 1000-2500 mm",
        ph=(4.5, 6.5), temp=(20, 33), duration_days=540, dk_local=True,
        note="Acid-soil loving fruit; well matched to DK's lateritic soils.",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "pomegranate": dict(
        kn="ದಾಳಿಂಬೆ", en_name="Pomegranate", category="fruit",
        seasons=["Rabi", "Kharif"], soils=["black", "red_loam"], water_need="low",
        rainfall_monthly=(25, 120), total_water_mm="drip; sensitive to waterlogging and high humidity",
        ph=(6.5, 8.0), temp=(20, 38), duration_days=1095, dk_local=False,
        note="Arid/semi-arid fruit; high coastal humidity raises bacterial blight risk.",
        source=SOURCE_KC, source_url=None),
    "grapes": dict(
        kn="ದ್ರಾಕ್ಷಿ", en_name="Grapes", category="fruit",
        seasons=["Rabi", "Zaid"], soils=["black", "red_loam"], water_need="medium",
        rainfall_monthly=(25, 120), total_water_mm="500-800 mm per pruning cycle (drip)",
        ph=(6.5, 8.0), temp=(15, 38), duration_days=180, dk_local=False,
        note="Needs a dry, low-humidity ripening window; not recommended for coastal DK.",
        source=SOURCE_KC, source_url=None),
    "orange": dict(
        kn="ಕಿತ್ತಳೆ", en_name="Orange / Citrus", category="fruit",
        seasons=["Kharif", "Rabi"], soils=["red_loam", "laterite", "alluvial"], water_need="medium",
        rainfall_monthly=(60, 200), total_water_mm="annual rainfall 900-2000 mm",
        ph=(5.5, 7.5), temp=(15, 35), duration_days=1095, dk_local=False,
        note="Citrus needs good drainage; fruit fly pressure is high in humid coastal tracts.",
        source=SOURCE_KC, source_url=None),
    "apple": dict(
        kn="ಸೇಬು", en_name="Apple", category="fruit",
        seasons=["Rabi"], soils=["alluvial", "red_loam"], water_need="medium",
        rainfall_monthly=(30, 150), total_water_mm="900-1200 mm but requires 1000+ chilling hours",
        ph=(5.5, 7.0), temp=(5, 25), duration_days=1500, dk_local=False,
        note="Temperate fruit requiring winter chilling — NOT agronomically viable in coastal DK; "
             "kept in the label space because the secondary dataset contains it.",
        source=SOURCE_KC, source_url=None),
    "cotton": dict(
        kn="ಹತ್ತಿ", en_name="Cotton", category="fibre",
        seasons=["Kharif"], soils=["black", "red_loam"], water_need="medium",
        rainfall_monthly=(50, 200), total_water_mm="700-1200 mm per season",
        ph=(6.0, 8.5), temp=(21, 35), duration_days=180, dk_local=False,
        note="Black-soil kharif crop of the Deccan; unsuitable on DK's acidic laterites.",
        source=SOURCE_KC, source_url=None),
    "jute": dict(
        kn="ಸೆಣಬು", en_name="Jute", category="fibre",
        seasons=["Kharif"], soils=["alluvial"], water_need="high",
        rainfall_monthly=(100, 300), total_water_mm="1000-1500 mm per season",
        ph=(6.0, 7.5), temp=(24, 37), duration_days=120, dk_local=False,
        note="Requires fertile alluvial flood plains; a Gangetic-basin crop.",
        source=SOURCE_KC, source_url=None),
    "sugarcane": dict(
        kn="ಕಬ್ಬು", en_name="Sugarcane", category="cash",
        seasons=["Kharif", "Zaid"], soils=["alluvial", "black", "red_loam"], water_need="high",
        rainfall_monthly=(80, 250), total_water_mm="1800-2500 mm per crop (irrigated)",
        ph=(6.0, 8.0), temp=(20, 38), duration_days=330, dk_local=False,
        note="Very high water and long duration; DK is not a notified sugarcane belt.",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "coffee": dict(
        kn="ಕಾಫಿ", en_name="Coffee", category="plantation",
        seasons=["Kharif", "Rabi"], soils=["laterite", "red_loam"], water_need="medium",
        rainfall_monthly=(80, 250), total_water_mm="annual rainfall 1000-2500 mm",
        ph=(5.0, 6.5), temp=(15, 30), duration_days=1095, dk_local=True,
        note="Grown only in the higher eastern taluks (Sullia / Belthangady) of the district.",
        source=SOURCE_KC, source_url=None),
    "groundnut": dict(
        kn="ಶೇಂಗಾ", en_name="Groundnut", category="oilseed",
        seasons=["Kharif", "Rabi", "Zaid"], soils=["coastal_sandy", "red_loam", "laterite"], water_need="low",
        rainfall_monthly=(40, 150), total_water_mm="500-700 mm per season",
        ph=(6.0, 7.5), temp=(20, 35), duration_days=110, dk_local=True,
        note="Upland oilseed suited to light red and sandy soils of the district.",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "sesame": dict(
        kn="ಎಳ್ಳು", en_name="Sesame (Ellu)", category="oilseed",
        seasons=["Kharif", "Zaid"], soils=["coastal_sandy", "red_loam", "black"], water_need="low",
        rainfall_monthly=(25, 100), total_water_mm="300-400 mm per season",
        ph=(5.5, 8.0), temp=(25, 38), duration_days=85, dk_local=True,
        note="Short-duration oilseed used in summer paddy fallows.",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "ginger": dict(
        kn="ಶುಂಠಿ", en_name="Ginger", category="spice",
        seasons=["Kharif"], soils=["laterite", "red_loam", "alluvial"], water_need="high",
        rainfall_monthly=(100, 300), total_water_mm="1500-2000 mm per crop",
        ph=(5.5, 7.0), temp=(19, 32), duration_days=240, dk_local=True,
        note="High-value spice; needs heavy rainfall with assured drainage to avoid rhizome rot.",
        source=SOURCE_KC, source_url=None, kb_only=True),
    "turmeric": dict(
        kn="ಅರಿಶಿನ", en_name="Turmeric", category="spice",
        seasons=["Kharif"], soils=["laterite", "red_loam", "alluvial"], water_need="high",
        rainfall_monthly=(90, 280), total_water_mm="1200-1600 mm per crop",
        ph=(5.5, 7.5), temp=(20, 32), duration_days=250, dk_local=True,
        note="Grown in the district's mixed gardens; cured turmeric has steady local demand.",
        source=SOURCE_KC, source_url=None, kb_only=True),
}
# fmt: on

# Crops that the ML model can output (everything else in CROPS is knowledge-base only).
KB_ONLY_CROPS = sorted(set(CROPS) - set(MODEL_CROP_LABELS))

WATER_ORDER = {"low": 0, "medium": 1, "high": 2}

# Crops that suffer badly from standing water / excess monsoon rain in a high-rainfall
# coastal district: their rule score is penalised when reported rainfall exceeds the top of
# their band. Agronomic basis: these crops are documented as drainage-sensitive (papaya,
# melons, grapes, pomegranate, citrus, ginger/turmeric rhizome rot, pepper/cocoa on
# waterlogged laterite) in the ICAR/TNAU package-of-practices material cited above.
WATERLOGGING_SENSITIVE = {"papaya", "muskmelon", "watermelon", "grapes", "pomegranate",
                          "orange", "ginger", "turmeric", "black_pepper", "cocoa"}
WATERLOGGING_PENALTY = 0.6

RULE_WEIGHTS = {"water": 0.30, "season": 0.25, "rain": 0.25, "soil": 0.20}
# Blending: geometric (multiplicative) mean, so a crop whose agronomic rule fit is poor
# cannot win on a high model probability alone. Documented in docs/dataset_schema.md and
# shown in the UI on every card.
MODEL_EXPONENT = 0.55
RULE_EXPONENT = 0.45


def _water_match(need: str, have: str) -> float:
    gap = abs(WATER_ORDER.get(need, 1) - WATER_ORDER.get(have, 1))
    return {0: 1.0, 1: 0.45, 2: 0.05}.get(gap, 0.05)


def _season_match(seasons: list[str], season: str) -> float:
    return 1.0 if season in seasons else 0.15


def _range_match(band: tuple[float, float], value: float) -> float:
    lo, hi = band
    if lo <= value <= hi:
        return 1.0
    width = max(hi - lo, 1.0)
    if value < lo:
        return max(0.0, 1.0 - (lo - value) / width)
    return max(0.0, 1.0 - (value - hi) / width)


def score_kb(kb: dict, soil_type: str, season: str, rainfall_mm: float,
             water_availability: str, regional_tuning: bool = False) -> dict:
    """Transparent agronomic fitness score in [0, 1] for ANY kb-shaped dict.

    kb dicts come either from the built-in CROPS table or from an admin-edited
    `crop_references` row (models.CropReference.kb_view()), so admins can genuinely
    change how the rule-fit part of the ranking behaves.
    """
    comps = {
        "water": _water_match(kb["water_need"], water_availability),
        "season": _season_match(kb["seasons"], season),
        "rain": _range_match(kb["rainfall_monthly"], float(rainfall_mm)),
        "soil": 1.0 if soil_type in kb["soils"] else 0.2,
    }
    score = sum(RULE_WEIGHTS[k] * v for k, v in comps.items())
    penalised = False
    slug = kb.get("en_name", "").lower().strip().replace(" ", "_").split("(")[0].strip("_")
    if rainfall_mm > kb["rainfall_monthly"][1] and slug in WATERLOGGING_SENSITIVE:
        score *= WATERLOGGING_PENALTY
        penalised = True
    if regional_tuning and kb.get("dk_local"):
        score = min(1.0, score * 1.08)          # regional bonus: crop is actually grown here
    return {"score": round(score, 4),
            "components": {k: round(v, 3) for k, v in comps.items()},
            "waterlogging_penalised": penalised, "kb": kb}


def rule_score(crop: str, soil_type: str, season: str, rainfall_mm: float,
               water_availability: str, regional_tuning: bool = False) -> dict:
    """Convenience wrapper over score_kb() for the built-in knowledge base."""
    kb = CROPS.get(crop)
    if not kb:
        return {"score": 0.0, "components": {}, "kb": None}
    return score_kb(kb, soil_type, season, rainfall_mm, water_availability, regional_tuning)


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def build_reasons(crop: str, soil_type: str, season: str, rainfall_mm: float,
                  water_availability: str, components: dict, regional_tuning: bool = False,
                  model_prob: float | None = None, kb_entry: dict | None = None) -> list[str]:
    """Assemble short, factual reasons from the knowledge base (no invented numbers)."""
    kb = kb_entry or CROPS[crop]
    reasons: list[str] = []

    # 1. Season
    if components.get("season", 0) == 1.0:
        reasons.append(f"{kb['en_name']} is a {', '.join(kb['seasons'])} crop, matching your {season} season.")
    else:
        reasons.append(f"Caution: {kb['en_name']} is normally a {', '.join(kb['seasons'])} crop — "
                       f"your {season} season is outside its usual window.")

    # 2. Water
    if components.get("water", 0) == 1.0:
        reasons.append(f"Its {kb['water_need']} water need matches your reported {water_availability} water availability "
                       f"({kb['total_water_mm']}).")
    else:
        reasons.append(f"Water mismatch: it typically needs {kb['water_need']} water, you reported {water_availability}. "
                       f"Reference requirement: {kb['total_water_mm']}.")

    # 3. Rainfall
    lo, hi = kb["rainfall_monthly"]
    if components.get("rain", 0) == 1.0:
        reasons.append(f"Your {_fmt(rainfall_mm)} mm growing-window rainfall falls inside its {_fmt(lo)}–{_fmt(hi)} mm band.")
    else:
        reasons.append(f"Rainfall fit is partial: {_fmt(rainfall_mm)} mm vs a typical {_fmt(lo)}–{_fmt(hi)} mm band "
                       f"for this crop.")

    # 4. Soil
    readable = ", ".join(s.replace("_", " ") for s in kb["soils"])
    if components.get("soil", 0) == 1.0:
        reasons.append(f"{soil_type.replace('_', ' ').title()} soil is in its suitable soil list ({readable}); "
                       f"tolerates pH {_fmt(kb['ph'][0])}–{_fmt(kb['ph'][1])}.")
    else:
        reasons.append(f"Soil is a weak point: {soil_type.replace('_', ' ')} is not among its usual soils "
                       f"({readable}), pH {_fmt(kb['ph'][0])}–{_fmt(kb['ph'][1])}.")

    # 5. Regional note
    if kb.get("dk_local"):
        tag = "regional tuning is ON" if regional_tuning else "regional tuning is OFF"
        reasons.append(f"Regional note: {kb['note']} ({tag}).")
    else:
        reasons.append(f"Regional note: {kb['note']}")

    return reasons


def advisories(crop: str, rainfall_mm: float, water_availability: str, components: dict,
               kb_entry: dict | None = None) -> list[str]:
    """Field cautions shown under the recommendation card."""
    kb = kb_entry or CROPS[crop]
    out: list[str] = []
    if rainfall_mm > kb["rainfall_monthly"][1] * 1.25 and kb["water_need"] != "high":
        out.append("Excess-rainfall risk: ensure drainage / raised beds to avoid waterlogging.")
    if water_availability == "low" and kb["water_need"] == "high":
        out.append("Assured irrigation is essential for this crop in your profile — do not rely on rainfall alone.")
    if components.get("season", 1.0) < 1.0:
        out.append("Off-season sowing: expect yield penalty; validate with your local KVK before planting.")
    if kb["water_need"] == "high":
        out.append("Water-intensive choice: budget irrigation for the full duration "
                   f"({kb['duration_days']} days).")
    return out


def kb_summary(crop: str) -> dict:
    kb = CROPS[crop]
    return {
        "crop": crop,
        "name": kb["en_name"],
        "name_kn": kb["kn"],
        "category": kb["category"],
        "seasons": kb["seasons"],
        "soils": kb["soils"],
        "water_need": kb["water_need"],
        "rainfall_monthly_mm": list(kb["rainfall_monthly"]),
        "total_water_mm": kb["total_water_mm"],
        "ph": list(kb["ph"]),
        "temp_c": list(kb["temp"]),
        "duration_days": kb["duration_days"],
        "dk_local": bool(kb.get("dk_local")),
        "note": kb["note"],
        "source": kb["source"],
        "source_url": kb.get("source_url"),
        "in_model_label_space": crop in MODEL_CROP_LABELS,
        "kb_only": bool(kb.get("kb_only", crop not in MODEL_CROP_LABELS)),
    }


def haversine_placeholder() -> float:  # pragma: no cover - kept for API symmetry
    return math.nan
