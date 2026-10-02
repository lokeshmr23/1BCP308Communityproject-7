"""SQLAlchemy setup: engine/session management and the declarative base.

Works unchanged against:
  * SQLite (local development / tests)
  * hosted Postgres free tiers: Neon, Supabase (production on Render, whose free disk
    is ephemeral, so a hosted database is required for persistence)
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import Config

_is_sqlite = Config.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    Config.DATABASE_URL,
    echo=Config.SQLALCHEMY_ECHO,
    future=True,
    pool_pre_ping=True,        # survives the connection reaping that free tiers do
    **({} if _is_sqlite else {"pool_recycle": 280, "pool_size": 5, "max_overflow": 5}),
    **({"connect_args": {"check_same_thread": False}} if _is_sqlite else {}),
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover - sqlite only
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create tables if they do not exist (idempotent)."""
    from . import models  # noqa: F401  (register mappers)
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    """FastAPI-style dependency, used by the Flask helpers below."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
