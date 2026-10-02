"""Full CRUD for the three core resources + the review workflow and the feedback loop."""

from __future__ import annotations

SAMPLE = {"soil_type": "laterite", "season": "Kharif", "rainfall_mm": 240,
          "water_availability": "high", "taluk": "Puttur", "notes": "crud test"}


def _create_prediction(client, headers):
    res = client.post("/api/history", json=SAMPLE, headers=headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["item"]


# ------------------------------------------------------------------ prediction history
def test_history_crud_round_trip(client, farmer_headers):
    item = _create_prediction(client, farmer_headers)
    hid = item["id"]

    listed = client.get("/api/history", headers=farmer_headers).get_json()
    assert listed["total"] >= 1
    assert any(r["id"] == hid for r in listed["items"])

    patched = client.patch(f"/api/history/{hid}", headers=farmer_headers,
                           json={"notes": "updated note"}).get_json()["item"]
    assert patched["notes"] == "updated note"

    assert client.delete(f"/api/history/{hid}", headers=farmer_headers).status_code == 200
    assert client.get(f"/api/history/{hid}", headers=farmer_headers).status_code == 404


def test_history_is_scoped_to_the_owner(client, farmer_headers, admin_headers):
    item = _create_prediction(client, farmer_headers)
    try:
        # another farmer cannot read it...
        other = client.post("/api/auth/register", json={
            "name": "Other", "email": "other-history@test.in", "password": "secret123"})
        if other.status_code == 201:
            headers = {"Authorization": "Bearer " + other.get_json()["token"]}
        else:
            res = client.post("/api/auth/login", json={"email": "other-history@test.in",
                                                       "password": "secret123"})
            headers = {"Authorization": "Bearer " + res.get_json()["token"]}
        assert client.get(f"/api/history/{item['id']}", headers=headers).status_code == 404
        # ... an admin can see it in the all-users view
        all_rows = client.get("/api/history?scope=all", headers=admin_headers).get_json()
        assert any(r["id"] == item["id"] for r in all_rows["items"])
    finally:
        client.delete(f"/api/history/{item['id']}", headers=farmer_headers)


def test_history_filters_and_summary(client, farmer_headers):
    items = [_create_prediction(client, farmer_headers) for _ in range(2)]
    try:
        filtered = client.get("/api/history?season=Kharif&limit=1", headers=farmer_headers).get_json()
        assert filtered["limit"] == 1 and len(filtered["items"]) <= 1
        summary = client.get("/api/history/summary", headers=farmer_headers).get_json()
        assert summary["total"] >= 2
        assert "avg_confidence" in summary and "top_crops" in summary
    finally:
        for it in items:
            client.delete(f"/api/history/{it['id']}", headers=farmer_headers)


def test_history_export_is_csv(client, farmer_headers):
    res = client.get("/api/history/export", headers=farmer_headers)
    assert res.status_code == 200
    assert res.mimetype == "text/csv"
    assert b"top_crop" in res.data


def test_history_rejects_unauthenticated_write(client):
    assert client.post("/api/history", json=SAMPLE).status_code == 401


# ------------------------------------------------------------------ primary surveys
def test_survey_crud_and_pending_status(client, farmer_headers, sample_survey):
    res = client.post("/api/surveys", json=sample_survey, headers=farmer_headers)
    assert res.status_code == 201, res.get_json()
    item = res.get_json()["item"]
    assert item["status"] == "pending"                # farmer rows need review
    assert item["consent"] is True
    assert item["water_availability"] == "low"        # derived from water_source=rainfed

    updated = client.patch(f"/api/surveys/{item['id']}", headers=farmer_headers,
                           json={"area_acres": 3.5}).get_json()["item"]
    assert updated["area_acres"] == 3.5
    assert client.delete(f"/api/surveys/{item['id']}", headers=farmer_headers).status_code == 200


def test_survey_without_consent_is_rejected(client, farmer_headers, sample_survey):
    res = client.post("/api/surveys", json={**sample_survey, "consent": False},
                      headers=farmer_headers)
    assert res.status_code == 400
    body = res.get_json()["error"]
    assert body["code"] == "cleaning_rules_failed"
    assert any("consent_required" in d for d in body["details"])


def test_survey_validation_details_are_actionable(client, farmer_headers, sample_survey):
    res = client.post("/api/surveys", json={**sample_survey, "rainfall_mm": 5000,
                                            "soil_type": "sand"},
                      headers=farmer_headers)
    details = res.get_json()["error"]["details"]
    assert any("rainfall_out_of_range" in d for d in details)
    assert any("invalid_vocabulary" in d for d in details)


def test_duplicate_survey_returns_409_then_force_creates(client, farmer_headers, sample_survey):
    # start clean so the assertion is not affected by rows left by another test
    existing = client.get("/api/surveys?search=DupVillage&limit=50",
                          headers=farmer_headers).get_json()["items"]
    for row in existing:
        client.delete(f"/api/surveys/{row['id']}", headers=farmer_headers)

    first = client.post("/api/surveys", json={**sample_survey, "village": "DupVillage"},
                        headers=farmer_headers)
    assert first.status_code == 201
    dup = client.post("/api/surveys", json={**sample_survey, "village": "DupVillage"},
                      headers=farmer_headers)
    assert dup.status_code == 409
    assert dup.get_json()["duplicate_of"]
    forced = client.post("/api/surveys", json={**sample_survey, "village": "DupVillage", "force": True},
                         headers=farmer_headers)
    assert forced.status_code == 201
    for row in (first.get_json()["item"], forced.get_json()["item"]):
        client.delete(f"/api/surveys/{row['id']}", headers=farmer_headers)


def test_admin_review_workflow(client, farmer_headers, admin_headers, sample_survey):
    created = client.post("/api/surveys", json={**sample_survey, "village": "ReviewVillage"},
                          headers=farmer_headers).get_json()["item"]
    try:
        queue = client.get("/api/surveys/review-queue", headers=admin_headers).get_json()
        assert any(r["id"] == created["id"] for r in queue["items"])

        bad = client.post(f"/api/surveys/{created['id']}/review", headers=admin_headers,
                          json={"status": "maybe"})
        assert bad.status_code == 400

        approved = client.post(f"/api/surveys/{created['id']}/review", headers=admin_headers,
                               json={"status": "approved", "review_note": "verified by phone"})
        assert approved.status_code == 200
        assert approved.get_json()["item"]["status"] == "approved"
    finally:
        client.delete(f"/api/surveys/{created['id']}", headers=admin_headers)


def test_cleaning_report_shows_merge_and_drop_counts(client, admin_headers):
    body = client.get("/api/surveys/cleaning-report", headers=admin_headers).get_json()
    assert body["approved_rows"] >= body["rows_merging_now"]
    assert len(body["rules"]) == 10
    assert "poor" in body["note"]


def test_survey_export_is_csv(client, farmer_headers):
    res = client.get("/api/surveys/export", headers=farmer_headers)
    assert res.status_code == 200 and res.mimetype == "text/csv"


# ------------------------------------------------------------------ feedback loop
def test_feedback_loop_writes_survey_row_when_consented(client, farmer_headers):
    pred = _create_prediction(client, farmer_headers)
    try:
        res = client.post(f"/api/history/{pred['id']}/feedback", headers=farmer_headers, json={
            "actual_crop": "rice", "yield_outcome": "good", "followed_advice": "yes",
            "feedback_notes": "pytest feedback", "add_to_dataset": True, "consent": True,
            "village": "Kabaka", "taluk": "Puttur", "area_acres": 1.5})
        assert res.status_code == 201, res.get_json()
        body = res.get_json()
        assert body["item"]["actual_crop"] == "rice"
        assert body["item"]["yield_outcome"] == "good"
        assert body["item"]["feedback_at"]
        assert body["created_survey"] is not None
        assert body["created_survey"]["status"] == "pending"
        assert body["created_survey"]["crop_grown"] == "rice"
        assert body["created_survey"]["sample_weight"] == 1.0
        client.delete(f"/api/surveys/{body['created_survey']['id']}", headers=farmer_headers)
    finally:
        client.delete(f"/api/history/{pred['id']}", headers=farmer_headers)


def test_feedback_without_consent_does_not_enter_the_dataset(client, farmer_headers):
    pred = _create_prediction(client, farmer_headers)
    try:
        res = client.post(f"/api/history/{pred['id']}/feedback", headers=farmer_headers, json={
            "actual_crop": "rice", "yield_outcome": "average", "add_to_dataset": True,
            "consent": False})
        assert res.status_code == 400
        assert res.get_json()["error"]["code"] == "survey_rejected"
    finally:
        client.delete(f"/api/history/{pred['id']}", headers=farmer_headers)


def test_feedback_rejects_bad_outcome(client, farmer_headers):
    pred = _create_prediction(client, farmer_headers)
    try:
        res = client.post(f"/api/history/{pred['id']}/feedback", headers=farmer_headers,
                          json={"actual_crop": "rice", "yield_outcome": "amazing"})
        assert res.status_code == 400
        assert res.get_json()["error"]["code"] == "invalid_yield_outcome"
    finally:
        client.delete(f"/api/history/{pred['id']}", headers=farmer_headers)
