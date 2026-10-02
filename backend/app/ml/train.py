"""
Training / evaluation pipeline with an honest two-track design.

TRACK A — main model ("agronomic core"), 7 real parameters
    Trained on the seven parameters the secondary dataset actually measures
    (N, P, K, temperature, humidity, pH, rainfall). This is directly comparable with the
    published work reviewed on the Project Comparison page. At serving time the app asks
    only four farmer-answerable questions and EXPANDS them into these seven parameters
    with documented typical soil/season profiles (features.expand_to_agronomic) — the
    assumption is displayed in the UI, never hidden.

TRACK B — ablation, 4 collected inputs only
    Same four algorithms trained only on (soil_type, season, rainfall_mm,
    water_availability), where soil_type/season/water_availability are DERIVED from the
    secondary data. This quantifies, instead of hiding, how much accuracy is given up by
    collecting only farmer-answerable inputs. Reported on the Model Performance page.

Protocol for both tracks
------------------------
* stratified 80/20 train-test split (random_state = 42)
* 5-fold StratifiedKFold cross-validation on the TRAIN split only (no leakage)
* accuracy, macro precision/recall/F1, weighted F1, top-3 accuracy, confusion matrix
* best model = highest mean CV macro-F1 (tie-break: test macro-F1), saved with joblib
  (compress=3) so the artefact stays small enough to keep in the Git repo — Render's
  free disk is ephemeral, so the model ships with the code, not on disk.

Run:  python -m app.ml.train     (from backend/)
"""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score, precision_score, recall_score, top_k_accuracy_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .features import (AGRO_FEATURES, CATEGORICAL_FEATURES, FEATURE_COLUMNS,
                       NUMERIC_FEATURES, TARGET_COLUMN, expand_to_agronomic,
                       load_secondary, merge_sources)
from .knowledge import MODEL_CROP_LABELS

RANDOM_STATE = 42
TEST_SIZE = 0.20
CV_FOLDS = 5
MODEL_VERSION = "1.0.0"

MODEL_SPECS = {
    "decision_tree": lambda: DecisionTreeClassifier(max_depth=14, min_samples_leaf=2,
                                                    random_state=RANDOM_STATE),
    "random_forest": lambda: RandomForestClassifier(n_estimators=150, min_samples_leaf=1,
                                                    n_jobs=-1, random_state=RANDOM_STATE),
    "knn": lambda: KNeighborsClassifier(n_neighbors=7, weights="distance"),
    "naive_bayes": lambda: GaussianNB(),
}

MODEL_LABELS = {
    "decision_tree": "Decision Tree",
    "random_forest": "Random Forest",
    "knn": "K-Nearest Neighbours (k=7, distance-weighted)",
    "naive_bayes": "Gaussian Naive Bayes",
}

# Sample weights (primary-survey confidence, see cleaning rules) are only accepted by the
# tree estimators; KNN / GaussianNB have no sample_weight argument, which is stated in the
# metrics rather than silently ignored.
SAMPLE_WEIGHT_MODELS = {"decision_tree": True, "random_forest": True, "knn": False, "naive_bayes": False}


def build_preprocessor(track: str) -> ColumnTransformer:
    if track == "agro":
        return ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), AGRO_FEATURES),
            ],
            remainder="drop",
        )
    return ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
            ("num", StandardScaler(), NUMERIC_FEATURES),
        ],
        remainder="drop",
    )


def build_pipeline(model_key: str, track: str = "agro") -> Pipeline:
    return Pipeline([("prep", build_preprocessor(track)), ("clf", MODEL_SPECS[model_key]())])


def _feature_names(prep: ColumnTransformer) -> list[str]:
    return [n.split("__", 1)[1] if "__" in n else n for n in prep.get_feature_names_out()]


def _group_importance(names: list[str], values: list[float], candidates: list[str] | None = None) -> dict[str, float]:
    """Aggregate one-hot / scaled columns back to the user-facing inputs."""
    candidates = candidates or (AGRO_FEATURES if all("_" not in n for n in names) else FEATURE_COLUMNS)
    groups: dict[str, float] = {f: 0.0 for f in candidates}
    for n, v in zip(names, values):
        for f in groups:
            if n == f or n.startswith(f + "_"):
                groups[f] += float(v)
                break
    total = sum(groups.values()) or 1.0
    return {k: round(v / total, 4) for k, v in sorted(groups.items(), key=lambda kv: -kv[1])}


