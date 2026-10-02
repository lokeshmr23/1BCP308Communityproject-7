"""Runtime configuration (env-driven, with sane local defaults)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_ROOT = BASE_DIR.parent                                 # repo root
DATA_DIR = BASE_DIR / "data"
SECONDARY_CSV = DATA_DIR / "secondary" / "crop_recommendation.csv"
DERIVED_CSV = DATA_DIR / "derived" / "derived_dataset.csv"
MODELS_DIR = DATA_DIR / "models"
MODEL_PATH = MODELS_DIR / "best_model.joblib"
METRICS_PATH = MODELS_DIR / "metrics.json"
FRONTEND_DIR = REPO_ROOT / "frontend"


def _normalise_db_url(url: str) -> str:
    """Render/Heroku hand out postgres:// URLs; SQLAlchemy 2.x wants a driver name."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


class Config:
    # --- paths ----------------------------------------------------------------
    BASE_DIR = BASE_DIR
    REPO_ROOT = REPO_ROOT
    DATA_DIR = DATA_DIR
    SECONDARY_CSV = SECONDARY_CSV
    DERIVED_CSV = DERIVED_CSV
    MODELS_DIR = MODELS_DIR
    MODEL_PATH = MODEL_PATH
    METRICS_PATH = METRICS_PATH
    FRONTEND_DIR = FRONTEND_DIR

    # --- database -------------------------------------------------------------
    # Local dev: SQLite file. Production (Render free tier): set DATABASE_URL to a
    # free hosted Postgres (Neon / Supabase) because Render's free disk is EPHEMERAL.
    DATABASE_URL = _normalise_db_url(
        os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'crop_advisor.db'}"
    )
    SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "0") == "1"

    # --- auth -----------------------------------------------------------------
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "24"))

    # --- app ------------------------------------------------------------------
    APP_NAME = "Dakshina Kannada Crop Advisor"
    APP_VERSION = "1.0.0"
    DISTRICT = "Dakshina Kannada, Karnataka"
    # Comma-separated list, or "*" (the front-end is served from the same origin,
    # and Render previews / localhost may differ, so the default is permissive).
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "en")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # First admin is created by the seed script; these are only used to bootstrap.
    BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@cropadvisor.in")
    BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "admin123")
