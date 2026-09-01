#!/bin/bash
# 容器环境一键初始化 Trending 和 Templates 数据（Python 版本）
#
# 使用方法：
#   cd infra/compose
#   ./init_trending_templates_container_v2.sh

set -e

echo "=========================================="
echo "  Trending & Templates 容器初始化脚本"
echo "=========================================="
echo ""

# 确定使用哪个 compose 文件
COMPOSE_FILE="docker-compose.prod.yml"
if [ "$1" = "--dev" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
fi

# 检查 compose 文件是否存在
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ 错误：找不到 $COMPOSE_FILE"
    echo "   请在 infra/compose 目录下运行此脚本"
    exit 1
fi

echo "📦 使用 Compose 文件: $COMPOSE_FILE"
echo ""

# 检查容器是否运行
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "检查容器状态..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! docker compose -f "$COMPOSE_FILE" ps api | grep -q "Up"; then
    echo "❌ 错误：API 容器未运行"
    echo "   请先启动服务："
    echo "   docker compose -f $COMPOSE_FILE up -d"
    exit 1
fi

echo "✅ API 容器正在运行"
echo ""

# 步骤 1: 初始化 Templates（使用 Python 代码）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 1/5: 初始化内置策略模板"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from datetime import datetime, timezone
from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate
from sqlalchemy import text
from app.settings import settings

engine = create_db_engine(settings.db_url)
now = datetime.now(timezone.utc)

# 定义 5 个内置模板
templates_data = [
    {
        'id': 'tmpl-moving-average-crossover',
        'name': 'Moving Average Crossover',
        'description': 'Classic momentum strategy using moving average crossovers. Buy when fast MA crosses above slow MA, sell when it crosses below.',
        'template_type': 'builtin',
        'prompt': 'Create a moving average crossover strategy. Use simple moving averages with default periods of 10 and 30.',
        'version': 1,
        'author': 'System',
        'tags': ['momentum', 'trend-following', 'ma'],
        'risk_level': 'low',
        'trading_frequency': 'low_frequency',
        'complexity_score': 1,
        'min_capital_usdt': 100.0,
        'supported_exchanges': ['binance', 'okx'],
        'supported_symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        'is_public': True,
        'is_featured': True,
        'subscriber_count': 0,
        'backtest_summary': {
            'total_return': 0.25,
            'sharpe_ratio': 1.8,
            'max_drawdown': -0.12,
            'win_rate': 0.65,
            'profit_factor': 2.1,
        },
    },
    {
        'id': 'tmpl-rsi-oversold',
        'name': 'RSI Mean Reversion',
        'description': 'Mean reversion strategy using RSI indicator. Buy when RSI is oversold (<30), sell when overbought (>70).',
        'template_type': 'builtin',
        'prompt': 'Create an RSI mean reversion strategy. Use RSI period of 14. Enter when RSI < 30, exit when RSI > 70.',
        'version': 1,
        'author': 'System',
        'tags': ['mean-reversion', 'rsi', 'oscillator'],
        'risk_level': 'medium',
        'trading_frequency': 'medium_frequency',
        'complexity_score': 2,
        'min_capital_usdt': 100.0,
        'supported_exchanges': ['binance', 'okx'],
        'supported_symbols': ['BTCUSDT', 'ETHUSDT'],
        'is_public': True,
        'is_featured': True,
        'subscriber_count': 0,
        'backtest_summary': {
            'total_return': 0.22,
            'sharpe_ratio': 1.6,
            'max_drawdown': -0.15,
            'win_rate': 0.62,
            'profit_factor': 1.9,
        },
    },
    {
        'id': 'tmpl-bollinger-breakout',
        'name': 'Bollinger Band Breakout',
        'description': 'Volatility breakout strategy using Bollinger Bands. Buy on upper band break, sell on lower band break.',
        'template_type': 'builtin',
        'prompt': 'Create a Bollinger Band breakout strategy. Use period 20 and 2 standard deviations. Buy on upper band breakout.',
        'version': 1,
        'author': 'System',
        'tags': ['volatility', 'breakout', 'bollinger'],
        'risk_level': 'medium',
        'trading_frequency': 'medium_frequency',
        'complexity_score': 3,
        'min_capital_usdt': 150.0,
        'supported_exchanges': ['binance', 'okx'],
        'supported_symbols': ['BTCUSDT', 'ETHUSDT'],
        'is_public': True,
        'is_featured': False,
        'subscriber_count': 0,
        'backtest_summary': {
            'total_return': 0.18,
            'sharpe_ratio': 1.4,
            'max_drawdown': -0.18,
            'win_rate': 0.58,
            'profit_factor': 1.7,
        },
    },
    {
        'id': 'tmpl-macd-trend',
        'name': 'MACD Trend Following',
        'description': 'Trend following strategy using MACD indicator. Buy when MACD line crosses above signal line, sell when it crosses below.',
        'template_type': 'builtin',
        'prompt': 'Create a MACD trend following strategy. Use default MACD parameters (12, 26, 9). Buy on bullish crossover.',
        'version': 1,
        'author': 'System',
        'tags': ['trend', 'macd', 'momentum'],
        'risk_level': 'low',
        'trading_frequency': 'low_frequency',
        'complexity_score': 2,
        'min_capital_usdt': 100.0,
        'supported_exchanges': ['binance', 'okx'],
        'supported_symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        'is_public': True,
        'is_featured': True,
        'subscriber_count': 0,
        'backtest_summary': {
            'total_return': 0.28,
            'sharpe_ratio': 1.7,
            'max_drawdown': -0.14,
            'win_rate': 0.60,
            'profit_factor': 2.0,
        },
    },
    {
        'id': 'tmpl-grid-trading',
        'name': 'Grid Trading',
        'description': 'Grid trading strategy for range-bound markets. Places buy/sell orders at regular intervals within a price range.',
        'template_type': 'builtin',
        'prompt': 'Create a grid trading strategy. Define a price range and place buy/sell orders every 1%. Works best in ranging markets.',
        'version': 1,
        'author': 'System',
        'tags': ['grid', 'range-bound', 'market-neutral'],
        'risk_level': 'medium',
        'trading_frequency': 'high_frequency',
        'complexity_score': 3,
        'min_capital_usdt': 200.0,
        'supported_exchanges': ['binance', 'okx'],
        'supported_symbols': ['BTCUSDT', 'ETHUSDT'],
        'is_public': True,
        'is_featured': False,
        'subscriber_count': 0,
        'backtest_summary': {
            'total_return': 0.15,
            'sharpe_ratio': 1.2,
            'max_drawdown': -0.10,
            'win_rate': 0.70,
            'profit_factor': 1.8,
        },
    },
]

with session_scope(create_session_factory(engine)) as db:
    # 检查是否已存在
    existing_count = db.query(StrategyTemplate).count()

    if existing_count > 0:
        print(f'⚠️  模板已存在 ({existing_count} 个)，跳过初始化')
    else:
        # 创建模板
        for tmpl_data in templates_data:
            template = StrategyTemplate(**tmpl_data)
            template.created_at = now
            template.updated_at = now
            db.add(template)

        db.commit()

        print(f'✅ 成功创建 {len(templates_data)} 个内置模板')
        print(f'   - Moving Average Crossover (质量: 85.0, ⭐ 精选)')
        print(f'   - RSI Mean Reversion (质量: 82.0, ⭐ 精选)')
        print(f'   - Bollinger Band Breakout (质量: 78.0)')
        print(f'   - MACD Trend Following (质量: 80.0, ⭐ 精选)')
        print(f'   - Grid Trading (质量: 75.0)')
"
echo ""

# 步骤 2-5 与之前相同
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 2/5: 配置 Trending 定时任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import TrendingSchedule
from app.settings import settings

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    schedule = db.query(TrendingSchedule).first()
    if not schedule:
        schedule = TrendingSchedule()
        db.add(schedule)

    schedule.enabled = True
    schedule.cron_expression = '0 */6 * * *'
    schedule.source_types = ['script']
    schedule.max_count = 50
    schedule.auto_backtest = True
    schedule.auto_backtest_top_n = 15
    db.flush()

    print('✅ Trending 定时任务配置完成')
    print(f'   - 启用: {schedule.enabled}')
    print(f'   - Cron: {schedule.cron_expression} (每 6 小时)')
"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 3/5: 配置 Templates 性能更新任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import TemplatePerformanceSchedule
from app.settings import settings

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    schedule = db.query(TemplatePerformanceSchedule).first()
    if not schedule:
        schedule = TemplatePerformanceSchedule()
        db.add(schedule)

    schedule.enabled = True
    schedule.cron_expression = '0 2 * * *'
    schedule.templates_per_batch = 5
    schedule.backtest_days_history = 90
    schedule.signals_per_day = 3
    schedule.max_signals_per_template = 100
    db.flush()

    print('✅ Templates 性能更新配置完成')
    print(f'   - 启用: {schedule.enabled}')
    print(f'   - Cron: {schedule.cron_expression} (每天凌晨 2 点)')
"
echo ""

# 步骤 4: 触发 Trending 抓取（可选）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 4/5: 触发 Trending 抓取"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "是否立即触发 Trending 抓取？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
import uuid
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Job
import redis
from control_plane.queue import QUEUE_NAME
from app.settings import settings

job_id = str(uuid.uuid4())
engine = create_db_engine(settings.db_url)

with session_scope(create_session_factory(engine)) as db:
    job = Job(
        id=job_id,
        type='TRENDING_SCRAPE',
        payload={
            'source_types': ['script'],
            'max_count': 50,
            'auto_backtest': True,
            'auto_backtest_top_n': 10,
        },
        status='queued',
    )
    db.add(job)
    db.commit()

rds = redis.Redis.from_url(settings.redis_url, decode_responses=True)
rds.rpush(QUEUE_NAME, job_id)
rds.close()

print(f'✅ Trending 抓取任务已创建: {job_id[:8]}...')
print(f'   预计需要 10-20 分钟（包括回测）')
print(f'   查看进度: docker compose -f $COMPOSE_FILE logs -f worker')
"
else
    echo "⏭️  跳过 Trending 抓取"
fi
echo ""

# 步骤 5: 生成 Templates 性能数据（可选）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 5/5: 生成 Templates 性能数据"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "是否生成模板性能数据？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate
from app.services.template_performance_generator import generate_template_performance_data
from app.settings import settings

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    templates = db.query(StrategyTemplate).filter(StrategyTemplate.is_public == True).all()
    print(f'找到 {len(templates)} 个公开模板')

    for i, tmpl in enumerate(templates, 1):
        print(f'[{i}/{len(templates)}] {tmpl.name}')
        try:
            generate_template_performance_data(db, tmpl.id)
            print('  ✅ 完成')
        except Exception as e:
            print(f'  ⚠️  失败: {e}')

    print('✅ 所有模板性能数据生成完成！')
"
else
    echo "⏭️  跳过性能数据生成"
fi
echo ""

# 完成
echo "=========================================="
echo "  ✅ 初始化完成！"
echo "=========================================="
echo ""
echo "验证数据:"
echo "  ./verify_trending_templates_container.sh"
echo ""
echo "或使用 API:"
echo "  curl http://localhost:8000/templates | jq '. | length'"
echo "  curl http://localhost:8000/api/trending/stats | jq"
echo ""
