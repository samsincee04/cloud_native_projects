-- Summaries table for persisting POST /summarize results.
CREATE TABLE IF NOT EXISTS summaries (
    id         SERIAL PRIMARY KEY,
    summary    TEXT NOT NULL,
    model      VARCHAR(255) NOT NULL,
    truncated  BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
