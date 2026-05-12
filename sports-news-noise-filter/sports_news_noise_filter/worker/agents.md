# Worker — agents.md (v1)

## Objective (Day 3)
Implement a run-once ingestion script that:
- reads 3–5 RSS feeds from docs/rss_sources.md
- inserts articles into Postgres (unique by URL)
- clusters by normalized title hash
- creates/updates placeholder cluster summary
- links articles to clusters

## Constraints
- No embeddings/pgvector.
- No LLM calls.
- Deterministic rules only.
- Must be runnable: python worker/run_once.py

## Allowed files (Day 3)
- worker/run_once.py
- worker/agents.md