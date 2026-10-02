"""Crop reference CRUD (admin write path) and its effect on the recommendation engine."""

from __future__ import annotations


def test_public_reference_list_is_readable_without_auth(client):
    body = client.get("/api/crops/reference").get_json()
    assert body["count"] >= 30
    assert all("kb_only" in c for c in body["crops"])


def test_import_defaults_populates_the_editable_table(client, admin_headers):
    res = client.post("/api/crops/import-defaults", headers=admin_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["total_builtin"] >= 30
    listed = client.get("/api/crops?limit=100").get_json()
    assert listed["total"] >= 30
    assert listed["items"][0]["crop_key"]


def test_crop_crud_round_trip(client, admin_headers):
    created = client.post("/api/crops", headers=admin_headers, json={
        "crop_key": "pytest_crop", "name": "Pytest Crop", "category": "cereal",
        "seasons": ["Kharif"], "soils": ["laterite"], "water_need": "medium",
        "rainfall_min": 50, "rainfall_max": 150, "dk_local": True}).get_json()["item"]
    cid = created["id"]
    try:
        assert created["rainfall_monthly_mm"] == [50, 150]

        patched = client.patch(f"/api/crops/{cid}", headers=admin_headers,
                               json={"water_need": "high", "note": "updated"}).get_json()["item"]
        assert patched["water_need"] == "high" and patched["note"] == "updated"

        assert client.get(f"/api/crops/{cid}").get_json()["item"]["crop_key"] == "pytest_crop"
    finally:
        assert client.delete(f"/api/crops/{cid}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/crops/{cid}").status_code == 404


def test_crop_validation_rules(client, admin_headers):
    bad_cases = [
        ({"crop_key": "x1", "name": "X", "water_need": "lots"}, "invalid_water_need"),
        ({"crop_key": "x2", "name": "X", "seasons": ["Monsoon"]}, "invalid_seasons"),
        ({"crop_key": "x3", "name": "X", "soils": ["moon_dust"]}, "invalid_soils"),
        ({"crop_key": "x4", "name": "X", "rainfall_min": 200, "rainfall_max": 100}, "invalid_range"),
    ]
    for payload, code in bad_cases:
        res = client.post("/api/crops", headers=admin_headers, json=payload)
        assert res.status_code == 400, payload
        assert res.get_json()["error"]["code"] == code


def test_duplicate_crop_key_is_rejected(client, admin_headers):
    client.post("/api/crops", headers=admin_headers,
                json={"crop_key": "dup_crop", "name": "Dup"})
    res = client.post("/api/crops", headers=admin_headers,
                      json={"crop_key": "dup_crop", "name": "Dup Again"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "duplicate_crop_key"
    listed = client.get("/api/crops?search=dup_crop").get_json()["items"]
    for row in listed:
        client.delete(f"/api/crops/{row['id']}", headers=admin_headers)


def test_editing_a_crop_changes_the_rule_fit_score(client, admin_headers):
    """The knowledge base is not decoration: an admin edit must change the ranking inputs."""
    from app.db import SessionLocal
    from app.ml.registry import registry

    # import the built-in rows if needed, then edit the real 'rice' row (not a copy)
    client.post("/api/crops/import-defaults", headers=admin_headers)
    rows = client.get("/api/crops?search=rice&limit=50").get_json()["items"]
    rice = next(r for r in rows if r["crop_key"] == "rice")
    cid = rice["id"]
    original = {"water_need": rice["water_need"],
                "rainfall_min": rice["rainfall_monthly_mm"][0],
                "rainfall_max": rice["rainfall_monthly_mm"][1]}
    try:
        client.patch(f"/api/crops/{cid}", headers=admin_headers, json={
            "water_need": "low", "rainfall_min": 10, "rainfall_max": 50})
        db = SessionLocal()
        try:
            kb_map = registry.effective_kb(db)
            assert kb_map["rice"]["water_need"] == "low"          # override in force
            from app.ml.knowledge import score_kb
            score = score_kb(kb_map["rice"], "laterite", "Kharif", 240, "high", True)["score"]
            assert score < 0.75, "an edited (worse) crop profile should lower the rule fit"
        finally:
            db.close()
    finally:
        client.patch(f"/api/crops/{cid}", headers=admin_headers, json=original)
        registry.invalidate_kb_cache()


def test_empty_state_hint_is_returned_when_no_rows_match(client):
    res = client.get("/api/crops?search=zzz-no-such-crop")
    assert res.status_code == 200
    body = res.get_json()
    if body["total"] == 0:
        assert "import-defaults" in body["hint"]
