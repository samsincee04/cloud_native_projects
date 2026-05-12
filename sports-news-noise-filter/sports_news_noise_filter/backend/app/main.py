from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import os
from pathlib import Path
import subprocess
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request
from sqlalchemy import desc, func, nulls_last, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.db import create_tables, get_session
from app.models import Article, Cluster, DailyBrief, Preferences, User
from app.utils import cache as feed_clusters_ttl_cache
from app.utils.rate_limit import (
    RateLimitExceeded,
    rate_limit_cluster_detail,
    rate_limit_feed_clusters,
    rate_limit_preferences_put,
    rate_limit_users_post,
)
from app.schemas import (
    ClusterArticleItem,
    ClusterDetailResponse,
    DailyBriefItem,
    DailyBriefResponse,
    FeedClusterItem,
    FeedClustersResponse,
    FeedItem,
    FeedResponse,
    PreferencesUpdateRequest,
    PreferencesUpdateResponse,
    UserCreateResponse,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="Sports News Noise Filter API",
    version="0.1.0",
    lifespan=lifespan,
)

def _normalize_sport_tag(sport: str) -> str:
    return sport.strip().lower()


def _content_json_to_brief_items(raw: object) -> list[DailyBriefItem]:
    if not isinstance(raw, list):
        return []
    items: list[DailyBriefItem] = []
    for x in raw:
        if isinstance(x, dict):
            items.append(
                DailyBriefItem(
                    headline=str(x.get("headline", "") or ""),
                    summary=str(x.get("summary", "") or ""),
                )
            )
    return items


def _daily_brief_to_response(row: DailyBrief) -> DailyBriefResponse:
    return DailyBriefResponse(
        sport=row.sport,
        brief_date=row.brief_date,
        model_name=row.model_name,
        items=_content_json_to_brief_items(row.content_json),
    )


def _placeholder_brief_content_json(session: Session, sport: str) -> list[dict[str, str]]:
    sport_norm = _normalize_sport_tag(sport)
    stmt = (
        select(
            Cluster.headline,
            func.count(Article.id).label("source_count"),
            func.max(Article.published_at).label("latest_published_at"),
        )
        .join(Article, Article.cluster_id == Cluster.id)
        .where(~Article.url.contains("bbc.co.uk/sounds/"))
        .where(~Article.url.contains("bbc.co.uk/iplayer/"))
        .where(Cluster.sport == sport_norm)
        .group_by(Cluster.id, Cluster.headline)
        .order_by(
            desc(func.count(Article.id)),
            nulls_last(desc(func.max(Article.published_at))),
        )
        .limit(5)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "headline": (row.headline or "").strip() or "Untitled",
            "summary": "",
        }
        for row in rows
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "rate_limited",
            "retry_after_seconds": exc.retry_after_seconds,
        },
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/users", response_model=UserCreateResponse)
def create_user(
    _rate_limit: None = Depends(rate_limit_users_post),
    session: Session = Depends(get_session),
) -> UserCreateResponse:
    user = User()
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserCreateResponse.model_validate(user)


@app.put(
    "/users/{user_id}/preferences",
    response_model=PreferencesUpdateResponse,
)
def update_preferences(
    user_id: UUID,
    body: PreferencesUpdateRequest,
    _rate_limit: None = Depends(rate_limit_preferences_put),
    session: Session = Depends(get_session),
) -> PreferencesUpdateResponse:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    topics = list(body.topics)
    sports = list(body.sports)
    prefs = session.get(Preferences, user_id)
    if prefs is None:
        prefs = Preferences(user_id=user_id, topics=topics, sports=sports)
        session.add(prefs)
    else:
        prefs.topics = topics
        prefs.sports = sports

    session.commit()
    session.refresh(prefs)
    return PreferencesUpdateResponse(
        user_id=user_id,
        topics=list(prefs.topics),
        sports=list(prefs.sports),
    )


@app.get("/feed", response_model=FeedResponse)
def get_feed(
    user_id: UUID = Query(..., description="User receiving the feed"),
    session: Session = Depends(get_session),
) -> FeedResponse:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    stmt = (
        select(Article)
        .where(~Article.url.contains("bbc.co.uk/sounds/"))
        .where(~Article.url.contains("bbc.co.uk/iplayer/"))
        .order_by(Article.created_at.desc())
    )
    articles = session.scalars(stmt).all()
    items = [FeedItem.model_validate(a) for a in articles]
    return FeedResponse(user_id=user_id, items=items)


