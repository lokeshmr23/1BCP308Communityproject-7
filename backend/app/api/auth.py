"""Authentication: register (farmer), login, profile, admin user management."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import SessionLocal
from ..models import Prediction, SurveyEntry, User
from .utils import (audit, auth_required, bad_request, body, create_token, current_user,
                    not_found, pagination, require_fields)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register():
    data = body()
    require_fields(data, ["name", "email", "password"])
    email = data["email"].strip().lower()
    if "@" not in email or "." not in email:
        bad_request("Please provide a valid email address", code="invalid_email")
    if len(data["password"]) < 6:
        bad_request("Password must be at least 6 characters", code="weak_password")
    role = (data.get("role") or "farmer").lower()
    if role not in ("farmer", "admin"):
        bad_request("role must be 'farmer' or 'admin'", code="invalid_role")
    # Self-registration as admin is intentionally blocked: the role exists for the
    # project evaluator / KVK staff account created by the seed script.
    if role == "admin":
        bad_request("Admin accounts are provisioned by the seed script or an existing admin. "
                    "Register as a farmer, or use the demo evaluator login.", code="admin_signup_blocked")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            bad_request("An account with this email already exists", code="email_taken")
        user = User(
            name=data["name"].strip(), email=email,
            password_hash=generate_password_hash(data["password"]),
            role="farmer", phone=data.get("phone"), village=data.get("village"),
            taluk=data.get("taluk"), district=data.get("district", "Dakshina Kannada"),
            locale=data.get("locale", "en"),
        )
        db.add(user)
        db.commit()
        audit(db, user, "register", "user", user.id)
        db.commit()
        return jsonify({"user": user.to_dict(), "token": create_token(user)}), 201
    finally:
        db.close()


@bp.post("/login")
def login():
    data = body()
    require_fields(data, ["email", "password"])
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == data["email"].strip().lower()).first()
        if not user or not check_password_hash(user.password_hash, data["password"]):
            bad_request("Incorrect email or password", code="invalid_credentials")
        if not user.is_active:
            bad_request("This account has been deactivated", code="inactive_user")
        return jsonify({"user": user.to_dict(), "token": create_token(user)})
    finally:
        db.close()


@bp.get("/me")
@auth_required()
def me():
    user = current_user()
    db = SessionLocal()
    try:
        return jsonify({
            "user": user.to_dict(),
            "stats": {
                "predictions": db.query(Prediction).filter(Prediction.user_id == user.id).count(),
                "surveys": db.query(SurveyEntry).filter(SurveyEntry.user_id == user.id).count(),
            },
        })
    finally:
        db.close()


@bp.put("/me")
@auth_required()
def update_me():
    data = body()
    db = SessionLocal()
    try:
        user = db.get(User, current_user().id)
        for field in ("name", "phone", "village", "taluk", "district", "locale"):
            if field in data and data[field] is not None:
                setattr(user, field, data[field])
        if data.get("password"):
            if len(data["password"]) < 6:
                bad_request("Password must be at least 6 characters", code="weak_password")
            user.password_hash = generate_password_hash(data["password"])
        db.commit()
        return jsonify({"user": user.to_dict()})
    finally:
        db.close()


@bp.get("/users")
@auth_required(role="admin")
def list_users():
    limit, offset = pagination(50)
    db = SessionLocal()
    try:
        q = db.query(User)
        if request.args.get("role"):
            q = q.filter(User.role == request.args["role"])
        total = q.count()
        users = q.order_by(User.id).offset(offset).limit(limit).all()
        return jsonify({"total": total, "limit": limit, "offset": offset,
                        "users": [u.to_dict() for u in users]})
    finally:
        db.close()


@bp.patch("/users/<int:user_id>")
@auth_required(role="admin")
def update_user(user_id: int):
    data = body()
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            not_found("User not found")
        if "role" in data:
            if data["role"] not in ("farmer", "admin"):
                bad_request("role must be 'farmer' or 'admin'", code="invalid_role")
            user.role = data["role"]
        if "is_active" in data:
            user.is_active = bool(data["is_active"])
        for field in ("name", "phone", "village", "taluk"):
            if field in data and data[field] is not None:
                setattr(user, field, data[field])
        audit(db, current_user(), "update", "user", user.id, detail=str(data))
        db.commit()
        return jsonify({"user": user.to_dict()})
    finally:
        db.close()
