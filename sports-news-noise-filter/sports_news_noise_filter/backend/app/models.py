"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    preferences: Mapped[Preferences | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Preferences(Base):
    __tablename__ = "preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topics: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    sports: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    user: Mapped[User] = relationship(back_populates="preferences")


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    headline: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sport: Mapped[str | None] = mapped_column(String(32), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    # LLM outputs (nullable when LLM is off or not yet run)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_changed: Mapped[str | None] = mapped_column(Text, nullable=True)
    facts_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    entities_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    llm_model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    articles: Mapped[list[Article]] = relationship(
        back_populates="cluster",
        order_by="Article.created_at",
    )


class DailyBrief(Base):
    """Daily per-sport brief (e.g. top stories + short summaries)."""

    __tablename__ = "daily_briefs"
    __table_args__ = (
        UniqueConstraint("brief_date", "sport", name="uq_daily_briefs_brief_date_sport"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    brief_date: Mapped[date] = mapped_column(Date, nullable=False)
    sport: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=text("now()"),
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clusters.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sport: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    cluster: Mapped[Cluster | None] = relationship(back_populates="articles")