@app.get("/feed_clusters", response_model=FeedClustersResponse)
def get_feed_clusters(
    user_id: UUID = Query(..., description="User receiving the feed"),
    refresh: str | None = Query(
        None, description="Set to 1 (or true) to bypass cache"
    ),
    _rate_limit: None = Depends(rate_limit_feed_clusters),
    session: Session = Depends(get_session),
) -> FeedClustersResponse:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    cache_key = str(user_id)
    bypass_cache = refresh is not None and str(refresh).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    if not bypass_cache:
        cached, age_s = feed_clusters_ttl_cache.feed_clusters_cache_get(cache_key)
        if cached is not None:
            print(
                f"feed_clusters_cache_hit key={cache_key} age_s={age_s:.2f}",
                flush=True,
            )
            return FeedClustersResponse.model_validate(cached)

    print(f"feed_clusters_cache_miss key={cache_key}", flush=True)

    prefs = session.get(Preferences, user_id)
    sports_filter: list[str] = []
    topics_filter: list[str] = []
    if prefs is not None:
        if prefs.sports:
            sports_filter = sorted(
                {
                    s.strip().lower()
                    for s in prefs.sports
                    if isinstance(s, str) and s.strip()
                }
            )
        if prefs.topics:
            topics_filter = sorted(
                {
                    t.strip().lower()
                    for t in prefs.topics
                    if isinstance(t, str) and t.strip()
                }
            )

    stmt = (
        select(
            Cluster.id,
            Cluster.headline,
            Cluster.created_at,
            Cluster.sport,
            Cluster.topic,
            func.count(Article.id).label("source_count"),
            func.max(Article.published_at).label("latest_published_at"),
        )
        .join(Article, Article.cluster_id == Cluster.id)
        .where(~Article.url.contains("bbc.co.uk/sounds/"))
        .where(~Article.url.contains("bbc.co.uk/iplayer/"))
    )
    if sports_filter:
        stmt = stmt.where(Cluster.sport.in_(sports_filter))
    if topics_filter:
        stmt = stmt.where(Cluster.topic.in_(topics_filter))
    # Rank: most sources first, then newest update (unknown dates last).
    stmt = (
        stmt.group_by(
            Cluster.id,
            Cluster.headline,
            Cluster.created_at,
            Cluster.sport,
            Cluster.topic,
        )
        .order_by(
            desc(func.count(Article.id)),  # source_count DESC
            nulls_last(desc(func.max(Article.published_at))),  # latest_published_at DESC
        )
    )
    rows = session.execute(stmt).all()
    items = [
        FeedClusterItem(
            cluster_id=row.id,
            headline=row.headline,
            source_count=int(row.source_count),
            latest_published_at=row.latest_published_at,
            sport=row.sport,
            topic=row.topic,
        )
        for row in rows
    ]
    response = FeedClustersResponse(user_id=user_id, items=items)
    feed_clusters_ttl_cache.feed_clusters_cache_set(
        cache_key, response.model_dump(mode="json")
    )
    return response


@app.get("/clusters/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster(
    cluster_id: UUID,
    _rate_limit: None = Depends(rate_limit_cluster_detail),
    session: Session = Depends(get_session),
) -> ClusterDetailResponse:
    stmt = (
        select(Cluster)
        .where(Cluster.id == cluster_id)
        .options(selectinload(Cluster.articles))
    )
    cluster = session.scalars(stmt).first()
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found")

    articles = [
        ClusterArticleItem.model_validate(a) for a in cluster.articles
    ]
    return ClusterDetailResponse(
        id=cluster.id,
        headline=cluster.headline,
        created_at=cluster.created_at,
        articles=articles,
        summary=cluster.summary,
        what_changed=cluster.what_changed,
        facts_json=cluster.facts_json,
        entities_json=cluster.entities_json,
        llm_model_name=cluster.llm_model_name,
        llm_updated_at=cluster.llm_updated_at,
    )


@app.get("/daily_brief", response_model=None)
def get_daily_brief(
    sport: str = Query(..., description="Sport tag, e.g. soccer, nba"),
    brief_day: date | None = Query(
        None,
        alias="date",
        description="Brief date (UTC). Defaults to today UTC.",
    ),
    session: Session = Depends(get_session),
) -> DailyBriefResponse | JSONResponse:
    sport_norm = _normalize_sport_tag(sport)
    day = brief_day or datetime.now(timezone.utc).date()
    row = session.scalars(
        select(DailyBrief).where(
            DailyBrief.sport == sport_norm,
            DailyBrief.brief_date == day,
        )
    ).first()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "brief_not_found",
                "sport": sport_norm,
                "brief_date": day.isoformat(),
            },
        )
    return _daily_brief_to_response(row)


@app.post("/daily_brief/generate", response_model=DailyBriefResponse)
def generate_daily_brief_placeholder(
    sport: str = Query(..., description="Sport tag, e.g. soccer, nba"),
    session: Session = Depends(get_session),
) -> DailyBriefResponse:
    sport_norm = _normalize_sport_tag(sport)
    day = datetime.now(timezone.utc).date()
    content = _placeholder_brief_content_json(session, sport_norm)
    for item in content:
        if not item.get("summary"):
            item["summary"] = "TBD"

    insert_stmt = pg_insert(DailyBrief).values(
        id=uuid4(),
        brief_date=day,
        sport=sport_norm,
        model_name="placeholder",
        content_json=content,
    )
    upsert = insert_stmt.on_conflict_do_update(
        index_elements=[DailyBrief.brief_date, DailyBrief.sport],
        set_={
            "model_name": insert_stmt.excluded.model_name,
            "content_json": insert_stmt.excluded.content_json,
            "created_at": func.now(),
        },
    )
    session.execute(upsert)
    session.commit()

    row = session.scalars(
        select(DailyBrief).where(
            DailyBrief.sport == sport_norm,
            DailyBrief.brief_date == day,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=500, detail="brief upsert failed")
    return _daily_brief_to_response(row)


@app.post("/admin/run_once")
def admin_run_once() -> dict[str, int | bool]:
    if os.getenv("RUN_WORKER_ENABLED", "").strip().lower() != "true":
        raise HTTPException(status_code=403, detail="run_once_disabled")

    repo_root = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["python3", "worker/run_once.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return {"ok": completed.returncode == 0, "exit_code": completed.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": 124}
