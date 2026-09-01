-- TradingView Trending Strategies migration
-- Creates tables for storing scraped TradingView strategies and their backtest results

-- Main table: store trending strategies scraped from TradingView
CREATE TABLE IF NOT EXISTS tradingview_trending_strategies (
    id VARCHAR(36) PRIMARY KEY,
    source_type VARCHAR(20) NOT NULL, -- 'idea' or 'script'
    tradingview_id VARCHAR(100) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    author VARCHAR(200),
    author_url VARCHAR(500),

    -- Engagement metrics (for ranking)
    likes INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,

    -- Content
    content_preview TEXT,
    image_url VARCHAR(500),
    script_id VARCHAR(100),
    url VARCHAR(500) NOT NULL UNIQUE,

    -- Auto-detected markets and symbols (crypto only for now)
    detected_symbols JSONB, -- ["BTCUSDT", "ETHUSDT"]
    detected_markets JSONB, -- ["crypto"]

    -- Scraping metadata
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    trending_rank INTEGER,
    trending_category VARCHAR(50), -- 'top_rated', 'most_liked', 'trending'

    -- Backtest status
    backtest_status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    backtest_results JSONB, -- {BTCUSDT: {metrics: {...}, run_id: "..."}}
    backtest_error TEXT,


    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_trending_status ON tradingview_trending_strategies(backtest_status);
CREATE INDEX IF NOT EXISTS idx_trending_scraped_at ON tradingview_trending_strategies(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_trending_markets ON tradingview_trending_strategies USING GIN(detected_markets);
CREATE INDEX IF NOT EXISTS idx_trending_source_type ON tradingview_trending_strategies(source_type);

-- Add comments for documentation
COMMENT ON TABLE tradingview_trending_strategies IS 'Stores trending strategies scraped from TradingView (scripts and ideas)';
COMMENT ON COLUMN tradingview_trending_strategies.source_type IS 'Type of source: idea or script';
COMMENT ON COLUMN tradingview_trending_strategies.detected_symbols IS 'Auto-detected trading symbols (e.g. BTCUSDT, ETHUSDT)';
COMMENT ON COLUMN tradingview_trending_strategies.detected_markets IS 'Auto-detected markets (e.g. crypto, stocks)';
COMMENT ON COLUMN tradingview_trending_strategies.backtest_results IS 'Backtest results per symbol, JSONB format';
