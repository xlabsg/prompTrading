-- Add strategy template classification fields for SaaS marketplace
-- Migration: 20260124_add_strategy_template_classifications.sql

-- Add new columns to strategy_templates table
ALTER TABLE strategy_templates
ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20),
ADD COLUMN IF NOT EXISTS trading_frequency VARCHAR(30),
ADD COLUMN IF NOT EXISTS complexity_score INTEGER,
ADD COLUMN IF NOT EXISTS min_capital_usdt NUMERIC(10, 2) DEFAULT 100.0,
ADD COLUMN IF NOT EXISTS supported_exchanges JSONB,
ADD COLUMN IF NOT EXISTS supported_symbols JSONB,
ADD COLUMN IF NOT EXISTS backtest_summary JSONB;

-- Add comments for documentation
COMMENT ON COLUMN strategy_templates.risk_level IS 'Risk level: low, medium, high';
COMMENT ON COLUMN strategy_templates.trading_frequency IS 'Trading frequency: low_frequency, intraday, high_frequency';
COMMENT ON COLUMN strategy_templates.complexity_score IS 'Complexity score from 1 (simple) to 5 (very complex)';
COMMENT ON COLUMN strategy_templates.min_capital_usdt IS 'Minimum recommended capital in USDT';
COMMENT ON COLUMN strategy_templates.supported_exchanges IS 'List of supported exchanges (e.g., ["okx", "binance"])';
COMMENT ON COLUMN strategy_templates.supported_symbols IS 'List of supported symbols (empty means all)';
COMMENT ON COLUMN strategy_templates.backtest_summary IS 'Aggregated backtest performance metrics';

-- Create index on risk_level and trading_frequency for filtering
CREATE INDEX IF NOT EXISTS idx_strategy_templates_risk_level ON strategy_templates(risk_level);
CREATE INDEX IF NOT EXISTS idx_strategy_templates_trading_frequency ON strategy_templates(trading_frequency);
CREATE INDEX IF NOT EXISTS idx_strategy_templates_complexity_score ON strategy_templates(complexity_score);

-- Update existing templates with default values
UPDATE strategy_templates
SET
    risk_level = 'medium',
    trading_frequency = 'intraday',
    complexity_score = 3,
    min_capital_usdt = 100.0,
    supported_exchanges = '["okx"]',
    supported_symbols = '[]'
WHERE risk_level IS NULL;
