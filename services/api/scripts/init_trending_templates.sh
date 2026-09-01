#!/bin/bash
# 一键初始化 Trending 和 Templates 数据

set -e

echo "=========================================="
echo "  Trending & Templates 初始化脚本"
echo "=========================================="
echo ""

# 检查是否在正确的目录
if [ ! -f "pyproject.toml" ] && [ ! -f "../pyproject.toml" ]; then
    echo "❌ 错误：请在 services/api 目录下运行此脚本"
    exit 1
fi

# 检查环境变量
if [ -z "$APP_DB_URL" ] && [ -z "$DATABASE_URL" ]; then
    echo "❌ 错误：请设置数据库连接字符串"
    echo "   export APP_DB_URL='postgresql+psycopg://user:pass@host:5432/db'"
    exit 1
fi

echo "✅ 环境检查通过"
echo ""

# 步骤 1: 初始化 Templates
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 1/5: 初始化内置策略模板"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python scripts/seed_builtin_templates.py
echo ""

# 步骤 2: 配置 Trending 定时任务
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 2/5: 配置 Trending 定时任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python scripts/setup_trending_schedule.py
echo ""

# 步骤 3: 配置 Templates 性能更新任务
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 3/5: 配置 Templates 性能更新任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python scripts/setup_template_performance_schedule.py
echo ""

# 步骤 4: 触发 Trending 抓取（可选）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 4/5: 触发 Trending 抓取"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "是否立即触发 Trending 抓取？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python scripts/trigger_trending_scrape.py --max-count 50 --min-quality 30 --backtest-top-n 10
    echo ""
    echo "⏳ Trending 抓取任务已创建"
    echo "   预计需要 10-20 分钟完成（包括回测）"
    echo "   查看进度: docker compose logs -f worker"
else
    echo "⏭️  跳过 Trending 抓取"
    echo "   稍后可手动运行: python scripts/trigger_trending_scrape.py"
fi
echo ""

# 步骤 5: 生成 Templates 性能数据（可选）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 5/5: 生成 Templates 性能数据"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "是否生成模板性能数据？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python scripts/generate_template_performance.py
else
    echo "⏭️  跳过性能数据生成"
    echo "   稍后可手动运行: python scripts/generate_template_performance.py"
fi
echo ""

# 完成
echo "=========================================="
echo "  ✅ 初始化完成！"
echo "=========================================="
echo ""
echo "验证数据:"
echo "  Templates: curl http://localhost:8000/templates | jq '. | length'"
echo "  Trending:  curl http://localhost:8000/api/trending/stats | jq"
echo ""
echo "查看日志:"
echo "  Worker: docker compose logs -f worker"
echo "  API:    docker compose logs -f api"
echo ""
