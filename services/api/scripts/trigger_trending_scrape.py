#!/usr/bin/env python3
"""
手动触发 Trending 抓取任务

创建 TRENDING_SCRAPE 任务并添加到队列
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Job
from app.settings import settings


def trigger_trending_scrape(
    max_count: int = 50,
    auto_backtest: bool = True,
    backtest_top_n: int = 10
):
    """
    创建 TRENDING_SCRAPE 任务

    Args:
        max_count: 最大抓取数量
        auto_backtest: 是否自动回测
        backtest_top_n: 回测前 N 个
    """

    print("🔄 触发 Trending 抓取任务...")

    # 创建任务
    job_id = str(uuid.uuid4())
    engine = create_db_engine(settings.db_url)

    try:
        with session_scope(create_session_factory(engine)) as db:
            job = Job(
                id=job_id,
                type="TRENDING_SCRAPE",
                payload={
                    "source_types": ["script"],
                    "max_count": max_count,
                    "auto_backtest": auto_backtest,
                    "auto_backtest_top_n": backtest_top_n,
                },
                status="queued",
            )
            db.add(job)
            db.commit()

        from control_plane.queue import enqueue_job
        enqueue_job(settings.workspaces_dir, job_id, "TRENDING_SCRAPE", priority="batch")

        print(f"✅ Trending 抓取任务已创建: {job_id[:8]}...")
        print("\n任务配置:")
        print(f"   - 最大抓取: {max_count}")
        print(f"   - 自动回测: {auto_backtest}")
        print(f"   - 回测数量: {backtest_top_n}")
        print("\n等待 Worker 处理...")
        print("查看日志: docker compose logs -f worker")

        return True

    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="触发 Trending 抓取任务")
    parser.add_argument("--max-count", type=int, default=50, help="最大抓取数量")
    parser.add_argument("--no-backtest", action="store_true", help="不自动回测")
    parser.add_argument("--backtest-top-n", type=int, default=10, help="回测前 N 个")

    args = parser.parse_args()

    success = trigger_trending_scrape(
        max_count=args.max_count,
        auto_backtest=not args.no_backtest,
        backtest_top_n=args.backtest_top_n,
    )

    sys.exit(0 if success else 1)
