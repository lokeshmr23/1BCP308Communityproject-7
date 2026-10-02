"""
Shared pytest fixtures.

The test suite always runs against a throwaway SQLite database in a temp directory and
never touches the demo database or the shipped model artefact, so `pytest` is safe to run
on a machine that is also running the demo.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# MUST be set before app.db is imported: the engine is created at import time.
_TMP_DB = Path(tempfile.mkdtemp(prefix="cropadvisor-tests-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture(scope="session")
def app():
    from app import create_app
    from app.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def seeded(app):
    """One admin + one farmer, created once per session."""
    from app.db import SessionLocal
    from app.models import User
    from werkzeug.security import generate_password_hash

    db = SessionLocal()
    try:
        out = {}
        for email, role, name in (("admin@test.in", "admin", "Test Admin"),
                                  ("farmer@test.in", "farmer", "Test Farmer")):
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(name=name, email=email, role=role,
                            password_hash=generate_password_hash("secret123"),
                            village="Kabaka", taluk="Puttur", district="Dakshina Kannada",
                            phone="+91 90000 00000")
                db.add(user)
                db.commit()
            out[role] = user.id
        return out
    finally:
        db.close()


def _token(client, email: str, password: str = "secret123") -> str:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["token"]


@pytest.fixture()
def farmer_headers(client, seeded):
    return {"Authorization": "Bearer " + _token(client, "farmer@test.in")}


@pytest.fixture()
def admin_headers(client, seeded):
    return {"Authorization": "Bearer " + _token(client, "admin@test.in")}


@pytest.fixture()
def sample_survey():
    return {
        "farmer_name": "Test Farmer", "village": "Kabaka", "taluk": "Puttur",
        "phone": "+91 90000 00000", "soil_type": "laterite", "season": "Kharif",
        "rainfall_mm": 240, "water_source": "rainfed", "crop_grown": "rice",
        "yield_outcome": "good", "area_acres": 1.2, "notes": "pytest row", "consent": True,
    }
