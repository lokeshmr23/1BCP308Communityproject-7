"""Shared controlled vocabularies for the Crop Advisor API (English + Kannada labels)."""

SOIL_TYPES = [
    {"value": "laterite", "label": "Laterite (red lateritic)", "label_kn": "ಜಂಬಿಟ್ಟಿಗೆ ಮಣ್ಣು",
     "hint": "Dominant soil of Dakshina Kannada; acidic, iron-rich, well drained."},
    {"value": "red_loam", "label": "Red loam", "label_kn": "ಕೆಂಪು ಮಣ್ಣು",
     "hint": "Moderately acidic, medium fertility, good for most field crops."},
    {"value": "alluvial", "label": "Alluvial (valley / river bank)", "label_kn": "ಮೆಕ್ಕಲು ಮಣ್ಣು",
     "hint": "Fertile transported soil along river banks and valleys."},
    {"value": "coastal_sandy", "label": "Coastal sandy", "label_kn": "ಕರಾವಳಿ ಮರಳು ಮಣ್ಣು",
     "hint": "Light, low water-holding, near-neutral; coconut belt of the coast."},
    {"value": "black", "label": "Black (clay / vertisol)", "label_kn": "ಕಪ್ಪು ಮಣ್ಣು",
     "hint": "High moisture retention; rare in DK (~5%), common in Deccan."},
    {"value": "coastal_saline", "label": "Coastal saline", "label_kn": "ಉಪ್ಪು ಮಣ್ಣು",
     "hint": "Near backwaters/estuaries; salinity risk, salt-tolerant crops only."},
]

SEASONS = [
    {"value": "Kharif", "label": "Kharif (Jun–Oct, monsoon)", "label_kn": "ಖಾರಿಫ್ (ಮುಂಗಾರು)",
     "months": "Jun-Oct"},
    {"value": "Rabi", "label": "Rabi (Oct/Nov–Mar, post-monsoon)", "label_kn": "ರಬಿ (ಹಿಂಗಾರು)",
     "months": "Oct-Mar"},
    {"value": "Zaid", "label": "Zaid (Mar–Jun, summer)", "label_kn": "ಝೈದ್ (ಬೇಸಿಗೆ)",
     "months": "Mar-Jun"},
]

WATER_LEVELS = [
    {"value": "low", "label": "Low — rainfed only", "label_kn": "ಕಡಿಮೆ — ಮಳೆ ಆಧಾರಿತ"},
    {"value": "medium", "label": "Medium — partial irrigation / well", "label_kn": "ಮಧ್ಯಮ — ಬಾವಿ/ಬೋರ್‌ವೆಲ್"},
    {"value": "high", "label": "High — assured irrigation", "label_kn": "ಹೆಚ್ಚು — ಖಾತರಿ ನೀರಾವರಿ"},
]

# Irrigation source -> water availability proxy level (documented in docs/dataset_schema.md)
IRRIGATION_SOURCES = [
    {"value": "rainfed", "label": "Rainfed only (no irrigation)", "label_kn": "ಮಳೆ ಆಧಾರಿತ", "level": "low"},
    {"value": "open_well", "label": "Open well", "label_kn": "ತೆರೆದ ಬಾವಿ", "level": "medium"},
    {"value": "borewell", "label": "Borewell", "label_kn": "ಬೋರ್‌ವೆಲ್", "level": "medium"},
    {"value": "drip_micro", "label": "Drip / micro irrigation", "label_kn": "ಹನಿ ನೀರಾವರಿ", "level": "medium"},
    {"value": "tank", "label": "Tank / pond", "label_kn": "ಕೆರೆ / ಕೊಳ", "level": "high"},
    {"value": "canal", "label": "Canal", "label_kn": "ಕಾಲುವೆ", "level": "high"},
    {"value": "river_lift", "label": "River lift irrigation", "label_kn": "ನದಿ ನೀರಾವರಿ", "level": "high"},
]

TALUKS = [
    {"value": "Mangaluru", "label": "Mangaluru", "label_kn": "ಮಂಗಳೂರು"},
    {"value": "Ullal", "label": "Ullal", "label_kn": "ಉಳ್ಳಾಲ"},
    {"value": "Mulki", "label": "Mulki", "label_kn": "ಮುಲ್ಕಿ"},
    {"value": "Moodabidri", "label": "Moodabidri", "label_kn": "ಮೂಡಬಿದರೆ"},
    {"value": "Bantwal", "label": "Bantwal", "label_kn": "ಬಂಟ್ವಾಳ"},
    {"value": "Belthangady", "label": "Belthangady", "label_kn": "ಬೆಳ್ತಂಗಡಿ"},
    {"value": "Puttur", "label": "Puttur", "label_kn": "ಪುತ್ತೂರು"},
    {"value": "Sullia", "label": "Sullia", "label_kn": "ಸುಳ್ಯ"},
    {"value": "Kadaba", "label": "Kadaba", "label_kn": "ಕಡಬ"},
    {"value": "Other (outside DK)", "label": "Other (outside DK)", "label_kn": "ಇತರೆ"},
]

YIELD_OUTCOMES = [
    {"value": "poor", "label": "Poor (< 50% of expected)", "label_kn": "ಕಳಪೆ",
     "sample_weight": 0.0, "excluded": True},
    {"value": "average", "label": "Average (~50–80%)", "label_kn": "ಸಾಧಾರಣ",
     "sample_weight": 0.5, "excluded": False},
    {"value": "good", "label": "Good (80–100%)", "label_kn": "ಉತ್ತಮ",
     "sample_weight": 1.0, "excluded": False},
    {"value": "excellent", "label": "Excellent (> 100% / better than usual)", "label_kn": "ಅತ್ಯುತ್ತಮ",
     "sample_weight": 1.0, "excluded": False},
]

ROLES = ["farmer", "admin"]

# District-level rainfall presets used to pre-fill the form (sourced, see docs).
RAINFALL_PRESETS = [
    {"label": "DK monsoon month (Jun–Sep, typical)", "value": 220, "kn": "ಮುಂಗಾರು ತಿಂಗಳು"},
    {"label": "DK post-monsoon (Oct–Nov)", "value": 90, "kn": "ಹಿಂಗಾರು"},
    {"label": "DK dry season (Dec–May)", "value": 25, "kn": "ಬೇಸಿಗೆ"},
    {"label": "Drier interior taluk (Sullia/Kadaba side)", "value": 140, "kn": "ಒಳನಾಡು"},
]
