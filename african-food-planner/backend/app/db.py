import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_NOTIFICATIONS_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        metadata_json JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        read_at TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_notifications_user_id
    ON notifications (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_notifications_user_created_at
    ON notifications (user_id, created_at DESC)
    """,
)


def ensure_notifications_schema() -> None:
    """Apply notifications DDL idempotently (for DBs created before the model existed)."""
    with engine.begin() as conn:
        for stmt in _NOTIFICATIONS_STATEMENTS:
            conn.execute(text(stmt))


def create_tables() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_notifications_schema()
