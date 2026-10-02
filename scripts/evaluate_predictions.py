#!/usr/bin/env python3
"""
Offline evaluation harness for the report.

It replays a grid of realistic Dakshina Kannada field profiles through the FULL serving
path (4 inputs -> expansion -> model -> rule fit -> blend) and reports:

  * top-1 / top-3 agreement between the served recommendation and an agronomic
    "reference crop" derived from the district's documented cropping pattern
  * confidence distribution and how often the app itself flags low confidence
  * the mean model probability vs mean rule fit per profile (is the blend doing work?)
  * the effect of turning regional tuning off

Reference crops (NOT model ground truth) come from the DK cropping pattern documented by
KVK Dakshina Kannada (paddy 48,689 ha; arecanut 35,409 ha; coconut 18,467 ha; plus the
seasonal paddy-fallow pulses and Zaid melons) and from the crop climate/water requirement
tables of the TNAU Crop Production Guide. They are used as a sanity benchmark for a
human-readable report — they are NOT an independent test set, and the script says so in
its own output.

Usage:
    python scripts/evaluate_predictions.py            # needs the backend importable
    python scripts/evaluate_predictions.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ml.registry import registry  # noqa: E402

# (soil, season, rainfall mm, water availability, reference crops that DK agronomy expects)
PROFILES = [
    ("laterite", "Kharif", 260, "high", ["rice", "coconut", "banana", "arecanut"]),
    ("laterite", "Kharif", 240, "medium", ["rice", "coconut", "banana"]),
    ("laterite", "Kharif", 220, "low", ["rice", "coconut", "groundnut"]),
    ("laterite", "Rabi", 70, "medium", ["blackgram", "cowpea", "horsegram", "maize"]),
    ("laterite", "Rabi", 60, "high", ["blackgram", "cowpea", "horsegram"]),
    ("laterite", "Zaid", 40, "low", ["watermelon", "muskmelon", "groundnut", "mango"]),
    ("laterite", "Zaid", 30, "medium", ["watermelon", "muskmelon", "cowpea"]),
    ("red_loam", "Kharif", 200, "medium", ["rice", "maize", "groundnut"]),
    ("red_loam", "Rabi", 85, "medium", ["maize", "blackgram", "horsegram"]),
    ("red_loam", "Zaid", 45, "high", ["watermelon", "muskmelon", "maize"]),
    ("alluvial", "Kharif", 250, "high", ["rice", "banana", "jute"]),
    ("alluvial", "Kharif", 230, "medium", ["rice", "banana"]),
    ("alluvial", "Rabi", 90, "high", ["rice", "blackgram", "banana"]),
    ("alluvial", "Zaid", 35, "high", ["watermelon", "muskmelon", "rice"]),
    ("coastal_sandy", "Kharif", 250, "medium", ["coconut", "cashew", "watermelon"]),
    ("coastal_sandy", "Kharif", 240, "low", ["coconut", "cashew"]),
    ("coastal_sandy", "Zaid", 35, "medium", ["watermelon", "muskmelon", "coconut"]),
    ("coastal_saline", "Kharif", 240, "medium", ["coconut"]),
    ("black", "Kharif", 120, "medium", ["maize", "cotton", "pigeonpeas"]),
    ("laterite", "Kharif", 300, "high", ["rice", "coconut", "arecanut"]),
]


def run(regional_tuning: bool = True) -> dict:
    hits1 = hits3 = reference_absent = 0
    confidences, model_probs, rule_fits, low_conf = [], [], [], 0
    rows = []
    for soil, season, rain, water, ref in PROFILES:
        result = registry.predict(soil_type=soil, season=season, rainfall_mm=rain,
                                  water_availability=water, regional_tuning=regional_tuning, top_k=3)
        recs = result["recommendations"]
        names = [r["crop"] for r in recs]
        top1 = names[0]
        in3 = any(n in ref for n in names)
        # a reference crop that the secondary dataset simply does not contain can never be
        # predicted; mark those rows so the report does not read as a model failure
        ref_in_label_space = [c for c in ref if c in registry.load()["classes"]]
        absent = not ref_in_label_space
        reference_absent += int(absent)
        hits1 += int(top1 in ref)
        hits3 += int(in3)
        confidences.append(recs[0]["confidence"])
        model_probs.append(recs[0]["model_probability"])
        rule_fits.append(recs[0]["rule_fit"])
        low_conf += int(result["low_confidence"])
        rows.append({
            "soil_type": soil, "season": season, "rainfall_mm": rain,
            "water_availability": water, "reference_crops": ref,
            "reference_crop_in_model_classes": ref_in_label_space,
            "top1": top1, "top1_hit": top1 in ref, "top3": names, "top3_hit": in3,
            "top1_confidence": recs[0]["confidence"],
            "top1_model_probability": recs[0]["model_probability"],
            "top1_rule_fit": recs[0]["rule_fit"],
            "advisory": [a["crop"] for a in result["regional_advisory"]],
            "flagged_low_confidence": result["low_confidence"],
        })
    n = len(PROFILES)
    return {
        "profiles": n,
        "reference_crop_absent_from_model_classes": reference_absent,
        "top1_agreement": round(hits1 / n, 4),
        "top3_agreement": round(hits3 / n, 4),
        "mean_top1_confidence": round(statistics.mean(confidences), 4),
        "mean_top1_model_probability": round(statistics.mean(model_probs), 4),
        "mean_top1_rule_fit": round(statistics.mean(rule_fits), 4),
        "low_confidence_flags": low_conf,
        "regional_tuning": regional_tuning,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay DK field profiles through the serving path")
    ap.add_argument("--json", help="write the full result to this JSON file")
    args = ap.parse_args()

    on = run(True)
    off = run(False)

    print("=" * 86)
    print("REGIONAL TUNING ON")
    print(f"top-1 agreement with the DK agronomic reference : {on['top1_agreement']:.1%}")
    print(f"top-3 agreement                                 : {on['top3_agreement']:.1%}")
    print(f"mean top-1 blended score / model prob / rule fit : "
          f"{on['mean_top1_confidence']:.3f} / {on['mean_top1_model_probability']:.3f} / {on['mean_top1_rule_fit']:.3f}")
    print(f"rows where the app flagged low confidence        : {on['low_confidence_flags']}/{on['profiles']}")
    print(f"reference crops absent from the model's classes  : "
          f"{on['reference_crop_absent_from_model_classes']} profile(s) — those can never be predicted "
          f"and are surfaced as knowledge-base advisories instead")
    print("-" * 86)
    print(f"{'profile':<44}{'top-1':<16}{'hit':<5}{'conf':<7}advisory")
    for r in on["rows"]:
        prof = f"{r['soil_type']}/{r['season']}/{r['rainfall_mm']}mm/{r['water_availability']}"
        print(f"{prof:<44}{r['top1']:<16}{'yes' if r['top1_hit'] else 'no':<5}"
              f"{r['top1_confidence']:.2f}   {', '.join(r['advisory'])}")
    print("=" * 86)
    print("REGIONAL TUNING OFF")
    print(f"top-1 agreement {off['top1_agreement']:.1%} | top-3 {off['top3_agreement']:.1%} | "
          f"mean score {off['mean_top1_confidence']:.3f}")
    print("\nHONESTY NOTE: the 'reference crops' above are an agronomic expectation compiled from the "
          "cited\nKVK DK cropping pattern and TNAU crop requirements — they are NOT an independent "
          "labelled test set.\nThis harness is a sanity benchmark for the report, not a field "
          "validation.")

    if args.json:
        Path(args.json).write_text(json.dumps({"regional_on": on, "regional_off": off}, indent=2))
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
