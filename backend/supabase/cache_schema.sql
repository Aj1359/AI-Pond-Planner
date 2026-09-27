-- Run this in your Supabase SQL Editor
-- Creates the analysis_cache table used by backend/app/cache.py

CREATE TABLE IF NOT EXISTS analysis_cache (
    cache_key   TEXT PRIMARY KEY,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    hit_count   INTEGER DEFAULT 0
);

-- Auto-delete entries older than 24 hours (optional, via pg_cron or manual)
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- SELECT cron.schedule('0 2 * * *', $$DELETE FROM analysis_cache WHERE created_at < NOW() - INTERVAL '24 hours'$$);

-- Index on creation time for cleanup queries
CREATE INDEX IF NOT EXISTS idx_cache_created ON analysis_cache(created_at);
