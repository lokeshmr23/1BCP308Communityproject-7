"""/api/predict contract, validation, transparency payload and the serving path."""

from __future__ import annotations

VALID = {"soil_type": "laterite", "season": "Kharif", "rainfall_mm": 240,
         "water_availability": "high"}


def test_meta_returns_form_vocabularies(client):
    body = client.get("/api/meta").get_json()
    assert len(body["soil_types"]) >= 6
    assert [s["value"] for s in body["seasons"]] == ["Kharif", "Rabi", "Zaid"]
    assert [w["value"] for w in body["water_levels"]] == ["low", "medium", "high"]
    assert any(s["value"] == "rainfed" for s in body["irrigation_sources"])
    assert len(body["model_crops"]) == 22
    assert "formula" in body["blend"]


def test_predict_anonymous_returns_top3_with_reasons(client):
    res = client.post("/api/predict", json=VALID)
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["recommendations"]) == 3
    for i, rec in enumerate(body["recommendations"], start=1):
        assert rec["rank"] == i
        assert 0 <= rec["confidence"] <= 1
        assert 0 <= rec["model_probability"] <= 1
        assert 0 <= rec["rule_fit"] <= 1
        assert rec["name"] and rec["name_kn"]
        assert isinstance(rec["reasons"], list) and len(rec["reasons"]) >= 4
        assert set(rec["rule_components"]) == {"water", "season", "rain", "soil"}
        assert rec["status"] in ("strong match", "reasonable match", "weak match - verify locally")
    # ranked by blended score
    scores = [r["confidence"] for r in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    # transparency blocks
    assert set(body["expanded_parameters"]) == {"N", "P", "K", "temperature", "humidity", "ph", "rainfall"}
    assert len(body["expansion_audit"]) == 3
    assert body["confidence_note"] and body["disclaimer"]
    assert body["model"]["key"] and body["model"]["version"]


def test_predict_includes_knowledge_base_advisory_flagged_as_not_model_output(client):
    body = client.post("/api/predict", json=VALID).get_json()
    for adv in body["regional_advisory"]:
        assert adv["name"] and adv["reasons"]
        assert "NOT in the secondary dataset" in adv["disclaimer"]
        # advisory crops must never appear as model predictions
        assert adv["crop"] not in [r["crop"] for r in body["recommendations"]]


def test_deterministic_for_same_input(client):
    a = client.post("/api/predict", json=VALID).get_json()
    b = client.post("/api/predict", json=VALID).get_json()
    assert [r["crop"] for r in a["recommendations"]] == [r["crop"] for r in b["recommendations"]]
    assert a["recommendations"][0]["confidence"] == b["recommendations"][0]["confidence"]


def test_irrigation_source_drives_water_availability(client):
    with_source = client.post("/api/predict", json={**VALID, "irrigation_source": "rainfed",
                                                    "water_availability": "high"}).get_json()
    assert with_source["input"]["water_availability"] == "low"      # rainfed wins over the field


def test_regional_tuning_changes_the_ranking_priors(client):
    on = client.post("/api/predict", json={**VALID, "regional_tuning": True}).get_json()
    off = client.post("/api/predict", json={**VALID, "regional_tuning": False}).get_json()
    assert on["blend"]["regional_prior"] != off["blend"]["regional_prior"]
    assert off["regional_advisory"] == []            # advisories only make sense with tuning on


def test_validation_errors_are_structured(client):
    cases = [
        ({**VALID, "soil_type": "moon_dust"}, "invalid_soil_type"),
        ({**VALID, "season": "Monsoon2"}, "invalid_season"),
        ({**VALID, "water_availability": "plenty"}, "invalid_water_availability"),
        ({**VALID, "rainfall_mm": "lots"}, "invalid_rainfall"),
        ({**VALID, "rainfall_mm": 5000}, "rainfall_out_of_range"),
    ]
    for payload, code in cases:
        res = client.post("/api/predict", json=payload)
        assert res.status_code == 400, payload
        assert res.get_json()["error"]["code"] == code


def test_rainfall_error_message_explains_the_district_scale(client):
    res = client.post("/api/predict", json={**VALID, "rainfall_mm": 3900})
    assert "annual district rainfall" in res.get_json()["error"]["message"]


def test_save_requires_login(client):
    res = client.post("/api/predict", json={**VALID, "save": True})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "login_required_to_save"


def test_save_persists_history_row(client, farmer_headers):
    res = client.post("/api/predict", json={**VALID, "save": True, "taluk": "Puttur"},
                      headers=farmer_headers)
    assert res.status_code == 200
    saved = res.get_json()["saved"]
    assert saved["id"] and saved["top_crop"]
    assert saved["results"]["recommendations"][0]["crop"] == saved["top_crop"]
    # the saved row is readable, then cleaned up
    assert client.get(f"/api/history/{saved['id']}", headers=farmer_headers).status_code == 200
    assert client.delete(f"/api/history/{saved['id']}", headers=farmer_headers).status_code == 200


def test_expansion_rules_and_cleaning_rules_are_public(client):
    exp = client.get("/api/expansion-rules").get_json()
    assert set(exp["soil_profiles"]) >= {"laterite", "coastal_sandy"}
    assert set(exp["season_profiles"]) == {"Kharif", "Rabi", "Zaid"}
    rules = client.get("/api/cleaning-rules").get_json()
    assert len(rules["primary_data_rules"]) == 10
    assert len(rules["secondary_data_rules"]) == 5


def test_crop_reference_public_marks_kb_only_crops(client):
    body = client.get("/api/crops/reference").get_json()
    assert body["count"] >= 30
    kb_only = [c for c in body["crops"] if c["kb_only"]]
    assert any(c["crop"] == "arecanut" for c in kb_only)
    assert all(c["in_model_label_space"] == (not c["kb_only"]) for c in body["crops"])
