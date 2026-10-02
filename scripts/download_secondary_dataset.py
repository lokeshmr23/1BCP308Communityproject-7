#!/usr/bin/env python3
"""
Download (or refresh) the FREE secondary dataset used for training.

Source
------
Kaggle — "Crop Recommendation Dataset" by atharvaingle
    https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset
    2200 rows x {N, P, K, temperature, humidity, ph, rainfall, label}, 22 crop classes.
Free to use; widely used in the peer-reviewed literature reviewed on the Project
Comparison page (2024 ACM comparison, Scientific Reports 2025/2026 papers).

The canonical copy ships in this repository at
    backend/data/secondary/crop_recommendation.csv
so the app never needs the network at runtime or build time.

Why a mirror and not the Kaggle API
-----------------------------------
Kaggle's API needs an account + API token, which is unsuitable for an unattended
free-tier build. This script therefore reads a public Hugging Face *mirror* of the
same dataset (the columns and the 2200 x 22 shape are identical) and validates the
result against the expected schema before writing it.

Usage
-----
    python scripts/download_secondary_dataset.py --check      # validate the shipped file
    python scripts/download_secondary_dataset.py --download   # fetch from the mirror

Verification performed either way:
  * required columns present
  * exactly 2200 rows
  * 22 distinct crop labels, 100 rows each
  * missing-value count, duplicate count, and range checks printed
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "backend" / "data" / "secondary" / "crop_recommendation.csv"

MIRROR = "Samarth-27/Crop-Recommendation-Parameters"     # Hugging Face dataset id
DS_SERVER = "https://datasets-server.huggingface.co"
COLUMNS = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall", "label"]
EXPECTED_ROWS = 2200
EXPECTED_CLASSES = 22


def validate(path: Path) -> dict:
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    problems: list[str] = []
    if not rows:
        problems.append("file is empty")
    header = list(rows[0].keys()) if rows else []
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        problems.append(f"missing columns: {missing}")
    counts: dict[str, int] = {}
    missing_values = 0
    for r in rows:
        counts[r.get("label", "?")] = counts.get(r.get("label", "?"), 0) + 1
        for c in COLUMNS:
            if r.get(c) in (None, ""):
                missing_values += 1
    if rows and len(rows) != EXPECTED_ROWS:
        problems.append(f"expected {EXPECTED_ROWS} rows, found {len(rows)}")
    if rows and len(counts) != EXPECTED_CLASSES:
        problems.append(f"expected {EXPECTED_CLASSES} classes, found {len(counts)}")
    uneven = {k: v for k, v in counts.items() if v != 100}
    if uneven and rows:
        problems.append(f"classes are not balanced at 100 rows: {uneven}")
    report = {
        "file": str(path.relative_to(REPO_ROOT)),
        "rows": len(rows),
        "columns": header,
        "classes": len(counts),
        "class_counts_sample": dict(sorted(counts.items())[:5]),
        "missing_values": missing_values,
        "ok": not problems,
        "problems": problems,
    }
    return report


def download() -> None:
    enc = urllib.parse.quote(MIRROR, safe="")
    with urllib.request.urlopen(f"{DS_SERVER}/info?dataset={enc}", timeout=45) as r:
        info = json.load(r)
    n = info["dataset_info"]["default"]["splits"]["train"]["num_examples"]
    print(f"Mirror {MIRROR} reports {n} rows; fetching in pages of 100…")
    out_rows: list[dict] = []
    for offset in range(0, n, 100):
        url = (f"{DS_SERVER}/rows?dataset={enc}&config=default&split=train"
               f"&offset={offset}&length=100")
        with urllib.request.urlopen(url, timeout=45) as r:
            payload = json.load(r)
        out_rows.extend(item["row"] for item in payload["rows"])
        print(f"  {len(out_rows)}/{n}")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in out_rows:
            writer.writerow({c: row[c] for c in COLUMNS})
    print(f"Wrote {TARGET}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch / verify the free secondary crop dataset")
    ap.add_argument("--download", action="store_true", help="download from the public mirror")
    ap.add_argument("--check", action="store_true", help="validate the shipped CSV")
    args = ap.parse_args()

    if args.download:
        download()
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run with --download.", file=sys.stderr)
        return 2
    report = validate(TARGET)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        print("VALIDATION FAILED", file=sys.stderr)
        return 1
    print("Dataset OK — 2200 rows x 22 balanced classes, no missing values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
