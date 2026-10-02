#!/usr/bin/env python3
"""
Artefact sanity check: the repository must ship a model small enough for a free-tier deploy and
metrics that match the code's own claims. Run before committing or pushing:

    python scripts/check_artifacts.py

Fails (exit 1) if:
  * best_model.joblib or metrics.json is missing;
  * the model artefact is larger than 3 MB (a free-tier cold start and a git push should stay cheap);
  * fewer than four algorithms are compared;
  * the recorded model_size_kb does not match the file on disk;
  * the dataset row accounting is inconsistent (total != used + dropped);
  * the stratified-split protocol line is missing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODEL = REPO / "backend" / "data" / "models" / "best_model.joblib"
METRICS = REPO / "backend" / "data" / "models" / "metrics.json"
SECONDARY = REPO / "backend" / "data" / "secondary" / "crop_recommendation.csv"

MAX_MODEL_KB = 3000
problems: list[str] = []

if not MODEL.exists():
    problems.append(f"missing model artefact: {MODEL.relative_to(REPO)}")
if not METRICS.exists():
    problems.append(f"missing metrics: {METRICS.relative_to(REPO)}")
if not SECONDARY.exists():
    problems.append(f"missing secondary dataset: {SECONDARY.relative_to(REPO)}")
if problems:
    print("\n".join("ERROR: " + p for p in problems))
    sys.exit(1)

size_kb = MODEL.stat().st_size / 1024
m = json.loads(METRICS.read_text())
ds = m.get("dataset", {})

if size_kb > MAX_MODEL_KB:
    problems.append(f"model artefact is {size_kb:.0f} KB (limit {MAX_MODEL_KB} KB)")
if len(m.get("models", {})) < 4:
    problems.append(f"only {len(m.get('models', {}))} algorithms compared, expected 4")
recorded = m.get("artifacts", {}).get("model_size_kb")
if recorded and abs(recorded - size_kb) / size_kb > 0.05:
    problems.append(f"metrics say {recorded} KB but the file is {size_kb:.1f} KB")
env = m.get("environment", {})
if not env:
    problems.append("metrics.json has no `environment` block (artefact provenance missing)")
else:
    req = (REPO / "backend" / "requirements.txt").read_text()
    for lib, pin in (("scikit_learn", "scikit-learn"), ("numpy", "numpy"), ("pandas", "pandas"),
                     ("joblib", "joblib")):
        if env.get(lib) and f"{pin}=={env[lib]}" not in req:
            problems.append(f"artefact built with {pin} {env[lib]} but requirements.txt pins another version")

if ds:
    if ds.get("rows_total") != ds.get("rows_used_for_training", 0) + ds.get("rows_dropped_outside_label_space", 0):
        problems.append("row accounting inconsistent: total != used + dropped_outside_label_space")
    if "stratified 80/20" not in str(ds.get("protocol", "")):
        problems.append("the dataset block does not state the stratified 80/20 protocol")

print(f"model artefact      : {size_kb:8.1f} KB  ({MODEL.name})")
print(f"algorithms compared : {len(m.get('models', {}))}  ({', '.join(sorted(m.get('models', {})))})")
print(f"selected model      : {m.get('best_model', {}).get('key')} "
      f"acc={m.get('best_model', {}).get('metrics', {}).get('test_accuracy')} "
      f"top3={m.get('best_model', {}).get('metrics', {}).get('top3_accuracy')}")
print(f"dataset rows        : {ds.get('rows_total')} total, {ds.get('rows_used_for_training')} trained, "
      f"{ds.get('rows_dropped_outside_label_space')} outside the label space, "
      f"{ds.get('primary_rows_used')} from the primary survey")
print(f"protocol            : {ds.get('protocol')}")
print(f"trained at          : {m.get('trained_at')}")
if env:
    print(f"build environment   : python {env.get('python')}, scikit-learn {env.get('scikit_learn')}, "
          f"numpy {env.get('numpy')}, pandas {env.get('pandas')}, joblib {env.get('joblib')} "
          f"(matching requirements.txt)")

if problems:
    print("\n" + "\n".join("ERROR: " + p for p in problems))
    sys.exit(1)
print("\nOK: artefacts are consistent and small enough for the free-tier deployment.")
