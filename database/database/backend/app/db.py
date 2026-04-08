"""
Database access using SQLAlchemy Core with explicit SQL strings.
No ORM models or sessions; all queries are text-based.
"""
import os
from sqlalchemy import create_engine, text

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = os.getenv("DATABASE_URL", "").strip()
        if not url:
            raise ValueError("DATABASE_URL environment variable is not set")
        _engine = create_engine(url)
    return _engine


def init_db():
    """Create summaries table if it does not exist; ensure required columns exist."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS summaries (
                id         SERIAL PRIMARY KEY,
                summary    TEXT NOT NULL,
                model      VARCHAR(255) NOT NULL,
                truncated  BOOLEAN NOT NULL DEFAULT FALSE,
                latency_ms INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        # Handle upgrades: CREATE TABLE IF NOT EXISTS doesn't add new columns.
        conn.execute(text("""
            ALTER TABLE summaries
            ADD COLUMN IF NOT EXISTS latency_ms INTEGER
        """))
        conn.commit()


def insert_summary(summary: str, model: str, truncated: bool, latency_ms: int) -> None:
    """Insert one row into summaries."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO summaries (summary, model, truncated, latency_ms)
                VALUES (:summary, :model, :truncated, :latency_ms)
            """),
            {"summary": summary, "model": model, "truncated": truncated, "latency_ms": latency_ms},
        )
        conn.commit()


def get_recent_summaries(limit: int = 50) -> list[dict]:
    """Return recent summaries ordered by created_at descending."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, summary, model, truncated, latency_ms, created_at
                FROM summaries
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        rows = result.fetchall()
    return [
        {
            "id": r[0],
            "summary": r[1],
            "model": r[2],
            "truncated": r[3],
            "latency_ms": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]
