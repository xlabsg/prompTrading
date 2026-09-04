#!/bin/bash
# Install dependencies and run tests in the API container

set -e

echo "=================================================="
echo "Verifying Dependencies and Imports..."
echo "=================================================="

python << 'EOF'
import cryptography
import okx_sdk
import risk_engine
from control_plane.models import TradingConfig, TradingSession, Order, Position
from control_plane.enums import TradingSessionStatus, OrderStatus, PositionStatus

print("✓ Cryptography installed")
print("✓ OKX SDK imported")
print("✓ Risk Engine imported")
print("✓ TradingConfig, TradingSession, Order, Position imported")
print("✓ All enums imported")
print("✅ Core imports verification PASSED")
EOF

echo ""
echo "=================================================="
echo "Running API Test Suite"
echo "=================================================="
echo ""

# Run API unit/integration tests
cd /app
if [ -d "tests" ]; then
    pytest tests -q
elif [ -d "services/api/tests" ]; then
    pytest services/api/tests -q
fi

echo ""
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Set TRADING_API_ENCRYPTION_KEY environment variable"
echo "2. Test OKX API connectivity with real credentials (optional)"
echo "3. Use the UI to configure trading"
echo ""
