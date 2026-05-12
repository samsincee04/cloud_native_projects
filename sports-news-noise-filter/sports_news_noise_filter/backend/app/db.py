"""Postgres database engine and session factory."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# backend/.env wins over inherited shell exports (e.g. a stale DATABASE_URL in ~/.zshrc).
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_ROOT / ".env", override=True)


def _database_url() -> str:
    """Prefer psycopg (v3); plain ``postgresql://`` would otherwise select psycopg2 in SQLAlchemy."""
    raw = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://sports:sports@localhost:5432/sportsnews",
    ).strip()
    if raw.startswith("postgresql+psycopg://"):
        return raw
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://") :]
    return raw


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for ORM models."""


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session() -> Generator[Session, None, None]:
    """Yield a DB session (use in FastAPI dependencies in a later step)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def ensure_sport_columns() -> None:
    """Add ``sport`` columns on existing DBs (``create_all`` does not alter tables)."""
    ddl = (
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS sport VARCHAR(32)",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS sport VARCHAR(32)",
        "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS sports JSONB NOT NULL DEFAULT '[]'::jsonb",
    )
    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


def ensure_embedding_schema() -> None:
    """Enable pgvector and create the embedding storage table."""
    ddl = (
        "CREATE EXTENSION IF NOT EXISTS vector",
        """
        CREATE TABLE IF NOT EXISTS article_embeddings (
            article_id UUID PRIMARY KEY
                REFERENCES articles(id) ON DELETE CASCADE,
            model_name TEXT NOT NULL,
            embedding vector(384) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    )
    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


def ensure_llm_output_schema() -> None:
    """Add LLM output columns on clusters and daily_briefs table (idempotent for existing DBs)."""
    cluster_ddl = (
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS summary TEXT",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS what_changed TEXT",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS facts_json JSONB",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS entities_json JSONB",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS llm_model_name TEXT",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS llm_updated_at TIMESTAMPTZ",
    )
    daily_briefs_ddl = """
    CREATE TABLE IF NOT EXISTS daily_briefs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        brief_date DATE NOT NULL,
        sport TEXT NOT NULL,
        model_name TEXT NOT NULL,
        content_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_daily_briefs_brief_date_sport UNIQUE (brief_date, sport)
    )
    """
    with engine.begin() as conn:
        for stmt in cluster_ddl:
            conn.execute(text(stmt))
        conn.execute(text(daily_briefs_ddl))


def create_tables() -> None:
    """Create all tables registered on ``Base`` (import models first so metadata is populated)."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_sport_columns()
    ensure_embedding_schema()
    ensure_llm_output_schema()
