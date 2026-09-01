-- Add result_summary to backtest_runs for lightweight DB-stored results
-- Migration: 20260128_add_backtest_run_result_summary.sql

ALTER TABLE backtest_runs
ADD COLUMN IF NOT EXISTS result_summary JSONB;

COMMENT ON COLUMN backtest_runs.result_summary IS 'Lightweight backtest summary for list/query';
