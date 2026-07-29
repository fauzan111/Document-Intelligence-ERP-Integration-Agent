"""SQLAlchemy engine + session factory. Declarative base for all models."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalize_db_url(url: str) -> str:
    """Managed hosts (Render, Heroku) hand out ``postgres://``, which SQLAlchemy
    2.0 no longer accepts. Rewrite to the explicit psycopg2 driver URL."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


_settings = get_settings()
engine = create_engine(_normalize_db_url(_settings.database_url), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
