"""
Model registry: lazy loading + the recommendation serving path.

Design points that matter for a free-tier deployment (Render free web service):
  * the model is NOT loaded at import time. `load()` is called on the first prediction
    request (thread-safe, single attempt) so the web service boots fast and cold starts
    stay short;
  * the artefact is small (~0.7 MB, joblib compress=3) because it lives in the Git repo —
    Render's free disk is ephemeral, so nothing important may live on the filesystem;
  * if the artefact is missing, the registry trains it on the fly from the bundled CSV
    (documented, ~12 s) instead of failing the request.

Serving path (documented on the About page):
    4 collected inputs
      -> expand_to_agronomic()          (documented typical soil/season profiles)
      -> best model <= .predict_proba() (probability over the 22 model crops)
      -> score_kb()                     (transparent agronomic rule fit)
      -> blended = 0.65 * probability + 0.35 * rule fit
      -> top-3 with reasons, warnings, and the input-expansion audit trail
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from ..config import Config
from . import knowledge as kb
from .features import (AGRO_FEATURES, expand_to_agronomic, expansion_explanation)

log = logging.getLogger(__name__)

# Suitability score = model_probability^0.55 x rule_fit^0.45, then a small prior for crops
# actually grown in Dakshina Kannada when regional tuning is on. A geometric (rather than
# additive) blend means a crop with a poor agronomic rule fit cannot be carried to the top
# of the list by a high model probability alone.
MODEL_EXPONENT = 0.55
RULE_EXPONENT = 0.45
# Regional tuning acts in BOTH directions, and both are documented in the UI:
#   * crops documented as grown in Dakshina Kannada get a small lift  (x1.05)
#   * crops documented as not viable / not grown here (apple needs winter chilling;
#     cotton, grapes, pomegranate, mothbean are Deccan or arid-zone crops) get demoted (x0.90)
REGIONAL_PRIOR = 1.05
REGIONAL_DEMOTION = 0.90
# Bands calibrated on the observed range of the geometric blend (0.20-0.85 for realistic DK
# profiles): a "strong" pick is one where both the model and the agronomic rules agree.
STRONG_THRESHOLD = 0.55
REASONABLE_THRESHOLD = 0.35
LOW_CONFIDENCE_THRESHOLD = REASONABLE_THRESHOLD


class ModelRegistry:
    def __init__(self, model_path=Config.MODEL_PATH) -> None:
        self.model_path = str(model_path)
        self._artifact: dict | None = None
        self._lock = threading.Lock()
        self._load_error: str | None = None
        self._loaded_at: float | None = None
        self._kb_cache: dict[str, dict] = {}
        self._kb_cache_at: float = 0.0

    # ------------------------------------------------------------------ loading
    @property
    def is_loaded(self) -> bool:
        return self._artifact is not None

    def load(self, force: bool = False) -> dict:
        if self._artifact is not None and not force:
            return self._artifact
        with self._lock:
            if self._artifact is not None and not force:
                return self._artifact
            import os
            if not os.path.exists(self.model_path):
                log.warning("Model artefact missing at %s - training on the fly (cold start path)",
                            self.model_path)
                from .train import default_paths, train_and_save
                secondary, out_dir, derived = default_paths()
                train_and_save(secondary, out_dir, derived_out=derived)
            self._artifact = joblib.load(self.model_path)
            self._loaded_at = time.time()
            self._load_error = None
            log.info("Model loaded: %s v%s (%s classes)",
                     self._artifact.get("model_label"), self._artifact.get("model_version"),
                     len(self._artifact.get("classes", [])))
            return self._artifact

    def status(self) -> dict:
        art = self._artifact
        metrics = self.metrics() or {}
        return {
            "loaded": self.is_loaded,
            "lazy": True,
            "model_path": self.model_path,
            "load_error": self._load_error,
            "loaded_seconds_ago": round(time.time() - self._loaded_at, 1) if self._loaded_at else None,
            "model_key": (art or {}).get("model_key"),
            "model_label": (art or {}).get("model_label"),
            "model_version": (art or {}).get("model_version") or metrics.get("model_version"),
            "trained_at": (art or {}).get("trained_at") or metrics.get("trained_at"),
            "n_classes": len((art or {}).get("classes", []) or metrics.get("dataset", {}).get("classes", [])),
            "model_size_kb": metrics.get("artifacts", {}).get("model_size_kb"),
            "blend": {"model_exponent": MODEL_EXPONENT, "rule_exponent": RULE_EXPONENT,
                      "regional_priors": {"local_crops": REGIONAL_PRIOR,
                                          "non_local_crops": REGIONAL_DEMOTION}},
            "bands": {"strong_match": STRONG_THRESHOLD, "reasonable_match": REASONABLE_THRESHOLD},
        }

    @staticmethod
    def metrics() -> dict | None:
        try:
            with open(Config.METRICS_PATH) as fh:
                return json.load(fh)
        except Exception:
            return None

    # ------------------------------------------------------------------ knowledge base
    def effective_kb(self, db=None) -> dict[str, dict]:
        """Built-in knowledge base merged with admin-edited crop reference rows (60 s cache)."""
        if db is None:
            return dict(kb.CROPS)
        if time.time() - self._kb_cache_at < 60 and self._kb_cache:
            return self._kb_cache
        merged = {k: dict(v) for k, v in kb.CROPS.items()}
        try:
            from ..models import CropReference
            for row in db.query(CropReference).filter(CropReference.is_active.is_(True)).all():
                view = row.kb_view()
                view.setdefault("kb_only", row.crop_key not in kb.MODEL_CROP_LABELS)
                merged[row.crop_key] = view
        except Exception as exc:  # pragma: no cover - DB unavailable should not break inference
            log.warning("Could not load crop reference overrides: %s", exc)
        self._kb_cache, self._kb_cache_at = merged, time.time()
        return merged

    def invalidate_kb_cache(self) -> None:
        self._kb_cache_at = 0.0

    # ------------------------------------------------------------------ prediction
    def predict(self, soil_type: str, season: str, rainfall_mm: float,
                water_availability: str, regional_tuning: bool = True,
                top_k: int = 3, db=None) -> dict:
        art = self.load()
        pipeline = art["pipeline"]
        kb_map = self.effective_kb(db)

        agro = expand_to_agronomic(soil_type, season, rainfall_mm, water_availability)
        frame = pd.DataFrame([agro], columns=AGRO_FEATURES)
        proba = pipeline.predict_proba(frame)[0]
        classes = list(pipeline.classes_)
        model_prob = {c: float(p) for c, p in zip(classes, proba)}

        # ---- transparent component scoring over every crop in the knowledge base
        scored = []
        for crop, prob in model_prob.items():
            entry = kb_map.get(crop)
            if not entry:
                continue
            rs = kb.score_kb(entry, soil_type, season, rainfall_mm, water_availability, regional_tuning)
            if regional_tuning:
                # Regional tuning works in both directions: it lifts the district's real crops
                # and demotes crops that the cited sources describe as not viable here (apple
                # needs winter chilling; cotton/grapes/pomegranate/mothbean are Deccan/arid-zone
                # crops). Both directions are documented on the About page.
                prior = REGIONAL_PRIOR if entry.get("dk_local") else REGIONAL_DEMOTION
            else:
                prior = 1.0
            blended = (max(prob, 1e-6) ** MODEL_EXPONENT) * (max(rs["score"], 1e-6) ** RULE_EXPONENT)
            scored.append({
                "crop": crop,
                "name": entry.get("en_name", crop),
                "name_kn": entry.get("kn", ""),
                "confidence": round(min(1.0, blended * prior), 4),
                "model_probability": round(prob, 4),
                "rule_fit": rs["score"],
                "rule_components": rs["components"],
                "waterlogging_penalised": rs.get("waterlogging_penalised", False),
                "in_model_label_space": True,
                "reasons": kb.build_reasons(crop, soil_type, season, rainfall_mm,
                                            water_availability, rs["components"],
                                            regional_tuning, kb_entry=entry),
                "advisories": kb.advisories(crop, rainfall_mm, water_availability,
                                            rs["components"], kb_entry=entry)
                + (["Waterlogging risk: reported rainfall is above this crop's band and it is "
                    "drainage-sensitive (rule-fit penalty applied)."] if rs.get("waterlogging_penalised")
                   else []),
                "kb_only": False,
                "_kb": entry,   # used only to derive metadata below, not serialised
            })

        for item in scored:
            e = item.pop("_kb", {})
            item["category"] = e.get("category")
            item["dk_local"] = bool(e.get("dk_local"))
            item["duration_days"] = e.get("duration_days")
            item["source"] = e.get("source")

        scored.sort(key=lambda d: (-d["confidence"], -d["model_probability"]))
        top = scored[:top_k]
        for rank, item in enumerate(top, start=1):
            item["rank"] = rank
            item["status"] = ("strong match" if item["confidence"] >= STRONG_THRESHOLD else
                              "reasonable match" if item["confidence"] >= REASONABLE_THRESHOLD else
                              "weak match - verify locally")

        # ---- regional advisory: crops that matter in DK but are NOT in the model's label space
        advisory = []
        if regional_tuning:
            for crop, entry in kb_map.items():
                if crop in model_prob or not entry.get("dk_local"):
                    continue
                rs = kb.score_kb(entry, soil_type, season, rainfall_mm, water_availability, True)
                if rs["score"] >= 0.6:
                    advisory.append({
                        "crop": crop,
                        "name": entry.get("en_name", crop),
                        "name_kn": entry.get("kn", ""),
                        "rule_fit": rs["score"],
                        "rule_components": rs["components"],
                "waterlogging_penalised": rs.get("waterlogging_penalised", False),
                "in_model_label_space": True,
                        "reasons": kb.build_reasons(crop, soil_type, season, rainfall_mm,
                                                    water_availability, rs["components"], True,
                                                    kb_entry=entry),
                        "disclaimer": ("Regional advisory from the cited agronomic knowledge base. "
                                       "This crop is NOT in the secondary dataset's 22 classes, so no "
                                       "machine-learning probability can be quoted for it."),
                    })
            advisory.sort(key=lambda d: -d["rule_fit"])
            advisory = advisory[:3]

        top_conf = top[0]["confidence"] if top else 0.0
        return {
            "input": {
                "soil_type": soil_type, "season": season, "rainfall_mm": rainfall_mm,
                "water_availability": water_availability, "regional_tuning": regional_tuning,
            },
            "expanded_parameters": agro,
            "expansion_audit": expansion_explanation(soil_type, season, water_availability),
            "recommendations": top,
            "regional_advisory": advisory,
            "confidence_note": (f"Suitability score = model probability^{MODEL_EXPONENT} x "
                                f"agronomic rule fit^{RULE_EXPONENT}"
                                + (f", then regional tuning applies x{REGIONAL_PRIOR} for crops grown in "
                                   f"Dakshina Kannada and x{REGIONAL_DEMOTION} for crops documented as "
                                   f"not viable here" if regional_tuning else "")),
            "low_confidence": bool(top and top_conf < LOW_CONFIDENCE_THRESHOLD),
            "disclaimer": ("Indicative decision support, not a guarantee. This advice cannot price "
                           "your crop, does not know your labour or market access, and is trained on "
                           "a secondary dataset whose rainfall range is much lower than coastal "
                           "Karnataka's. Confirm with your local KVK / Raitha Samparka Kendra before "
                           "sowing."),
            "blend": {"model_exponent": MODEL_EXPONENT, "rule_exponent": RULE_EXPONENT,
                      "regional_prior": ({"local_crops": REGIONAL_PRIOR, "non_local_crops": REGIONAL_DEMOTION}
                                         if regional_tuning else {"applied": False}),
                      "bands": {"strong_match": STRONG_THRESHOLD, "reasonable_match": REASONABLE_THRESHOLD},
                      "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
                      "score_label": "blended suitability score (NOT a calibrated probability of "
                                     "success; model_probability is reported separately)"},
            "model": {
                "key": art.get("model_key"),
                "label": art.get("model_label"),
                "version": art.get("model_version"),
                "trained_at": art.get("trained_at"),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


registry = ModelRegistry()


def warm_up_async() -> None:
    """Optional background warm-up so the first user does not pay the load cost."""
    def _warm():
        try:
            registry.load()
        except Exception as exc:  # pragma: no cover
            log.warning("Warm-up failed: %s", exc)
    threading.Thread(target=_warm, daemon=True).start()
