#!/bin/bash
# 容器环境一键初始化 Trending 和 Templates 数据
#
# 使用方法：
#   cd infra/compose
#   ./init_trending_templates_container.sh [--dev]

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

# 步骤 1: 初始化 Templates (调用单一真相源 seed_builtin_templates.py)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 1/5: 初始化内置策略模板"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python /app/services/api/scripts/seed_builtin_templates.py
echo ""

# 步骤 2: 配置 Trending 定时任务
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 2/5: 配置 Trending 定时任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python /app/services/api/scripts/setup_trending_schedule.py
echo ""

# 步骤 3: 配置 Templates 性能更新任务
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 3/5: 配置 Templates 性能更新任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f "$COMPOSE_FILE" exec -T api python /app/services/api/scripts/setup_template_performance_schedule.py
echo ""

# 步骤 4: 触发 Trending 抓取（可选）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 4/5: 触发 Trending 抓取"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "是否立即触发 Trending 抓取？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f "$COMPOSE_FILE" exec -T api python /app/services/api/scripts/trigger_trending_scrape.py --max-count 50 --auto-backtest --backtest-top-n 10
    echo ""
    echo "⏳ Trending 抓取任务已创建"
    echo "   预计需要 10-20 分钟（包括回测）"
    echo "   查看进度: docker compose -f $COMPOSE_FILE logs -f worker"
else
    echo "⏭️  跳过 Trending 抓取"
    echo "   稍后可手动运行: ./trigger_trending_scrape_container.sh"
fi
echo ""

# 步骤 5: 生成 Templates 性能数据（可选）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 5/5: 生成 Templates 性能数据"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "是否生成模板性能数据？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f "$COMPOSE_FILE" exec -T api python /app/services/api/scripts/generate_template_performance.py
else
    echo "⏭️  跳过性能数据生成"
    echo "   稍后可手动运行: ./generate_template_performance_container.sh"
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
echo "  curl http://localhost:8000/api/templates | jq '. | length'"
echo "  curl http://localhost:8000/api/trending/stats | jq"
echo ""
