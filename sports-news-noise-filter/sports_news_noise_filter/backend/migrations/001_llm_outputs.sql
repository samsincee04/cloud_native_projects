-- Day 21 Part 1: LLM outputs on clusters + daily_briefs table.
-- Idempotent; safe to re-run. Mirrors ensure_llm_output_schema() in app/db.py.

ALTER TABLE clusters ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS what_changed TEXT;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS facts_json JSONB;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS entities_json JSONB;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS llm_model_name TEXT;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS llm_updated_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS daily_briefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_date DATE NOT NULL,
    sport TEXT NOT NULL,
    model_name TEXT NOT NULL,
    content_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_daily_briefs_brief_date_sport UNIQUE (brief_date, sport)
);
