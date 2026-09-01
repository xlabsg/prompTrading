-- Migration: Add multi-symbol live trading fields
-- Date: 2025-01-19
-- Description: Add multi-symbol/interval config and signal metadata fields.

ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS symbols JSONB;
ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS intervals JSONB;

ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS interval VARCHAR(20);
ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS target DOUBLE PRECISION;
ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS params_snapshot JSONB;
ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS indicators JSONB;
ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS position JSONB;
ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS price_source VARCHAR(50);
