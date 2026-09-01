#!/usr/bin/env python3
"""
配置 Trending 定时抓取任务

创建或更新 TrendingSchedule 配置
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import TrendingSchedule
from app.settings import settings


def setup_trending_schedule():
    """创建或更新 Trending 定时任务配置"""

    print("📅 配置 Trending 定时抓取任务...")

    engine = create_db_engine(settings.db_url)

    try:
        with session_scope(create_session_factory(engine)) as db:
            schedule = db.query(TrendingSchedule).first()

            if not schedule:
                schedule = TrendingSchedule()
                db.add(schedule)

            # 默认配置
            schedule.enabled = True
            schedule.cron_expression = "0 */6 * * *"  # 每 6 小时
            schedule.source_types = ["script"]  # 只抓取脚本类型
            schedule.max_count = 50
            schedule.auto_backtest = True
            schedule.auto_backtest_top_n = 15  # 回测前 15 个
            schedule.last_run_at = None

            db.flush()

            print(f"✅ Trending 定时任务配置完成:")
            print(f"   - 启用: {schedule.enabled}")
            print(f"   - Cron: {schedule.cron_expression} (每 6 小时)")
            print(f"   - 抓取类型: {schedule.source_types}")
            print(f"   - 最大数量: {schedule.max_count}")
            print(f"   - 自动回测: {schedule.auto_backtest}")
            print(f"   - 回测数量: {schedule.auto_backtest_top_n}")

            return True

    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = setup_trending_schedule()
    sys.exit(0 if success else 1)
