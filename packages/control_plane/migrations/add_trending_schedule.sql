-- Trending Schedule migration
-- Creates table for storing scheduled scraping configuration

CREATE TABLE IF NOT EXISTS trending_schedules (
    id VARCHAR(36) PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    cron_expression VARCHAR(100) NOT NULL DEFAULT '0 */6 * * *',
    source_types JSONB,
    max_count INTEGER NOT NULL DEFAULT 50,
    auto_backtest BOOLEAN NOT NULL DEFAULT TRUE,
    auto_backtest_top_n INTEGER NOT NULL DEFAULT 15,
    last_run_at TIMESTAMP WITH TIME ZONE,
    next_run_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trending_schedules_enabled ON trending_schedules(enabled);

COMMENT ON TABLE trending_schedules IS 'Stores scheduled configuration for TradingView trending strategy scraping';
