# Backend — agents.md (v0)

## Objective (Day 1)
Create a minimal FastAPI backend skeleton that runs locally and exposes:
- GET /health -> {"status": "healthy"}

## Hard Constraints
- Use FastAPI.
- Keep it minimal: only /health today.
- Do not add /feed, /clusters, DB code, RSS code, or LLM code yet.
- Keep code readable and easy to test.

## Allowed Files (Day 1)
- backend/pyproject.toml
- backend/app/__init__.py
- backend/app/main.py

## Day 2 Scope
- Add SQL database layer (Postgres) and create tables:
  users, preferences, articles, clusters.
- Implement endpoints:
  POST /users
  PUT /users/{user_id}/preferences
  GET /feed?user_id=...
  GET /clusters/{cluster_id}
- Keep models minimal. Feed may be empty before ingestion.

## Constraints
- Schemas first, then logic.
- No worker ingestion in backend.
- No embeddings/LLM.