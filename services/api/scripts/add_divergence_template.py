#!/usr/bin/env python3
"""Add Divergence template to the database.

This creates a StrategyTemplate record that points to:
  strategy_templates.templates.divergence:create_live_strategy
"""

import os
import sys
import uuid
from datetime import datetime, timezone

# Add the repo root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from control_plane.db import create_db_engine, create_session_factory  # noqa: E402
from control_plane.enums import StrategyTemplateType  # noqa: E402
from control_plane.models import StrategyTemplate  # noqa: E402
from app.settings import settings  # noqa: E402


def add_divergence_template() -> str:
    engine = create_db_engine(settings.db_url)
    session_factory = create_session_factory(engine)
    db = session_factory()

    try:
        existing = db.query(StrategyTemplate).filter_by(name="divergence").first()
        if existing:
            print(f"Template 'divergence' already exists with ID: {existing.id}")
            return existing.id

        template = StrategyTemplate(
            id=str(uuid.uuid4()),
            name="divergence",
            description="Regular RSI divergence on confirmed pivots (simplified migration from trading_view_script).",
            template_type=StrategyTemplateType.BUILTIN.value,
            author="PromptTrading",
            tags=["divergence", "rsi", "mean_reversion"],
            risk_level="medium",
            trading_frequency="intraday",
            complexity_score=3,
            min_capital_usdt=100.0,
            supported_exchanges=["okx"],
            supported_symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
            prompt=(
                "Regular RSI divergence on confirmed pivots.\n"
                "- Bearish: price higher high, RSI lower high\n"
                "- Bullish: price lower low, RSI higher low\n"
                "Trades only after pivot confirmation."
            ),
            config_snapshot={
                # Live adapter settings (kept small for fast backtests; strategy is incremental).
                "live_bar_interval": "1h",
                "live_history_bars": 1,
                # Adapter/base sizing defaults used by Stable5 screening.
                "default_max_position_pct": 10.0,
                "default_stop_loss_pct": 2.0,
                # Strategy params
                "pivot_period": 10,
                "rsi_period": 14,
                "min_rsi_delta": 0.0,
                "cooldown_bars": 0,
                "position_size_pct": 1.0,
                "stop_loss_pct": 2.0,
                "max_hold_bars": 0,
            },
            code_snapshot={
                "module": "strategy_templates.templates.divergence",
                "entrypoint": "create_live_strategy",
            },
            version=1,
            is_public=True,
            is_featured=False,
            subscriber_count=0,
            backtest_summary={
                "note": "Backtest results pending (Stable5 screening will populate stable5 summary).",
                "status": "pending_backtest",
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        print("✓ Created template: divergence")
        print(f"  ID: {template.id}")
        return template.id
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    template_id = add_divergence_template()
    print(f"\nTemplate ID: {template_id}")
