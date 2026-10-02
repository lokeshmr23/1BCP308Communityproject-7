"""Health probe, authentication, roles and RBAC."""

from __future__ import annotations


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code in (200, 503)          # 503 only if the DB is unreachable
    body = res.get_json()
    assert body["status"] in ("ok", "degraded")
    assert body["app"] and body["version"]
    assert "database" in body and "connected" in body["database"]
    # the health probe must NOT load the model (that would defeat the lazy-load design)
    assert body["model"]["lazy"] is True


def test_health_reports_sqlite_as_non_persistent(client):
    body = client.get("/health").get_json()
    if body["database"]["engine"] == "sqlite":
        assert body["database"]["persistent"] is False


def test_register_and_login_flow(client):
    email = "newfarmer@test.in"
    res = client.post("/api/auth/register", json={
        "name": "New Farmer", "email": email, "password": "secret123",
        "village": "Ujire", "taluk": "Belthangady"})
    assert res.status_code in (201, 400)          # 400 if a previous run already created it
    res = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["user"]["role"] == "farmer"
    assert body["token"]


def test_login_rejects_wrong_password(client, seeded):
    res = client.post("/api/auth/login", json={"email": "farmer@test.in", "password": "nope"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "invalid_credentials"


def test_self_registration_as_admin_is_blocked(client):
    res = client.post("/api/auth/register", json={
        "name": "Sneaky", "email": "sneaky@test.in", "password": "secret123", "role": "admin"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "admin_signup_blocked"


def test_weak_password_rejected(client):
    res = client.post("/api/auth/register", json={
        "name": "Weak", "email": "weak@test.in", "password": "123"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "weak_password"


def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_profile_and_stats(client, farmer_headers):
    body = client.get("/api/auth/me", headers=farmer_headers).get_json()
    assert body["user"]["email"] == "farmer@test.in"
    assert "predictions" in body["stats"] and "surveys" in body["stats"]


def test_expired_or_garbage_token_is_rejected(client):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "invalid_token"


def test_farmer_cannot_write_crop_reference(client, farmer_headers):
    res = client.post("/api/crops", headers=farmer_headers,
                      json={"crop_key": "hack", "name": "Hack"})
    assert res.status_code == 403
    assert res.get_json()["error"]["code"] == "forbidden"


def test_farmer_cannot_use_admin_endpoints(client, farmer_headers):
    for path in ("/api/auth/users", "/api/surveys/cleaning-report", "/api/surveys/review-queue"):
        assert client.get(path, headers=farmer_headers).status_code == 403, path
    assert client.post("/api/model/retrain", headers=farmer_headers, json={}).status_code == 403


def test_admin_can_list_users(client, admin_headers):
    body = client.get("/api/auth/users", headers=admin_headers).get_json()
    assert body["total"] >= 2
    assert {u["role"] for u in body["users"]} <= {"farmer", "admin"}


def test_unknown_endpoint_and_method_errors_are_json(client):
    assert client.get("/api/does-not-exist").status_code == 404
    res = client.delete("/health")
    assert res.status_code == 405
    assert res.get_json()["error"]["code"] == "method_not_allowed"
