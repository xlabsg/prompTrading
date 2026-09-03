#!/usr/bin/env python3
"""
验证 Trending 和 Templates 数据

检查数据是否正确初始化
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import (
    StrategyTemplate,
    TradingViewTrendingStrategy,
    TrendingSchedule,
    TemplatePerformanceSchedule,
)
from app.settings import settings


def print_section(title):
    """打印章节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def check_templates():
    """检查 Templates 数据"""

    print_section("📚 Templates 数据检查")

    engine = create_db_engine(settings.db_url)

    with session_scope(create_session_factory(engine)) as db:
        total = db.query(StrategyTemplate).count()
        public = db.query(StrategyTemplate).filter(
            StrategyTemplate.is_public == True
        ).count()
        featured = db.query(StrategyTemplate).filter(
            StrategyTemplate.is_featured == True
        ).count()
        builtin = db.query(StrategyTemplate).filter(
            StrategyTemplate.template_type == 'builtin'
        ).count()
        total_subs = db.query(StrategyTemplate).all()
        total_subs = sum(t.subscriber_count or 0 for t in total_subs)

        print(f"总模板数: {total}")
        print(f"公开模板: {public}")
        print(f"精选模板: {featured}")
        print(f"内置模板: {builtin}")
        print(f"总订阅数: {total_subs}")

        if total == 0:
            print("\n❌ 未找到模板数据！")
            print("   请运行: python scripts/seed_builtin_templates.py")
            return False

        # 列出模板
        print("\n模板列表:")
        templates = db.query(StrategyTemplate).order_by(
            StrategyTemplate.updated_at.desc()
        ).limit(10).all()

        for t in templates:
            featured = "⭐" if t.is_featured else "  "
            print(f"  {featured} {t.name}")
            print(f"     类型: {t.template_type}, 风险: {t.risk_level}, 订阅: {t.subscriber_count or 0}")

        return True


def check_trending():
    """检查 Trending 数据"""

    print_section("📈 Trending 数据检查")

    engine = create_db_engine(settings.db_url)

    with session_scope(create_session_factory(engine)) as db:
        total = db.query(TradingViewTrendingStrategy).count()
        completed = db.query(TradingViewTrendingStrategy).filter(
            TradingViewTrendingStrategy.backtest_status == 'completed'
        ).count()
        pending = db.query(TradingViewTrendingStrategy).filter(
            TradingViewTrendingStrategy.backtest_status == 'pending'
        ).count()
        failed = db.query(TradingViewTrendingStrategy).filter(
            TradingViewTrendingStrategy.backtest_status == 'failed'
        ).count()

        print(f"总策略数: {total}")
        print(f"回测完成: {completed}")
        print(f"等待回测: {pending}")
        print(f"回测失败: {failed}")

        if total == 0:
            print("\n⚠️  未找到 Trending 数据")
            print("   这是正常的，如果还没有触发抓取")
            print("   运行: python scripts/trigger_trending_scrape.py")
            return True

        # 列出 Top 策略
        print("\nTop 5 策略:")
        top_strategies = db.query(TradingViewTrendingStrategy).order_by(
            TradingViewTrendingStrategy.scraped_at.desc()
        ).limit(5).all()

        for s in top_strategies:
            print(f"  {s.title[:60]}")
            print(f"     状态: {s.backtest_status}, "
                  f"点赞: {s.likes or 0}")

        return True


def check_schedules():
    """检查定时任务配置"""

    print_section("⏰ 定时任务配置检查")

    engine = create_db_engine(settings.db_url)

    with session_scope(create_session_factory(engine)) as db:
        # Trending Schedule
        trending_schedule = db.query(TrendingSchedule).first()
        print("Trending 定时任务:")
        if trending_schedule:
            status = "✅ 启用" if trending_schedule.enabled else "❌ 禁用"
            print(f"  状态: {status}")
            print(f"  Cron: {trending_schedule.cron_expression}")
            print(f"  抓取数: {trending_schedule.max_count}")
            print(f"  自动回测: {trending_schedule.auto_backtest}")
            if trending_schedule.last_run_at:
                print(f"  上次运行: {trending_schedule.last_run_at}")
        else:
            print("  ⚠️  未配置")
            print("  运行: python scripts/setup_trending_schedule.py")

        print()

        # Template Performance Schedule
        template_schedule = db.query(TemplatePerformanceSchedule).first()
        print("Templates 性能更新:")
        if template_schedule:
            status = "✅ 启用" if template_schedule.enabled else "❌ 禁用"
            print(f"  状态: {status}")
            print(f"  Cron: {template_schedule.cron_expression}")
            print(f"  每批处理: {template_schedule.templates_per_batch}")
            print(f"  历史天数: {template_schedule.backtest_days_history}")
            if template_schedule.last_run_at:
                print(f"  上次运行: {template_schedule.last_run_at}")
        else:
            print("  ⚠️  未配置")
            print("  运行: python scripts/setup_template_performance_schedule.py")

        return True


def main():
    """主函数"""

    print("\n🔍 Trending & Templates 数据验证")
    print("检查数据是否正确初始化...")

    all_ok = True

    # 检查 Templates
    if not check_templates():
        all_ok = False

    # 检查 Trending
    if not check_trending():
        all_ok = False

    # 检查定时任务
    check_schedules()

    # 总结
    print_section("📊 总结")

    if all_ok:
        print("✅ 所有数据检查通过！")
        print("\n下一步:")
        print("  1. 访问前端查看 Trending 和 Templates 页面")
        print("  2. 如果需要 Trending 数据，运行抓取脚本")
        print("  3. 定期检查 Worker 日志确保定时任务正常运行")
    else:
        print("⚠️  发现问题，请根据上述提示修复")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
