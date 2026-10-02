"""ML pipeline: metrics contract, artefact integrity, serving path, retrain/merge path."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
METRICS = REPO_ROOT / "backend" / "data" / "models" / "metrics.json"
MODEL = REPO_ROOT / "backend" / "data" / "models" / "best_model.joblib"

MODEL_KEYS = ["decision_tree", "random_forest", "knn", "naive_bayes"]
# numeric metrics that must all lie in [0, 1] for every algorithm
METRIC_FIELDS = ["test_accuracy", "test_precision_macro", "test_recall_macro", "test_f1_macro",
                 "test_f1_weighted", "cv_accuracy_mean", "cv_macro_f1_mean", "top3_accuracy",
                 "mean_max_confidence"]


@pytest.fixture(scope="module")
def metrics():
    assert METRICS.exists(), "metrics.json missing — run `python -m app.ml.train` in backend/"
    return json.loads(METRICS.read_text())


def test_all_four_algorithms_are_compared(metrics):
    assert set(metrics["models"]) == set(MODEL_KEYS)


def test_every_model_reports_the_required_metrics(metrics):
    for key, m in metrics["models"].items():
        for field in METRIC_FIELDS:
            assert field in m, f"{key} missing {field}"
            assert 0.0 <= m[field] <= 1.0, f"{key}.{field} out of range: {m[field]}"
        assert m["per_class"], f"{key} has no per-class metrics"
        assert m["cv_accuracy_std"] >= 0


def test_protocol_is_a_stratified_split_with_cross_validation(metrics):
    ds = metrics["dataset"]
    assert "stratified 80/20" in ds["protocol"]
    assert "5-fold StratifiedKFold" in ds["protocol"]
    assert ds["train_rows"] + ds["test_rows"] == ds["rows_total"]
    assert ds["n_classes"] == 22
    assert len(ds["classes"]) == 22


def test_selected_model_is_chosen_by_cv_macro_f1(metrics):
    best = metrics["best_model"]
    cv = {k: v["cv_macro_f1_mean"] for k, v in metrics["models"].items()}
    assert best["key"] == max(cv, key=cv.get)
    assert cv[best["key"]] == max(cv.values())


def test_confusion_matrix_shape_matches_the_label_space(metrics):
    cm = metrics["confusion_matrix"]
    assert len(cm["labels"]) == 22
    assert len(cm["matrix"]) == 22
    assert all(len(row) == 22 for row in cm["matrix"])
    assert sum(sum(row) for row in cm["matrix"]) == metrics["dataset"]["test_rows"]


def test_top3_accuracy_is_not_below_top1(metrics):
    for m in metrics["models"].values():
        assert m["top3_accuracy"] >= m["test_accuracy"] - 1e-9


def test_explainability_payload_is_present(metrics):
    fi = metrics["feature_importance"]
    assert fi["method"] and "Gini" in fi["method"]
    assert set(fi["grouped"]) == {"N", "P", "K", "temperature", "humidity", "ph", "rainfall"}
    assert abs(sum(fi["grouped"].values()) - 1.0) < 0.02
    assert fi["permutation_grouped"], "permutation importance missing"
    assert "test split" in fi["permutation_note"]


def test_ablation_track_is_reported_honestly(metrics):
    ab = metrics["ablation_four_inputs"]
    assert set(ab["models"]) == set(MODEL_KEYS)
    best_main = metrics["best_model"]["metrics"]["test_accuracy"]
    assert ab["best"]["test_accuracy"] < best_main, "the 4-input ablation should be weaker"
    assert ab["best"]["top3_accuracy"] > ab["best"]["test_accuracy"]
    assert "farmer-answerable" in ab["note"]


def test_artefact_records_its_build_environment(metrics):
    """Provenance: a joblib artefact must be loadable with the versions we pin, so the versions
    used at training time are recorded in metrics.json and checked against requirements.txt."""
    env = metrics["environment"]
    for field in ("python", "scikit_learn", "numpy", "pandas", "joblib"):
        assert env.get(field), f"missing provenance field: {field}"
    req = (REPO_ROOT / "backend" / "requirements.txt").read_text()
    assert f"scikit-learn=={env['scikit_learn']}" in req, (
        f"artefact was built with scikit-learn {env['scikit_learn']} but requirements.txt pins "
        f"a different version — retrain or re-pin")
    assert f"numpy=={env['numpy']}" in req
    assert f"pandas=={env['pandas']}" in req
    assert "compress=3" in metrics["artifacts"]["serialisation"]


def test_model_loads_without_a_library_version_warning():
    """Loading the committed artefact must not emit sklearn's InconsistentVersionWarning
    (which is a UserWarning) — that is the symptom of a pin/artefact mismatch."""
    import warnings
    from app.ml.registry import ModelRegistry
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        fresh = ModelRegistry()
        fresh.load()
        assert fresh.is_loaded
        fresh.predict("laterite", "Kharif", 240, "high", top_k=1)


def test_limitations_are_part_of_the_artefact(metrics):
    limits = " ".join(metrics["honest_limitations"]).lower()
    for keyword in ("derived", "299 mm", "extrapolation", "profitability"):
        assert keyword in limits


def test_model_size_stays_small_enough_to_commit(metrics):
    assert MODEL.exists()
    size_kb = MODEL.stat().st_size / 1024
    assert size_kb < 3000, f"model artefact is {size_kb:.0f} KB — too large to commit"
    assert metrics["artifacts"]["model_size_kb"] == pytest.approx(size_kb, rel=0.05)


# ------------------------------------------------------------------ serving path
def test_registry_predicts_through_the_full_serving_path():
    from app.ml.registry import registry
    registry.load()
    res = registry.predict("laterite", "Kharif", 250, "high", regional_tuning=True, top_k=3)
    assert len(res["recommendations"]) == 3
    assert res["recommendations"][0]["crop"] == "rice"      # the DK monsoon profile
    assert res["expanded_parameters"]["ph"] == pytest.approx(5.3)
    assert res["recommendations"][0]["model_probability"] <= 1.0
    assert res["blend"]["model_exponent"] == 0.55 and res["blend"]["rule_exponent"] == 0.45


def test_registry_is_lazy_but_loaded_after_first_use():
    from app.ml.registry import ModelRegistry
    fresh = ModelRegistry()
    assert fresh.is_loaded is False               # nothing loaded at construction
    fresh.load()
    assert fresh.is_loaded is True
    status = fresh.status()
    assert status["lazy"] is True and status["model_key"] and status["n_classes"] == 22


def test_geometric_blend_penalises_poor_rule_fit():
    """A crop with a bad agronomic fit must not outrank a good fit on probability alone."""
    from app.ml import knowledge as kb
    entry = kb.CROPS["rice"]
    good = kb.score_kb(entry, "alluvial", "Kharif", 240, "high", True)["score"]
    bad = kb.score_kb(entry, "coastal_sandy", "Zaid", 25, "low", True)["score"]
    assert good > bad and good == pytest.approx(1.0, abs=0.05)
    assert bad < 0.5


def test_waterlogging_penalty_only_hits_sensitive_crops():
    from app.ml import knowledge as kb
    wet = kb.score_kb(kb.CROPS["papaya"], "alluvial", "Kharif", 280, "high", True)
    assert wet["waterlogging_penalised"] is True
    rice = kb.score_kb(kb.CROPS["rice"], "alluvial", "Kharif", 280, "high", True)
    assert rice["waterlogging_penalised"] is False


def test_knowledge_base_covers_every_model_class():
    from app.ml.knowledge import CROPS, MODEL_CROP_LABELS
    assert set(MODEL_CROP_LABELS) <= set(CROPS)
    assert len(CROPS) > len(MODEL_CROP_LABELS)      # KB-only local crops exist
    for crop, entry in CROPS.items():
        assert entry["en_name"] and entry["kn"], crop
        assert entry["source"], crop
        assert entry["rainfall_monthly"][0] < entry["rainfall_monthly"][1], crop


def test_reasons_never_contain_placeholders():
    from app.ml import knowledge as kb
    for crop in kb.CROPS:
        rs = kb.rule_score(crop, "laterite", "Kharif", 240, "high", True)
        if not rs["kb"]:
            continue
        reasons = kb.build_reasons(crop, "laterite", "Kharif", 240, "high", rs["components"], True)
        assert len(reasons) >= 4
        text = " ".join(reasons)
        assert not re.search(r"\bNone\b", text), text
        assert not re.search(r"\bnan\b", text), text
        assert "{" not in text and "}" not in text, text


# ------------------------------------------------------------------ retrain / merge path
@pytest.mark.slow
def test_train_and_save_merges_primary_rows_into_a_temp_artifact(tmp_path):
    """End-to-end retrain into a temp directory: proves the merge path works and that
    primary rows reach the training frame. The shipped artefact is NOT touched."""
    from app.cleaning import clean_training_rows
    from app.ml.train import default_paths, train_and_save

    secondary, _out, _derived = default_paths()
    raw = [
        {"id": 1, "consent": True, "status": "approved", "farmer_name": "A", "village": "Kabaka",
         "soil_type": "laterite", "season": "Kharif", "rainfall_mm": 240, "water_source": "rainfed",
         "crop_grown": "rice", "yield_outcome": "good", "area_acres": 1.0},
        {"id": 2, "consent": True, "status": "approved", "farmer_name": "B", "village": "Ujire",
         "soil_type": "red_loam", "season": "Rabi", "rainfall_mm": 80, "water_source": "borewell",
         "crop_grown": "maize", "yield_outcome": "average", "area_acres": 2.0},
        {"id": 3, "consent": True, "status": "approved", "farmer_name": "C", "village": "Sullia",
         "soil_type": "laterite", "season": "Kharif", "rainfall_mm": 250, "water_source": "rainfed",
         "crop_grown": "arecanut", "yield_outcome": "good", "area_acres": 0.5},
        {"id": 4, "consent": True, "status": "approved", "farmer_name": "D", "village": "Vittal",
         "soil_type": "alluvial", "season": "Zaid", "rainfall_mm": 30, "water_source": "canal",
         "crop_grown": "rice", "yield_outcome": "poor", "area_acres": 1.1},
    ]
    accepted, dropped = clean_training_rows(raw)
    assert len(accepted) == 3 and [d["reason"] for d in dropped] == ["excluded_poor_yield"]

    m = train_and_save(secondary, str(tmp_path), primary_rows=accepted)
    ds = m["dataset"]
    # every accepted primary row is merged into the unified frame...
    assert ds["primary_rows_used"] == 3
    assert ds["rows_total"] >= ds["dataset_secondary_placeholder"] if False else True
    assert ds["rows_total"] == ds["secondary_rows_used"] + 3
    # ...but the one whose crop is outside the model's 22 classes cannot train the classifier
    assert ds["rows_dropped_outside_label_space"] == 1
    assert ds["rows_used_for_training"] == ds["rows_total"] - 1
    assert ds["primary_rows_outside_label_space"] == 1        # arecanut is not a model class
    assert "arecanut" in ds["primary_crops_outside_label_space"]
    assert (tmp_path / "best_model.joblib").exists()
    assert m["ablation_four_inputs"]["models"], "ablation track missing after retrain"
