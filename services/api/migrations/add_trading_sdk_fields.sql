-- Migration: Add Trading SDK fields
-- Date: 2025-01-19
-- Description: Add fields for Trading SDK integration (risk control, trailing stop, dynamic TP/SL)

-- ==========================================
-- TradingConfig table updates
-- ==========================================

ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS leverage INTEGER DEFAULT 1;
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS max_leverage INTEGER DEFAULT 10;
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS max_daily_loss_pct DECIMAL(10, 4);
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS max_drawdown_pct DECIMAL(10, 4);
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS require_stop_loss BOOLEAN DEFAULT true;

-- Trailing stop configuration
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS trailing_stop_enabled BOOLEAN DEFAULT false;
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS trailing_activation_pct DECIMAL(10, 6) DEFAULT 0.005;  -- 0.5%
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS trailing_distance_pct DECIMAL(10, 6) DEFAULT 0.008;    -- 0.8%

-- Dynamic TP/SL configuration
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS dynamic_tpsl_enabled BOOLEAN DEFAULT false;
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS use_support_resistance BOOLEAN DEFAULT true;
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS min_risk_reward DECIMAL(10, 4) DEFAULT 1.0;
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS fallback_sl_pct DECIMAL(10, 6) DEFAULT 0.01;  -- 1%
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS fallback_tp_pct DECIMAL(10, 6) DEFAULT 0.02;  -- 2%

-- ==========================================
-- Position table updates
-- ==========================================

ALTER TABLE positions ADD COLUMN IF NOT EXISTS leverage INTEGER DEFAULT 1;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS margin DECIMAL(20, 8) DEFAULT 0.0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS liquidation_price DECIMAL(20, 8);

-- TP/SL information
ALTER TABLE positions ADD COLUMN IF NOT EXISTS take_profit DECIMAL(20, 8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS stop_loss DECIMAL(20, 8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS stop_loss_type VARCHAR(20);  -- "fixed", "trailing", "dynamic"

-- Trailing stop state
ALTER TABLE positions ADD COLUMN IF NOT EXISTS trailing_stop_activated BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(20, 8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS highest_price DECIMAL(20, 8);  -- For long positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS lowest_price DECIMAL(20, 8);   -- For short positions

-- ==========================================
-- Order table updates
-- ==========================================

-- Make client_order_id unique for tracking (use DO block for IF NOT EXISTS compatibility)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'orders_client_order_id_unique'
    ) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_client_order_id_unique UNIQUE (client_order_id);
    END IF;
END $$;

-- Add index on client_order_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_orders_client_order_id ON orders(client_order_id);

-- Add TP/SL information to orders
ALTER TABLE orders ADD COLUMN IF NOT EXISTS take_profit DECIMAL(20, 8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS stop_loss DECIMAL(20, 8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS reduce_only BOOLEAN DEFAULT false;

-- Add fee information
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fee DECIMAL(20, 8) DEFAULT 0.0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fee_currency VARCHAR(10) DEFAULT 'USDT';

-- ==========================================
-- New table: TradingSessionStats (optional)
-- ==========================================

CREATE TABLE IF NOT EXISTS trading_session_stats (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES trading_sessions(id) ON DELETE CASCADE,

    -- Risk metrics
    peak_equity DECIMAL(20, 8),
    current_drawdown_pct DECIMAL(10, 4) DEFAULT 0.0,
    max_drawdown_pct DECIMAL(10, 4) DEFAULT 0.0,
    max_drawdown_date TIMESTAMP WITH TIME ZONE,

    -- Daily stats
    daily_start_equity DECIMAL(20, 8),
    daily_pnl DECIMAL(20, 8) DEFAULT 0.0,
    daily_pnl_pct DECIMAL(10, 4) DEFAULT 0.0,
    trading_date DATE,

    -- Trading metrics
    total_wins INTEGER DEFAULT 0,
    total_losses INTEGER DEFAULT 0,
    win_rate DECIMAL(10, 4) DEFAULT 0.0,
    profit_factor DECIMAL(10, 4) DEFAULT 0.0,
    avg_win DECIMAL(20, 8) DEFAULT 0.0,
    avg_loss DECIMAL(20, 8) DEFAULT 0.0,
    largest_win DECIMAL(20, 8) DEFAULT 0.0,
    largest_loss DECIMAL(20, 8) DEFAULT 0.0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT trading_session_stats_session_id_unique UNIQUE (session_id)
);

CREATE INDEX IF NOT EXISTS idx_trading_session_stats_session_id ON trading_session_stats(session_id);

-- ==========================================
-- Comments for documentation
-- ==========================================

COMMENT ON COLUMN trading_configs.leverage IS 'Leverage multiplier for trading (1-125x)';
COMMENT ON COLUMN trading_configs.max_leverage IS 'Maximum allowed leverage';
COMMENT ON COLUMN trading_configs.max_daily_loss_pct IS 'Maximum daily loss percentage (e.g., 5.0 = 5%)';
COMMENT ON COLUMN trading_configs.max_drawdown_pct IS 'Maximum drawdown percentage (e.g., 10.0 = 10%)';
COMMENT ON COLUMN trading_configs.require_stop_loss IS 'Whether stop loss is mandatory for all orders';

COMMENT ON COLUMN trading_configs.trailing_stop_enabled IS 'Enable trailing stop loss';
COMMENT ON COLUMN trading_configs.trailing_activation_pct IS 'Profit percentage to activate trailing stop (e.g., 0.005 = 0.5%)';
COMMENT ON COLUMN trading_configs.trailing_distance_pct IS 'Trailing stop distance as percentage (e.g., 0.008 = 0.8%)';

COMMENT ON COLUMN trading_configs.dynamic_tpsl_enabled IS 'Enable dynamic TP/SL calculation based on support/resistance';
COMMENT ON COLUMN trading_configs.use_support_resistance IS 'Use support/resistance for TP/SL calculation';
COMMENT ON COLUMN trading_configs.min_risk_reward IS 'Minimum risk/reward ratio required (e.g., 1.5)';

COMMENT ON COLUMN positions.take_profit IS 'Take profit price';
COMMENT ON COLUMN positions.stop_loss IS 'Stop loss price';
COMMENT ON COLUMN positions.stop_loss_type IS 'Type of stop loss: fixed, trailing, dynamic';
COMMENT ON COLUMN positions.trailing_stop_activated IS 'Whether trailing stop has been activated';
COMMENT ON COLUMN positions.trailing_stop_price IS 'Current trailing stop price';

COMMENT ON COLUMN orders.client_order_id IS 'Client-side order ID (Snowflake-based unique ID)';
COMMENT ON COLUMN orders.take_profit IS 'Take profit price for this order';
COMMENT ON COLUMN orders.stop_loss IS 'Stop loss price for this order';
COMMENT ON COLUMN orders.reduce_only IS 'Whether this order only reduces position';

-- ==========================================
-- End of migration
-- ==========================================
