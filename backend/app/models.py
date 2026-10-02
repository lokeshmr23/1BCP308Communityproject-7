"""ORM models: users, prediction history, primary farmer surveys, crop reference data."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="farmer", nullable=False)  # farmer | admin
    phone: Mapped[str | None] = mapped_column(String(20))
    village: Mapped[str | None] = mapped_column(String(120))
    taluk: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80), default="Dakshina Kannada")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    locale: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="user",
                                                           cascade="all, delete-orphan")
    # `reviewed_by` is a second FK to users, so the join column must be explicit here.
    surveys: Mapped[list["SurveyEntry"]] = relationship(
        back_populates="user", foreign_keys="SurveyEntry.user_id", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "email": self.email, "role": self.role,
            "phone": self.phone, "village": self.village, "taluk": self.taluk,
            "district": self.district, "is_active": self.is_active, "locale": self.locale,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Prediction(Base):
    """One row per saved recommendation request (CRUD resource #1)."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    soil_type: Mapped[str] = mapped_column(String(40), nullable=False)
    season: Mapped[str] = mapped_column(String(20), nullable=False)
    rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False)
    water_availability: Mapped[str] = mapped_column(String(20), nullable=False)
    irrigation_source: Mapped[str | None] = mapped_column(String(40))
    taluk: Mapped[str | None] = mapped_column(String(80))
    regional_tuning: Mapped[bool] = mapped_column(Boolean, default=True)

    top_crop: Mapped[str] = mapped_column(String(60), nullable=False)
    top_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    results_json: Mapped[str] = mapped_column(Text, nullable=False)   # full top-3 payload
    model_key: Mapped[str | None] = mapped_column(String(40))
    model_version: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    # feedback loop: what did the farmer actually do / harvest?
    actual_crop: Mapped[str | None] = mapped_column(String(60))
    yield_outcome: Mapped[str | None] = mapped_column(String(20))
    feedback_notes: Mapped[str | None] = mapped_column(Text)
    followed_advice: Mapped[str | None] = mapped_column(String(20))   # yes | partly | no
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User | None] = relationship(back_populates="predictions")

    @property
    def results(self) -> dict:
        try:
            return json.loads(self.results_json)
        except Exception:  # pragma: no cover
            return {}

    def to_dict(self, i18n: bool = False) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "farmer": (self.user.name if self.user else None),
            "village": (self.user.village if self.user else None),
            "taluk": self.taluk or (self.user.taluk if self.user else None),
            "soil_type": self.soil_type,
            "season": self.season,
            "rainfall_mm": self.rainfall_mm,
            "water_availability": self.water_availability,
            "irrigation_source": self.irrigation_source,
            "regional_tuning": self.regional_tuning,
            "top_crop": self.top_crop,
            "top_confidence": self.top_confidence,
            "results": self.results,
            "model_key": self.model_key,
            "model_version": self.model_version,
            "notes": self.notes,
            "actual_crop": self.actual_crop,
            "yield_outcome": self.yield_outcome,
            "feedback_notes": self.feedback_notes,
            "followed_advice": self.followed_advice,
            "feedback_at": self.feedback_at.isoformat() if self.feedback_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SurveyEntry(Base):
    """Primary dataset row contributed by a farmer / KVK staff member (CRUD resource #2).

    Duplicate handling deliberately lives in the application layer (cleaning rule 6), not in a
    database unique constraint: rule 6 collapses duplicate farmer/village/season/crop/rainfall
    submissions at MERGE time, and the API exposes a documented `force=true` escape hatch so a
    genuine repeat cultivation can still be recorded. A DB-level unique index would make that
    escape hatch impossible and turn it into a 500 error.
    """

    __tablename__ = "survey_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    farmer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    village: Mapped[str] = mapped_column(String(120), nullable=False)
    taluk: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))

    soil_type: Mapped[str] = mapped_column(String(40), nullable=False)
    season: Mapped[str] = mapped_column(String(20), nullable=False)
    rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False)
    water_source: Mapped[str] = mapped_column(String(40), nullable=False)   # irrigation source value
    water_availability: Mapped[str] = mapped_column(String(20), nullable=False)  # derived level

    crop_grown: Mapped[str] = mapped_column(String(60), nullable=False)
    yield_outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    area_acres: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    sample_weight: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User | None] = relationship(back_populates="surveys",
                                             foreign_keys=[user_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "farmer_name": self.farmer_name,
            "village": self.village,
            "taluk": self.taluk,
            "phone": self.phone,
            "soil_type": self.soil_type,
            "season": self.season,
            "rainfall_mm": self.rainfall_mm,
            "water_source": self.water_source,
            "water_availability": self.water_availability,
            "crop_grown": self.crop_grown,
            "yield_outcome": self.yield_outcome,
            "area_acres": self.area_acres,
            "notes": self.notes,
            "consent": self.consent,
            "status": self.status,
            "review_note": self.review_note,
            "sample_weight": self.sample_weight,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CropReference(Base):
    """Crop reference data, editable by admins (CRUD resource #3).

    Rows here override the built-in knowledge base for the rule-fit score and supply the
    values shown on the Crop Reference page.
    """

    __tablename__ = "crop_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crop_key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_kn: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40), default="cereal")

    seasons_json: Mapped[str] = mapped_column(Text, default="[]")
    soils_json: Mapped[str] = mapped_column(Text, default="[]")
    water_need: Mapped[str] = mapped_column(String(20), default="medium")
    rainfall_min: Mapped[float] = mapped_column(Float, default=30)
    rainfall_max: Mapped[float] = mapped_column(Float, default=200)
    ph_min: Mapped[float] = mapped_column(Float, default=5.5)
    ph_max: Mapped[float] = mapped_column(Float, default=7.5)
    temp_min: Mapped[float] = mapped_column(Float, default=18)
    temp_max: Mapped[float] = mapped_column(Float, default=35)
    total_water_mm: Mapped[str | None] = mapped_column(String(160))
    duration_days: Mapped[int | None] = mapped_column(Integer)
    dk_local: Mapped[bool] = mapped_column(Boolean, default=False)
    in_model_label_space: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "crop_key": self.crop_key,
            "name": self.name,
            "name_kn": self.name_kn,
            "category": self.category,
            "seasons": json.loads(self.seasons_json or "[]"),
            "soils": json.loads(self.soils_json or "[]"),
            "water_need": self.water_need,
            "rainfall_monthly_mm": [self.rainfall_min, self.rainfall_max],
            "ph": [self.ph_min, self.ph_max],
            "temp_c": [self.temp_min, self.temp_max],
            "total_water_mm": self.total_water_mm,
            "duration_days": self.duration_days,
            "dk_local": self.dk_local,
            "in_model_label_space": self.in_model_label_space,
            "note": self.note,
            "source": self.source,
            "source_url": self.source_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def kb_view(self) -> dict:
        """Shape used by the recommendation engine (mirrors ml.knowledge.CROPS entries)."""
        return {
            "en_name": self.name,
            "kn": self.name_kn or "",
            "category": self.category,
            "seasons": json.loads(self.seasons_json or "[]"),
            "soils": json.loads(self.soils_json or "[]"),
            "water_need": self.water_need,
            "rainfall_monthly": (self.rainfall_min, self.rainfall_max),
            "total_water_mm": self.total_water_mm or "not recorded",
            "ph": (self.ph_min, self.ph_max),
            "temp": (self.temp_min, self.temp_max),
            "duration_days": self.duration_days or 120,
            "dk_local": self.dk_local,
            "note": self.note or "",
            "source": self.source or "",
            "source_url": self.source_url,
        }


class AuditLog(Base):
    """Lightweight trail for admin actions (helps an evaluator see who changed what)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "action": self.action, "entity": self.entity,
                "entity_id": self.entity_id, "detail": self.detail,
                "created_at": self.created_at.isoformat() if self.created_at else None}
