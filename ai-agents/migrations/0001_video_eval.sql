-- MindSafe Supabase migration: video_eval table
-- Run once against your Supabase project:
--   psql $DATABASE_URL -f migrations/0001_video_eval.sql
-- Or paste into the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS video_eval (
    video_path            TEXT        PRIMARY KEY,
    child_age             NUMERIC(4, 1),
    age_band              TEXT,
    age_band_name         TEXT,
    duration_seconds      NUMERIC(8, 2),
    duration_minutes      NUMERIC(6, 2),
    dev_score             NUMERIC(5, 2)  CHECK (dev_score BETWEEN 0 AND 100),
    dev_interpretation    TEXT,
    brainrot_index        NUMERIC(5, 2)  CHECK (brainrot_index BETWEEN 0 AND 100),
    brainrot_interpretation TEXT,
    overall_recommendation TEXT,
    dimension_scores      JSONB,
    metrics               JSONB,
    strengths             JSONB,
    concerns              JSONB,
    recommendations       JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-update updated_at on upsert
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER video_eval_updated_at
    BEFORE UPDATE ON video_eval
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Index for frequent lookups
CREATE INDEX IF NOT EXISTS idx_video_eval_age_band ON video_eval (age_band);
CREATE INDEX IF NOT EXISTS idx_video_eval_dev_score ON video_eval (dev_score);
CREATE INDEX IF NOT EXISTS idx_video_eval_brainrot  ON video_eval (brainrot_index);
