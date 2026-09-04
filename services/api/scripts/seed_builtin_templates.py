#!/usr/bin/env python3
"""
初始化内置策略模板

使用 SQLAlchemy ORM 幂等写入内置模板，兼容 SQLite 和 PostgreSQL
"""

import os
import sys

# 添加项目路径
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_script_dir, '..')))
sys.path.insert(0, os.path.abspath(os.path.join(_script_dir, '../../../packages/control_plane')))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Base, StrategyTemplate
from app.settings import settings


BUILTIN_TEMPLATES = [
    {
        "id": "tmpl-divergence",
        "name": "divergence",
        "description": "Regular divergence with multi-indicator confirmation and S/R risk filter.",
        "template_type": "builtin",
        "prompt": (
            "Regular divergence on confirmed pivots using MACD, histogram, and stochastic.\n"
            "Optional VW-MACD, OBV, RSI, MFI, CCI confirmations.\n"
            "Dynamic TP/SL based on support/resistance with minimum R:R filtering."
        ),
        "config_snapshot": {
            "live_bar_interval": "1h",
            "live_history_bars": 200,
            "default_max_position_pct": 10.0,
            "default_stop_loss_pct": 1.0,
            "pivot_period": 10,
            "pivot_confirm_bars": 1,
            "min_confirmations": 3,
            "min_risk_reward": 1.0,
            "use_dynamic_tpsl": True,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "cooldown_bars": 0,
            "position_size_pct": 1.0,
            "min_rsi_delta": 0.0,
            "indicators": {
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "stochastic_k": 14,
                "stochastic_d": 3,
                "stochastic_smooth": 3,
                "vw_macd_fast": 12,
                "vw_macd_slow": 26,
                "vw_macd_signal": 9,
                "vw_macd_enabled": True,
                "obv_enabled": True,
                "rsi_enabled": False,
                "rsi_period": 14,
                "mfi_enabled": False,
                "mfi_period": 14,
                "cci_enabled": False,
                "cci_period": 20,
                "stochastic_zone_filter": {
                    "enabled": False,
                    "overbought": 70.0,
                    "oversold": 30.0,
                },
            },
        },
        "author": "Stratsmith",
        "tags": ["divergence", "rsi", "macd", "mean_reversion"],
        "risk_level": "medium",
        "trading_frequency": "intraday",
        "complexity_score": 4,
        "min_capital_usdt": 100.0,
        "supported_exchanges": ["okx"],
        "supported_symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        "is_public": True,
        "is_featured": False,
        "subscriber_count": 0,
    },
]


def seed_templates():
    """执行内置策略模板初始化"""
    print("📝 开始初始化内置模板...")

    engine = create_db_engine(settings.db_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    try:
        with session_scope(session_factory) as db:
            for tmpl_data in BUILTIN_TEMPLATES:
                existing = db.query(StrategyTemplate).filter_by(id=tmpl_data["id"]).first()
                if not existing:
                    tmpl = StrategyTemplate(**tmpl_data)
                    db.add(tmpl)
                else:
                    for key, val in tmpl_data.items():
                        setattr(existing, key, val)

            db.commit()

            template_count = db.query(StrategyTemplate).count()
            featured_count = db.query(StrategyTemplate).filter(
                StrategyTemplate.is_featured == True
            ).count()

            print("\n✅ 模板初始化完成！")
            print(f"   - 总模板数: {template_count}")
            print(f"   - 精选模板: {featured_count}")

            templates = db.query(StrategyTemplate).order_by(
                StrategyTemplate.updated_at.desc()
            ).all()

            print("\n📊 已初始化的模板:")
            for tmpl in templates:
                featured = "⭐ " if tmpl.is_featured else "   "
                risk = tmpl.risk_level or "unknown"
                freq = tmpl.trading_frequency or "unknown"
                print(f"   {featured}- {tmpl.name}")
                print(f"      类型: {tmpl.template_type}, 风险: {risk}, 频率: {freq}")

            return True

    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = seed_templates()
    sys.exit(0 if success else 1)

