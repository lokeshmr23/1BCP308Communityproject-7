"""Shared API helpers: JSON errors, JWT auth, role gating, pagination, audit trail."""

from __future__ import annotations

import functools
from datetime import datetime, timedelta, timezone

import jwt
from flask import g, jsonify, request

from ..config import Config
from ..db import SessionLocal
from ..models import AuditLog, User


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "bad_request", details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details or []

    def to_response(self):
        return jsonify({"error": {"code": self.code, "message": self.message, "details": self.details}}), self.status


def bad_request(message: str, details=None, code: str = "bad_request"):
    raise ApiError(message, 400, code, details)


def not_found(message: str = "Resource not found"):
    raise ApiError(message, 404, "not_found")


def forbidden(message: str = "You do not have permission to do that"):
    raise ApiError(message, 403, "forbidden")


def unauthorised(message: str = "Authentication required"):
    raise ApiError(message, 401, "unauthorised")


# --------------------------------------------------------------------------- auth
def create_token(user: User, hours: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=hours or Config.JWT_EXPIRES_HOURS)
    payload = {"sub": str(user.id), "email": user.email, "role": user.role, "exp": exp,
               "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


def _user_from_token(token: str):
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ApiError("Session expired — please sign in again", 401, "token_expired")
    except jwt.InvalidTokenError:
        raise ApiError("Invalid session token", 401, "invalid_token")
    # Reuse the request-scoped session when one exists so a request never holds more than
    # one connection (the teardown handler in create_app() closes it).
    db = getattr(g, "_current_db", None)
    owns_session = db is None
    if db is None:
        db = SessionLocal()
        g._current_db = db
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        if owns_session:
            db.close()
        raise ApiError("Account not found or deactivated", 401, "invalid_user")
    return db, user


def current_user(optional: bool = False):
    """Resolve the caller from the Authorization header (or ?token= for CSV downloads)."""
    if getattr(g, "_current_user", None) is not None:
        return g._current_user
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else request.args.get("token", "")
    if not token:
        if optional:
            return None
        unauthorised()
    db, user = _user_from_token(token)
    g._current_db = db       # keep the session alive for the request
    g._current_user = user
    return user


def auth_required(role: str | None = None):
    """Route decorator. role='admin' also accepts admins only for write operations."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if role and user.role != role:
                forbidden(f"This action requires the '{role}' role (your role: {user.role})")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def optional_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        current_user(optional=True)
        return fn(*args, **kwargs)
    return wrapper


def audit(db, user, action: str, entity: str, entity_id=None, detail: str | None = None):
    db.add(AuditLog(user_id=getattr(user, "id", None), action=action, entity=entity,
                    entity_id=str(entity_id) if entity_id is not None else None, detail=detail))


# --------------------------------------------------------------------------- misc
MAX_LIMIT = 200


def pagination(default_limit: int = 20):
    try:
        limit = min(MAX_LIMIT, max(1, int(request.args.get("limit", default_limit))))
    except (TypeError, ValueError):
        limit = default_limit
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    return limit, offset


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        bad_request("Request body must be a JSON object")
    return data


def require_fields(data: dict, fields: list[str]):
    missing = [f for f in fields if data.get(f) in (None, "", [])]
    if missing:
        bad_request("Missing required field(s): " + ", ".join(missing), code="missing_fields")
