-- Drop the tmpl-flow-right builtin template.
--
-- flow_right needs tick-level trade flow. This platform's data layer is an
-- OHLCV parquet cache and its backtester is vectorized over bars, so the
-- template could not do what its name and its 35-parameter config promised:
-- the code that actually ran read 2 of those 35 parameters and estimated
-- order-flow imbalance from candle body over range.
--
-- 20260129_keep_only_divergence_flow_right.sql seeded it; this removes it.
-- seed_builtin_templates.py is upsert-only and never deletes, so existing
-- databases need this migration.
--
-- The child tables declare ON DELETE CASCADE, but they are deleted explicitly
-- so this also works where the constraint was never created.

BEGIN;

DELETE FROM template_signals WHERE template_id = 'tmpl-flow-right';
DELETE FROM template_performance_runs WHERE template_id = 'tmpl-flow-right';
DELETE FROM strategy_subscriptions WHERE template_id = 'tmpl-flow-right';
DELETE FROM strategy_templates WHERE id = 'tmpl-flow-right';

COMMIT;