def evaluate_model(pipeline: Pipeline, X_tr, X_te, y_tr, y_te, classes: list[str],
                   cv: StratifiedKFold, sample_weight=None) -> dict:
    # CV folds are scored without sample weights so all four algorithms are compared on
    # exactly the same footing.
    cv_acc = cross_val_score(pipeline, X_tr, y_tr, cv=cv, scoring="accuracy", n_jobs=1)
    cv_f1 = cross_val_score(pipeline, X_tr, y_tr, cv=cv, scoring="f1_macro", n_jobs=1)

    t0 = time.perf_counter()
    if sample_weight is not None:
        pipeline.fit(X_tr, y_tr, clf__sample_weight=sample_weight)
    else:
        pipeline.fit(X_tr, y_tr)
    fit_seconds = round(time.perf_counter() - t0, 2)

    t0 = time.perf_counter()
    y_pred = pipeline.predict(X_te)
    predict_ms = round((time.perf_counter() - t0) * 1000, 2)
    proba = pipeline.predict_proba(X_te)

    try:
        top3 = float(top_k_accuracy_score(y_te, proba, k=3, labels=list(pipeline.classes_)))
    except ValueError:
        top3 = float("nan")

    report = classification_report(y_te, y_pred, output_dict=True, zero_division=0)
    per_class = {
        c: {
            "precision": round(report[c]["precision"], 4),
            "recall": round(report[c]["recall"], 4),
            "f1": round(report[c]["f1-score"], 4),
            "support": int(report[c]["support"]),
        }
        for c in classes if c in report and isinstance(report[c], dict)
    }

    return {
        "cv_accuracy_mean": round(float(cv_acc.mean()), 4),
        "cv_accuracy_std": round(float(cv_acc.std()), 4),
        "cv_macro_f1_mean": round(float(cv_f1.mean()), 4),
        "cv_macro_f1_std": round(float(cv_f1.std()), 4),
        "test_accuracy": round(float(accuracy_score(y_te, y_pred)), 4),
        "test_precision_macro": round(float(precision_score(y_te, y_pred, average="macro", zero_division=0)), 4),
        "test_recall_macro": round(float(recall_score(y_te, y_pred, average="macro", zero_division=0)), 4),
        "test_f1_macro": round(float(f1_score(y_te, y_pred, average="macro", zero_division=0)), 4),
        "test_f1_weighted": round(float(f1_score(y_te, y_pred, average="weighted", zero_division=0)), 4),
        "top3_accuracy": round(top3, 4),
        "mean_max_confidence": round(float(np.mean(proba.max(axis=1))), 4),
        "fit_seconds": fit_seconds,
        "predict_ms_for_test_split": predict_ms,
        "per_class": per_class,
    }


def _primary_frame(primary_rows: list[dict]) -> pd.DataFrame:
    """Primary survey rows -> the seven agronomic parameters through the expansion layer."""
    rows = []
    for r in primary_rows:
        try:
            agro = expand_to_agronomic(r["soil_type"], r["season"], float(r["rainfall_mm"]),
                                      r["water_availability"])
        except Exception:
            continue
        agro[TARGET_COLUMN] = r[TARGET_COLUMN]
        rows.append(agro)
    return pd.DataFrame(rows)


