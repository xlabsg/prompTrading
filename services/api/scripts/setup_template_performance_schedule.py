#!/usr/bin/env python3
"""
配置 Templates 性能更新定时任务

创建或更新 TemplatePerformanceSchedule 配置
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import TemplatePerformanceSchedule
from app.settings import settings


def setup_template_performance_schedule():
    """创建或更新 Templates 性能更新配置"""

    print("📅 配置 Templates 性能更新任务...")

    engine = create_db_engine(settings.db_url)

    try:
        with session_scope(create_session_factory(engine)) as db:
            schedule = db.query(TemplatePerformanceSchedule).first()

            if not schedule:
                schedule = TemplatePerformanceSchedule()
                db.add(schedule)

            # 默认配置
            schedule.enabled = True
            schedule.cron_expression = "0 2 * * *"  # 每天凌晨 2 点 UTC
            schedule.templates_per_batch = 5
            schedule.backtest_days_history = 90
            schedule.signals_per_day = 3
            schedule.max_signals_per_template = 100

            db.flush()

            print(f"✅ Templates 性能更新配置完成:")
            print(f"   - 启用: {schedule.enabled}")
            print(f"   - Cron: {schedule.cron_expression} (每天凌晨 2 点 UTC)")
            print(f"   - 每批处理: {schedule.templates_per_batch} 个模板")
            print(f"   - 历史天数: {schedule.backtest_days_history}")
            print(f"   - 每天信号数: {schedule.signals_per_day}")
            print(f"   - 最大信号数: {schedule.max_signals_per_template}")

            return True

    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = setup_template_performance_schedule()
    sys.exit(0 if success else 1)
