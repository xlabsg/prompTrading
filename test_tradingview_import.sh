#!/bin/bash
# Quick test script for TradingView import functionality

set -e

echo "🧪 Testing TradingView Import Functionality"
echo "=========================================="
echo ""

# Test 1: Check if tradingview_scraper is installed
echo "✓ Test 1: Checking tradingview_scraper installation..."
docker compose -f infra/compose/docker-compose.dev.yml exec -T api python -c "
from tradingview_scraper import get_pinescript
print('✓ tradingview_scraper imported successfully')
" || echo "✗ Failed to import tradingview_scraper"

# Test 2: Test scraping a public TradingView script
echo ""
echo "✓ Test 2: Testing PineScript scraping..."
docker compose -f infra/compose/docker-compose.dev.yml exec -T api python -c "
from tradingview_scraper import get_pinescript
import json

# Test with a well-known public indicator
url = 'https://www.tradingview.com/script/jXvqrU4q-OBV-MACD-Indicator/'
print(f'Fetching: {url}')

result = get_pinescript(url)
print(f'Script Name: {result.get(\"name\", \"N/A\")}')
print(f'Author: {result.get(\"author\", \"N/A\")}')
print(f'Has Source: {\"Yes\" if result.get(\"source\") else \"No\"}')

if result.get('source'):
    print(f'Source Length: {len(result[\"source\"])} characters')
    print('✓ Successfully fetched PineScript source')
else:
    print(f'✗ Failed: {result.get(\"error\", \"Unknown error\")}')
" || echo "✗ Failed to scrape TradingView URL"

# Test 3: Test API endpoint
echo ""
echo "✓ Test 3: Testing import API endpoint..."
curl -s -X POST http://localhost:8000/api/strategies/import/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.tradingview.com/script/jXvqrU4q/",
    "strategy_name": "Test Import Strategy"
  }' | python -m json.tool || echo "✗ API endpoint test failed (may need authentication)"

echo ""
echo "=========================================="
echo "🎉 Tests completed!"
echo ""
echo "Next steps:"
echo "1. Check API logs: docker compose -f infra/compose/docker-compose.dev.yml logs api"
echo "2. Test via UI: http://localhost:3000 -> Click 'Import Strategy'"
echo "3. Monitor job progress in console"
