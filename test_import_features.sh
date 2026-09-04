#!/bin/bash
# 完整的策略导入功能测试脚本

set -e

echo "🧪 Testing Strategy Import Functionality"
echo "=========================================="
echo ""

echo "📦 Test 1: TradingView Scraper"
echo "-------------------------------"
docker compose -f infra/compose/docker-compose.dev.yml exec -T api python -c "
from tradingview_scraper import get_pinescript
print('✓ TradingView scraper imported successfully')

# Test with a public script
url = 'https://www.tradingview.com/script/jXvqrU4q-OBV-MACD-Indicator/'
result = get_pinescript(url)
print(f'✓ Script Name: {result.get(\"name\", \"N/A\")}')
print(f'✓ Has Source: {\"Yes\" if result.get(\"source\") else \"No\"}')
" || echo "✗ TradingView scraper test failed"

echo ""
echo "📺 Test 2: YouTube Processor (Temporarily Disabled)"
echo "-------------------------------"
echo "ℹ️  YouTube import is temporarily parked/disabled (see CLAUDE.md)."
echo "   Skipping container import check."

echo ""
echo "🔌 Test 3: API Endpoints"
echo "-------------------------------"
echo "Testing TradingView import endpoint..."
curl -s -X POST http://localhost:8000/api/strategies/import/tradingview \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.tradingview.com/script/test/"}' \
  | python -m json.tool | head -20 || echo "(Endpoint requires authentication)"

echo ""
echo "Testing YouTube import endpoint..."
curl -s -X POST http://localhost:8000/api/strategies/import/youtube \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=test"}' \
  | python -m json.tool | head -20 || echo "(Endpoint requires authentication)"

echo ""
echo "=========================================="
echo "🎉 All tests completed!"
echo ""
echo "📋 Next Steps:"
echo "1. Visit http://localhost:3000"
echo "2. Click 'Import Strategy' button"
echo "3. Test TradingView import (Tab 1)"
echo "4. Test YouTube import (Tab 2)"
echo ""
echo "📚 Documentation:"
echo "- TradingView: Use public script URLs"
echo "- YouTube: Max 30 minutes, clear strategy content"
echo ""
echo "🔍 Monitor logs:"
echo "docker compose -f infra/compose/docker-compose.dev.yml logs -f api"
