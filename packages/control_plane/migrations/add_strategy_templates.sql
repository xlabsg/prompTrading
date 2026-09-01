-- Strategy Templates and Subscriptions Migration
-- Creates tables for template-based copy trading functionality

-- Strategy Template: A static strategy configuration that can be copied/subscribed
-- Templates don't have trading sessions or exchange accounts - they are pure configurations
CREATE TABLE IF NOT EXISTS strategy_templates (
    id VARCHAR(36) PRIMARY KEY,

    -- Template identity
    name VARCHAR(200) NOT NULL,
    description TEXT,
    template_type VARCHAR(50) NOT NULL, -- 'builtin', 'tradingview', 'community'

    -- Source reference (for TradingView imports)
    source_id VARCHAR(36), -- FK to tradingview_trending_strategies

    -- Template content (the actual strategy code/prompt)
    prompt TEXT,
    config_snapshot JSONB, -- Trading config template
    code_snapshot JSONB, -- Version snapshot

    -- Metadata
    version INTEGER DEFAULT 1,
    author VARCHAR(200),
    tags JSONB, -- ["momentum", "crypto", "scalping"]

    -- Visibility and sharing
    is_public BOOLEAN DEFAULT TRUE,
    is_featured BOOLEAN DEFAULT FALSE,

    -- Subscription stats
    subscriber_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_synced_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for templates
CREATE INDEX IF NOT EXISTS idx_template_type ON strategy_templates(template_type);
CREATE INDEX IF NOT EXISTS idx_template_public ON strategy_templates(is_public);
CREATE INDEX IF NOT EXISTS idx_template_featured ON strategy_templates(is_featured);
CREATE INDEX IF NOT EXISTS idx_template_subscribers ON strategy_templates(subscriber_count DESC);
CREATE INDEX IF NOT EXISTS idx_template_tags ON strategy_templates USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_template_source ON strategy_templates(source_id);

COMMENT ON TABLE strategy_templates IS 'Strategy templates - static configurations that users can subscribe/copy';
COMMENT ON COLUMN strategy_templates.template_type IS 'Type: builtin (platform), tradingview (imported), community (shared)';
COMMENT ON COLUMN strategy_templates.config_snapshot IS 'Template trading configuration (symbols, intervals, etc)';
COMMENT ON COLUMN strategy_templates.code_snapshot IS 'Snapshot of the strategy code/version';

-- Strategy Subscription: Links a user's strategy copy to the source template
CREATE TABLE IF NOT EXISTS strategy_subscriptions (
    id VARCHAR(36) PRIMARY KEY,

    -- Links
    template_id VARCHAR(36) NOT NULL REFERENCES strategy_templates(id) ON DELETE CASCADE,
    strategy_id VARCHAR(36) NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Subscription status
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'paused', 'sync_error', 'outdated'

    -- Sync tracking
    subscribed_version INTEGER DEFAULT 1,
    last_synced_at TIMESTAMP WITH TIME ZONE,
    sync_error TEXT,

    -- User configuration (trading params, overrides)
    user_config JSONB,
    -- Example:
    -- {
    --   "exchange": "okx",
    --   "symbol": "BTCUSDT",
    --   "max_position_pct": 20.0,
    --   "stop_loss_pct": 5.0,
    --   "custom_params": {...}
    -- }

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for subscriptions
CREATE INDEX IF NOT EXISTS idx_subscription_template ON strategy_subscriptions(template_id);
CREATE INDEX IF NOT EXISTS idx_subscription_strategy ON strategy_subscriptions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_subscription_user ON strategy_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscription_status ON strategy_subscriptions(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_unique ON strategy_subscriptions(template_id, strategy_id);

COMMENT ON TABLE strategy_subscriptions IS 'Links user strategy copies to source templates for sync purposes';
COMMENT ON COLUMN strategy_subscriptions.user_config IS 'User-specific trading configuration overrides';
COMMENT ON COLUMN strategy_subscriptions.subscribed_version IS 'Template version this subscription is synced to';
