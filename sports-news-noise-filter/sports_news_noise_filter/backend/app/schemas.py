"""Pydantic API schemas (contract types; no route handlers here)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- POST /users ---


class UserCreateResponse(BaseModel):
    """Response body for ``POST /users``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


# --- PUT /users/{user_id}/preferences ---


class PreferencesUpdateRequest(BaseModel):
    """Request body for ``PUT /users/{user_id}/preferences``."""

    topics: list[str] = Field(default_factory=list)
    sports: list[str] = Field(default_factory=list)


class PreferencesUpdateResponse(BaseModel):
    """Response body for ``PUT /users/{user_id}/preferences``."""

    user_id: UUID
    topics: list[str]
    sports: list[str]


# --- GET /feed ---


class FeedItem(BaseModel):
    """One article row in a personalized feed."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    url: str
    cluster_id: UUID | None = None
    published_at: datetime | None = None


class FeedResponse(BaseModel):
    """Response body for ``GET /feed``."""

    user_id: UUID
    items: list[FeedItem]


# --- GET /feed_clusters ---


class FeedClusterItem(BaseModel):
    """One cluster row in a feed (aggregated, not per-article)."""

    cluster_id: UUID
    headline: str | None
    source_count: int
    latest_published_at: datetime | None
    sport: str | None = None
    topic: str | None = None


class FeedClustersResponse(BaseModel):
    """Response body for ``GET /feed_clusters``."""

    user_id: UUID
    items: list[FeedClusterItem]


# --- GET /clusters/{cluster_id} ---


class ClusterArticleItem(BaseModel):
    """Article summary returned with a cluster."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    url: str


class ClusterDetailResponse(BaseModel):
    """Response body for ``GET /clusters/{cluster_id}``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    headline: str | None
    created_at: datetime
    articles: list[ClusterArticleItem]
    # Optional LLM fields (omitted in JSON when null if using response_model_exclude_none — not enabled; clients ignore unknown keys)
    summary: str | None = None
    what_changed: str | None = None
    facts_json: Any | None = None
    entities_json: Any | None = None
    llm_model_name: str | None = None
    llm_updated_at: datetime | None = None


# --- GET /daily_brief ---


class DailyBriefItem(BaseModel):
    """One row inside ``daily_briefs.content_json``."""

    headline: str
    summary: str


class DailyBriefResponse(BaseModel):
    """Response body for ``GET /daily_brief`` and ``POST /daily_brief/generate``."""

    sport: str
    brief_date: date
    model_name: str
    items: list[DailyBriefItem]
