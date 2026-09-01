-- Add builtin divergence template (migrated from trading_view_script).
-- Safe to run multiple times.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM strategy_templates WHERE id = 'tmpl-divergence') THEN
    INSERT INTO strategy_templates (
      id,
      name,
      description,
      template_type,
      prompt,
      config_snapshot,
      code_snapshot,
      version,
      author,
      tags,
      risk_level,
      trading_frequency,
      complexity_score,
      min_capital_usdt,
      supported_exchanges,
      supported_symbols,
      backtest_summary,
      is_public,
      is_featured,
      subscriber_count,
      created_at,
      updated_at
    ) VALUES (
      'tmpl-divergence',
      'divergence',
      'Regular RSI divergence on confirmed pivots (simplified migration from trading_view_script).',
      'builtin',
      'Regular RSI divergence on confirmed pivots.\n- Bearish: price higher high, RSI lower high\n- Bullish: price lower low, RSI higher low\nTrades only after pivot confirmation.',
      '{
        "live_bar_interval": "1h",
        "live_history_bars": 1,
        "default_max_position_pct": 10.0,
        "default_stop_loss_pct": 2.0,
        "pivot_period": 10,
        "rsi_period": 14,
        "min_rsi_delta": 0.0,
        "cooldown_bars": 0,
        "position_size_pct": 1.0,
        "stop_loss_pct": 2.0,
        "max_hold_bars": 0
      }'::jsonb,
      '{
        "module": "strategy_templates.templates.divergence",
        "entrypoint": "create_live_strategy"
      }'::jsonb,
      1,
      'Stratsmith',
      '["divergence", "rsi", "mean_reversion"]'::jsonb,
      'medium',
      'intraday',
      3,
      100.0,
      '["okx"]'::jsonb,
      '["BTC-USDT-SWAP", "ETH-USDT-SWAP"]'::jsonb,
      '{"note": "Backtest results pending (Stable5 screening will populate stable5 summary).", "status": "pending_backtest"}'::jsonb,
      true,
      false,
      0,
      NOW(),
      NOW()
    );
  END IF;
END $$;
