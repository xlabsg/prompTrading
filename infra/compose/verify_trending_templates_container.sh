#!/bin/bash
# 容器环境验证 Trending 和 Templates 数据

set -e

echo "🔍 验证 Trending & Templates 数据"
echo ""

COMPOSE_FILE="docker-compose.prod.yml"
if [ "$1" = "--dev" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 Templates 数据检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate
from app.settings import settings

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    total = db.query(StrategyTemplate).count()
    public = db.query(StrategyTemplate).filter(StrategyTemplate.is_public == True).count()
    featured = db.query(StrategyTemplate).filter(StrategyTemplate.is_featured == True).count()

    print(f'总模板数: {total}')
    print(f'公开模板: {public}')
    print(f'精选模板: {featured}')

    if total == 0:
        print('\n❌ 未找到模板数据！')
    else:
        print(f'\n模板列表:')
        templates = db.query(StrategyTemplate).order_by(StrategyTemplate.updated_at.desc()).limit(5).all()
        for t in templates:
            featured = '⭐' if t.is_featured else '  '
            print(f'  {featured} {t.name}')
"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 Trending 数据检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import TradingViewTrendingStrategy
from app.settings import settings

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    total = db.query(TradingViewTrendingStrategy).count()
    completed = db.query(TradingViewTrendingStrategy).filter(
        TradingViewTrendingStrategy.backtest_status == 'completed'
    ).count()
    pending = db.query(TradingViewTrendingStrategy).filter(
        TradingViewTrendingStrategy.backtest_status == 'pending'
    ).count()

    print(f'总策略数: {total}')
    print(f'回测完成: {completed}')
    print(f'等待回测: {pending}')

    if total == 0:
        print('\n⚠️  未找到 Trending 数据（这是正常的，如果还没有触发抓取）')
    else:
        print(f'\nTop 3 策略:')
        top = db.query(TradingViewTrendingStrategy).order_by(
            TradingViewTrendingStrategy.scraped_at.desc()
        ).limit(3).all()
        for s in top:
            print(f'  {s.title[:50]}...')
"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏰ 定时任务配置检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import TrendingSchedule, TemplatePerformanceSchedule
from app.settings import settings

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    trending = db.query(TrendingSchedule).first()
    print('Trending 定时任务:')
    if trending:
        status = '✅ 启用' if trending.enabled else '❌ 禁用'
        print(f'  状态: {status}')
        print(f'  Cron: {trending.cron_expression}')
        if trending.last_run_at:
            print(f'  上次运行: {trending.last_run_at}')
    else:
        print('  ⚠️  未配置')

    print()

    template = db.query(TemplatePerformanceSchedule).first()
    print('Templates 性能更新:')
    if template:
        status = '✅ 启用' if template.enabled else '❌ 禁用'
        print(f'  状态: {status}')
        print(f'  Cron: {template.cron_expression}')
        if template.last_run_at:
            print(f'  上次运行: {template.last_run_at}')
    else:
        print('  ⚠️  未配置')
"
echo ""

echo "=========================================="
echo "  ✅ 验证完成"
echo "=========================================="
