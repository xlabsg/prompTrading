"""Unit tests for BinanceClient and BinanceAdapter."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from risk_engine import (
    BinanceAdapter,
    BinanceClient,
    OrderSide,
    OrderSpec,
    OrderType,
    PositionSide,
    TradingMode,
)


@pytest.fixture
def mock_binance_client():
    client = BinanceClient(
        api_key="test_api_key",
        secret_key="test_secret_key",
        testnet=True,
    )
    return client


@pytest.fixture
def binance_adapter(mock_binance_client):
    return BinanceAdapter(mock_binance_client)


def test_binance_signature(mock_binance_client):
    """Test HMAC SHA256 signature generation."""
    query = "symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=1&price=50000&timestamp=1600000000000"
    sig = mock_binance_client._sign(query)
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex string


def test_normalize_symbol(binance_adapter):
    """Test symbol normalization across various formats."""
    assert binance_adapter.normalize_symbol("BTC-USDT-SWAP") == "BTCUSDT"
    assert binance_adapter.normalize_symbol("ETH/USDT") == "ETHUSDT"
    assert binance_adapter.normalize_symbol("sol-usdt") == "SOLUSDT"
    assert binance_adapter.normalize_symbol("BTCUSDT") == "BTCUSDT"


def test_normalize_price_and_size(binance_adapter):
    """Test price and size rounding against filter rules."""
    # Mock filters
    binance_adapter.client.get_symbol_filters = MagicMock(return_value={
        "tickSize": Decimal("0.1"),
        "stepSize": Decimal("0.001"),
        "minQty": Decimal("0.005"),
        "minNotional": Decimal("5.0"),
    })

    # Price normalization (direction down for BUY)
    p_down = binance_adapter.normalize_price("BTCUSDT", Decimal("60123.456"), direction="down")
    assert p_down == Decimal("60123.4")

    # Price normalization (direction up for SELL)
    p_up = binance_adapter.normalize_price("BTCUSDT", Decimal("60123.411"), direction="up")
    assert p_up == Decimal("60123.5")

    # Size normalization
    sz = binance_adapter.normalize_size("BTCUSDT", Decimal("0.0129"))
    assert sz == Decimal("0.012")

    # Size below minQty should clamp to minQty
    sz_small = binance_adapter.normalize_size("BTCUSDT", Decimal("0.001"))
    assert sz_small == Decimal("0.005")


def test_place_order(binance_adapter):
    """Test order placement and parameter mapping."""
    binance_adapter.client.get_symbol_filters = MagicMock(return_value={
        "tickSize": Decimal("0.01"),
        "stepSize": Decimal("0.001"),
        "minQty": Decimal("0.001"),
        "minNotional": Decimal("5.0"),
    })
    binance_adapter.client.place_order = MagicMock(return_value={"orderId": 123456, "status": "NEW"})

    order_spec = OrderSpec(
        symbol="BTC-USDT-SWAP",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        size=Decimal("0.05"),
        price=Decimal("62000.55"),
        client_order_id="strategy_123_L_456",
        position_side=PositionSide.LONG,
    )

    res = binance_adapter.place_order(order_spec)
    assert res["orderId"] == 123456

    binance_adapter.client.place_order.assert_called_once_with(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("0.050"),
        price=Decimal("62000.55"),
        client_order_id="strategy_123_L_456",
        reduce_only=False,
        position_side="LONG",
        stop_price=None,
    )


def test_cancel_order(binance_adapter):
    """Test order cancellation routing (numeric orderId vs string clientOrderId)."""
    binance_adapter.client.cancel_order = MagicMock(return_value={"status": "CANCELED"})

    # Numeric ID
    assert binance_adapter.cancel_order("BTCUSDT", "987654") is True
    binance_adapter.client.cancel_order.assert_called_with("BTCUSDT", order_id="987654")

    # Client order ID
    assert binance_adapter.cancel_order("BTCUSDT", "cl_ord_123") is True
    binance_adapter.client.cancel_order.assert_called_with("BTCUSDT", client_order_id="cl_ord_123")


def test_get_positions(binance_adapter):
    """Test positionRisk mapping to standardized format."""
    mock_raw_positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.150",
            "entryPrice": "58000.0",
            "markPrice": "60000.0",
            "unRealizedProfit": "300.0",
            "liquidationPrice": "45000.0",
            "leverage": "10",
            "isolatedMargin": "870.0",
            "positionSide": "BOTH",
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "0.000",
            "entryPrice": "0",
            "markPrice": "3000.0",
            "unRealizedProfit": "0",
            "positionSide": "BOTH",
        },
    ]
    binance_adapter.client.get_positions = MagicMock(return_value=mock_raw_positions)

    positions = binance_adapter.get_positions("BTCUSDT")
    assert len(positions) == 1
    pos = positions[0]
    assert pos["instId"] == "BTCUSDT"
    assert pos["pos"] == "0.150"
    assert pos["posSide"] == "long"
    assert pos["avgPx"] == "58000.0"
    assert pos["markPx"] == "60000.0"
    assert pos["upl"] == "300.0"
    assert pos["lever"] == 10
    assert pos["liqPx"] == "45000.0"


def test_get_balance(binance_adapter):
    """Test balance aggregation."""
    mock_balance_res = {
        "balances": [
            {"asset": "USDT", "balance": "5000.00", "availableBalance": "4130.00"},
            {"asset": "BNB", "balance": "10.00", "availableBalance": "10.00"},
        ]
    }
    binance_adapter.client.get_balance = MagicMock(return_value=mock_balance_res)

    bal = binance_adapter.get_balance()
    assert Decimal(bal["totalEq"]) == Decimal("5000.00")
    assert Decimal(bal["availBal"]) == Decimal("4130.00")


def test_set_leverage(binance_adapter):
    """Test leverage and margin mode setting."""
    binance_adapter.client.set_margin_type = MagicMock(return_value=True)
    binance_adapter.client.set_leverage = MagicMock(return_value={"leverage": 20})

    ok = binance_adapter.set_leverage("BTC-USDT", 20, TradingMode.ISOLATED)
    assert ok is True
    binance_adapter.client.set_margin_type.assert_called_with("BTCUSDT", "ISOLATED")
    binance_adapter.client.set_leverage.assert_called_with("BTCUSDT", 20)


def test_test_connection(binance_adapter):
    """Test connection test method."""
    binance_adapter.client.ping = MagicMock(return_value=True)
    assert binance_adapter.test_connection() is True
