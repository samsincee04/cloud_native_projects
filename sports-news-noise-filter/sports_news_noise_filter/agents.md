# Sports News Noise Filter — agents.md (Top-Level v0)

## Objective (v0)
Build a local, container-friendly web system that:
- ingests sports news (RSS),
- clusters duplicate stories,
- stores results in Postgres,
- serves a personalized feed via a backend API.

## Phase 1 (Day 1) Scope
- Create repo structure + docs.
- Create backend skeleton with /health only.
- Establish venv + dependency setup.
- No ingestion, no clustering, no LLM calls yet.

## Hard Constraints
- Follow “schemas first, then logic” in later steps.
- Make changes incrementally and verify after each step.
- Do not add features not requested.
- No cloud deployment required; local-first is fine.

## Secrets
- Any API keys go in .env files (never committed).
- Do not place secrets in code or frontend.

## Allowed Files (Day 1)
- agents.md
- docs/*
- backend/*
- worker/agents.md
- frontend/agents.md
- infra/README.md

## Disallowed (Day 1)
- No database setup yet
- No RSS ingestion yet
- No embeddings/LLM yet
- No UI implementation yet

## Verification (Day 1)
- Folder structure exists.
- docs/rss_sources.md has 5–10 feeds.
- Python venv created and dependencies install cleanly.
- Backend starts and GET /health returns 200.

## Day 2 Scope (Backend + DB)
- Add Postgres via Docker Compose (infra/docker-compose.yml).
- Add backend DB schema and CRUD endpoints: /users, /preferences, /feed, /clusters/{id}.
- No RSS ingestion yet (worker is Day 3).
- No embeddings/LLM, no credibility scoring, no advanced ranking.

## Day 2 Allowed Files
- infra/docker-compose.yml
- backend/**
- docs/** (only if needed for notes)