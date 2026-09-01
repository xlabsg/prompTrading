#!/bin/bash
# Install dependencies and run tests in the API container

set -e

echo "=================================================="
echo "Installing OKX SDK and dependencies..."
echo "=================================================="

# Install OKX SDK in development mode
pip install -e /app/../../packages/okx_sdk

# Verify cryptography is installed
pip list | grep cryptography || pip install cryptography

echo ""
echo "=================================================="
echo "Running OKX SDK and Encryption Tests"
echo "=================================================="
echo ""

# Run the test script
python test_okx_setup.py

echo ""
echo "=================================================="
echo "Testing Database Models"
echo "=================================================="
echo ""

# Quick Python check for database models
python << 'EOF'
import sys
sys.path.insert(0, '/app/../../packages/control_plane')

from control_plane.models import TradingConfig, TradingSession, Order, Position
from control_plane.enums import TradingSessionStatus, OrderStatus, PositionStatus

print("✓ TradingConfig model imported")
print("✓ TradingSession model imported")
print("✓ Order model imported")
print("✓ Position model imported")
print("✓ All enums imported")
print("\n✅ Database models verification PASSED")
EOF

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