def train_and_save(secondary_path: str, out_dir: str, primary_rows: list[dict] | None = None,
                   derived_out: str | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    started = time.time()

    secondary = load_secondary(secondary_path)
    n_secondary = len(secondary)
    data = merge_sources(secondary, primary_rows or [])
    n_primary = int((data["source"] == "primary_survey").sum())
    outside_label_space = sorted(set(data.loc[data["source"] == "primary_survey", TARGET_COLUMN])
                                 - set(MODEL_CROP_LABELS))
    n_primary_outside = int(((data["source"] == "primary_survey")
                            & (~data[TARGET_COLUMN].isin(MODEL_CROP_LABELS))).sum())
    rows_merged = int(len(data))
    data = data[data[TARGET_COLUMN].isin(MODEL_CROP_LABELS)].reset_index(drop=True)
    classes = sorted(data[TARGET_COLUMN].unique())

    # ---------------------------------------------------------------- TRACK A (main)
    Xa = data[AGRO_FEATURES]
    ya = data[TARGET_COLUMN]
    Xa_tr, Xa_te, ya_tr, ya_te = train_test_split(
        Xa, ya, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=ya)
    wa = data.loc[Xa_tr.index, "sample_weight"].to_numpy()

    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    results, fitted = {}, {}
    for key in MODEL_SPECS:
        pipe = build_pipeline(key, "agro")
        metrics = evaluate_model(pipe, Xa_tr, Xa_te, ya_tr, ya_te, classes, cv,
                                 sample_weight=wa if SAMPLE_WEIGHT_MODELS[key] else None)
        metrics["sample_weights_used"] = bool(SAMPLE_WEIGHT_MODELS[key] and n_primary > 0)
        metrics["label"] = MODEL_LABELS[key]
        results[key] = metrics
        fitted[key] = pipe

    best_key = max(results, key=lambda k: (results[k]["cv_macro_f1_mean"], results[k]["test_f1_macro"]))
    best_pipe = fitted[best_key]
    best = results[best_key]

    y_pred = best_pipe.predict(Xa_te)
    cm = confusion_matrix(ya_te, y_pred, labels=classes).tolist()
    report = classification_report(ya_te, y_pred, output_dict=True, zero_division=0)

    # ---------------------------------------------------------------- explainability
    names = _feature_names(best_pipe.named_steps["prep"])
    clf = best_pipe.named_steps["clf"]
    fi: dict = {"method": None, "raw": None, "grouped": None, "permutation_grouped": None}
    if hasattr(clf, "feature_importances_"):
        raw = clf.feature_importances_.tolist()
        fi["method"] = "impurity-based (mean decrease in Gini) on the fitted best model"
        fi["raw"] = sorted([{"feature": n, "importance": round(float(v), 5)} for n, v in zip(names, raw)],
                           key=lambda d: -d["importance"])
        fi["grouped"] = _group_importance(names, raw, AGRO_FEATURES)
    try:
        perm = permutation_importance(best_pipe, Xa_te, ya_te, n_repeats=10,
                                      random_state=RANDOM_STATE, scoring="accuracy", n_jobs=1)
        fi["permutation_grouped"] = _group_importance(list(Xa_te.columns), perm.importances_mean.tolist(), AGRO_FEATURES)
        fi["permutation_note"] = ("permutation importance on the untouched 20% test split "
                                  f"(n_repeats=10, n_test={len(Xa_te)})")
    except Exception as exc:  # pragma: no cover
        fi["permutation_note"] = f"permutation importance unavailable: {exc}"

    # ---------------------------------------------------------------- TRACK B (ablation)
    ablation = {"track": "4 collected inputs only (soil_type, season, rainfall_mm, water_availability)",
                "note": ("Same algorithms and protocol, but trained only on the four inputs the app "
                         "collects — soil_type/season/water_availability being DERIVED from the "
                         "secondary data. This is the honest cost of collecting only "
                         "farmer-answerable inputs."),
                "models": {}}
    Xb = data[FEATURE_COLUMNS]
    Xb_tr, Xb_te, yb_tr, yb_te = train_test_split(
        Xb, ya, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=ya)
    for key in MODEL_SPECS:
        pipe = build_pipeline(key, "four")
        m = evaluate_model(pipe, Xb_tr, Xb_te, yb_tr, yb_te, classes, cv)
        m["label"] = MODEL_LABELS[key]
        ablation["models"][key] = m
    best_ablation_key = max(ablation["models"],
                            key=lambda k: ablation["models"][k]["cv_macro_f1_mean"])
    ablation["best_key"] = best_ablation_key
    ablation["best"] = ablation["models"][best_ablation_key]

    # ---------------------------------------------------------------- external check
    external = {"n_rows": 0, "n_rows_available": 0,
                "note": "No cleaned primary survey rows were supplied to this training run."}
    if primary_rows:
        try:
            prim_all = _primary_frame(primary_rows)
            prim = prim_all[prim_all[TARGET_COLUMN].isin(classes)]
            if len(prim) < 10:
                external = {
                    "n_rows": 0,
                    "n_rows_available": int(len(prim)),
                    "note": (f"{len(prim)} of {len(prim_all)} cleaned primary survey rows use a crop that "
                             "is inside the model's 22 classes (at least 10 are needed for a sanity "
                             "check). The remaining rows describe local crops such as arecanut, cashew "
                             "and black pepper that the secondary dataset does not contain."),
                }
            if len(prim) >= 10:
                yp = best_pipe.predict(prim[AGRO_FEATURES])
                pp = best_pipe.predict_proba(prim[AGRO_FEATURES])
                try:
                    t3 = float(top_k_accuracy_score(prim[TARGET_COLUMN], pp, k=3,
                                                    labels=list(best_pipe.classes_)))
                except ValueError:
                    t3 = float("nan")
                external = {
                    "n_rows": int(len(prim)),
                    "accuracy": round(float(accuracy_score(prim[TARGET_COLUMN], yp)), 4),
                    "top3_accuracy": round(t3, 4) if t3 == t3 else None,
                    "note": ("Agreement between the served recommendation and the crop actually reported "
                             "in the primary survey rows (through the full expansion + model path). "
                             "Treat as a sanity check only: few rows, self-reported outcomes, and in "
                             "the demo seed they are synthetic — NOT independent field validation."),
                }
        except Exception as exc:  # pragma: no cover
            external = {"n_rows": 0, "note": f"external check skipped: {exc}"}

    metrics = {
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_seconds": round(time.time() - started, 2),
        # Provenance: which interpreter and which library versions produced this artefact.
        # A joblib file must be unpickled with a compatible scikit-learn (a patch mismatch only
        # warns, a minor mismatch can break), so the versions are recorded here and asserted by
        # tests/test_ml_pipeline.py against the pins in requirements.txt.
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "joblib": joblib.__version__,
        },
        "dataset": {
            "secondary_source": ("Kaggle Crop Recommendation Dataset "
                                 "(kaggle.com/datasets/atharvaingle/crop-recommendation-dataset), "
                                 "2200 rows x 22 crops x 7 parameters"),
            "secondary_rows_used": n_secondary,
            "primary_rows_used": n_primary,
            "primary_rows_in_label_space": n_primary - n_primary_outside,
            "primary_rows_outside_label_space": n_primary_outside,
            "primary_crops_outside_label_space": outside_label_space,
            "primary_label_space_note": ("Primary survey rows whose crop is outside the model's 22 "
                                         "classes (e.g. arecanut, cashew, black pepper) cannot train "
                                         "the classifier - there is no such class - but they still "
                                         "document the district's real cropping pattern and feed the "
                                         "knowledge base."),
            "rows_total": rows_merged,
            "rows_used_for_training": int(len(data)),
            "rows_dropped_outside_label_space": rows_merged - int(len(data)),
            "feature_space": AGRO_FEATURES,
            "collected_inputs": FEATURE_COLUMNS,
            "n_classes": len(classes),
            "classes": classes,
            "train_rows": int(len(Xa_tr)),
            "test_rows": int(len(Xa_te)),
            "protocol": (f"stratified {int((1 - TEST_SIZE) * 100)}/{int(TEST_SIZE * 100)} split "
                         f"(random_state={RANDOM_STATE}) + {CV_FOLDS}-fold StratifiedKFold CV on the train split"),
        },
        "models": results,
        "best_model": {
            "key": best_key,
            "label": MODEL_LABELS[best_key],
            "selection_rule": "highest mean CV macro-F1 (tie-break: test macro-F1)",
            "metrics": best,
        },
        "ablation_four_inputs": ablation,
        "confusion_matrix": {"labels": classes, "matrix": cm},
        "classification_report": {
            k: (v if isinstance(v, dict) else round(float(v), 4)) for k, v in report.items()
        },
        "feature_importance": fi,
        "external_check": external,
        "honest_limitations": [
            "The model is trained on the SEVEN measured parameters of the secondary dataset. The app "
            "collects only four farmer-answerable inputs and expands them into seven using documented "
            "TYPICAL soil/season profiles (backend/app/ml/features.py: SOIL_PROFILES, SEASON_PROFILES). "
            "Those profiles are stated assumptions, not measurements — field accuracy will be lower "
            "than the holdout accuracy reported here.",
            "soil_type, season and water_availability have no ground-truth column in the secondary "
            "dataset; in the ablation track they are DERIVED (see docs/dataset_schema.md). Primary "
            "survey rows are the only place where real soil type / season / water source exist.",
            "The secondary dataset caps rainfall at ~299 mm per period, whereas Dakshina Kannada "
            "receives ~3,900 mm per year (KVK DK normal ~4,000 mm). The model's behaviour above that "
            "range is extrapolation — which is why water availability, regional tuning and the rule-fit "
            "score exist as separate, visible safeguards.",
            "22 classes with exactly 100 rows each make the classification task unusually clean; the "
            "headline accuracy is a dataset property first and a field-reliability claim second.",
            "Locally important crops absent from the secondary dataset (arecanut, cashew, black pepper, "
            "cocoa, rubber) are surfaced by the cited knowledge base and are always labelled "
            "'regional advisory (knowledge base) — not model-predicted'.",
            "Crop suitability is not the same as profitability, market access or labour availability; "
            "the app states this on every recommendation card.",
        ],
        "artifacts": {
            "model_file": "best_model.joblib",
            "model_size_kb": None,
            "serialisation": "joblib.dump(..., compress=3) — must be loaded with the "
                             "scikit-learn version recorded in `environment`",
            "serving_path": ("4 inputs -> expand_to_agronomic() -> 7 params -> pipeline -> "
                             "geometric blend (prob^0.55 x rule_fit^0.45) -> top-3 with reasons"),
        },
    }

    model_path = os.path.join(out_dir, "best_model.joblib")
    joblib.dump(
        {
            "pipeline": best_pipe,
            "model_key": best_key,
            "model_label": MODEL_LABELS[best_key],
            "classes": list(best_pipe.classes_),
            "track": "agro",
            "features": AGRO_FEATURES,
            "collected_inputs": FEATURE_COLUMNS,
            "model_version": MODEL_VERSION,
            "trained_at": metrics["trained_at"],
            "n_training_rows": int(len(Xa_tr)),
        },
        model_path, compress=3,
    )
    metrics["artifacts"]["model_size_kb"] = round(os.path.getsize(model_path) / 1024, 1)

    with open(os.path.join(out_dir, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    if derived_out:
        os.makedirs(os.path.dirname(derived_out), exist_ok=True)
        cols = FEATURE_COLUMNS + AGRO_FEATURES + [TARGET_COLUMN, "source"]
        data.reindex(columns=cols).to_csv(derived_out, index=False)

    return metrics


def default_paths() -> tuple[str, str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    backend = os.path.abspath(os.path.join(here, "..", ".."))
    return (
        os.path.join(backend, "data", "secondary", "crop_recommendation.csv"),
        os.path.join(backend, "data", "models"),
        os.path.join(backend, "data", "derived", "derived_dataset.csv"),
    )


if __name__ == "__main__":
    sec, out, derived = default_paths()
    m = train_and_save(sec, out, derived_out=derived)
    print(json.dumps({
        "best_model": m["best_model"]["key"],
        "main_track": {k: {"acc": v["test_accuracy"], "cv_f1": v["cv_macro_f1_mean"], "top3": v["top3_accuracy"]}
                       for k, v in m["models"].items()},
        "ablation_4_input": {k: {"acc": v["test_accuracy"], "cv_f1": v["cv_macro_f1_mean"], "top3": v["top3_accuracy"]}
                             for k, v in m["ablation_four_inputs"]["models"].items()},
        "model_kb": m["artifacts"]["model_size_kb"],
    }, indent=2))
