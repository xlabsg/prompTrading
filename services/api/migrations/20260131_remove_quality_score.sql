-- Remove quality_score / min_quality_score fields (deprecated)

DROP INDEX IF EXISTS idx_template_quality;
DROP INDEX IF EXISTS idx_trending_quality;

ALTER TABLE strategy_templates
    DROP COLUMN IF EXISTS quality_score;

ALTER TABLE tradingview_trending_strategies
    DROP COLUMN IF EXISTS quality_score;

ALTER TABLE trending_schedules
    DROP COLUMN IF EXISTS min_quality_score;

ALTER TABLE template_performance_schedule
    DROP COLUMN IF EXISTS min_quality_score;
