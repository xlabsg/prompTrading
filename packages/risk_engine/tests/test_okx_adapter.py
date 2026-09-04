"""Unit tests for OKXAdapter."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from okx_sdk.models import Balance as OKXBalance, OrderResponse, Position as OKXPosition
from risk_engine import (
    OKXAdapter,
    OrderSide,
    OrderSpec,
    OrderType,
    PositionSide,
    TradingMode,
)


@pytest.fixture
def mock_okx_client():
    """Mock of the real okx_sdk.client.OKXClient."""
    client = MagicMock()
    # Mock get_instrument
    client.get_instrument.return_value = {
        "tickSz": "0.1",
        "lotSz": "0.01",
        "minSz": "0.01",
    }
    return client


@pytest.fixture
def mock_paper_client():
    """Mock of the PaperExchangeClient used in paper trading / simulator."""
    client = MagicMock()
    # PaperExchangeClient.get_instrument only accepts inst_id
    def _fake_get_instrument(inst_id: str):
        return {
            "tickSz": "0.1",
            "lotSz": "0.01",
            "minSz": "0.01",
        }
    client.get_instrument = MagicMock(side_effect=_fake_get_instrument)
    return client


@pytest.fixture
def okx_adapter(mock_okx_client):
    return OKXAdapter(mock_okx_client)


@pytest.fixture
def paper_adapter(mock_paper_client):
    return OKXAdapter(mock_paper_client)


# --- Symbol & Precision Normalization Tests ---

def test_normalize_symbol(okx_adapter):
    """Test symbol normalization to OKX format."""
    assert okx_adapter.normalize_symbol("BTC-USDT-SWAP") == "BTC-USDT-SWAP"
    assert okx_adapter.normalize_symbol("BTC/USDT:USDT") == "BTC-USDT-SWAP"
    assert okx_adapter.normalize_symbol("ETH/USDT") == "ETH-USDT"
    assert okx_adapter.normalize_symbol("BTCUSDT") == "BTC-USDT-SWAP"


def test_normalize_price_and_size_okx_client(okx_adapter, mock_okx_client):
    """Test price and size rounding against OKXClient get_instrument."""
    p_down = okx_adapter.normalize_price("BTC-USDT-SWAP", Decimal("60123.456"), direction="down")
    assert p_down == Decimal("60123.4")
    mock_okx_client.get_instrument.assert_called_with("SWAP", "BTC-USDT-SWAP")

    p_up = okx_adapter.normalize_price("BTC-USDT-SWAP", Decimal("60123.411"), direction="up")
    assert p_up == Decimal("60123.5")

    sz = okx_adapter.normalize_size("BTC-USDT-SWAP", Decimal("0.0567"))
    assert sz == Decimal("0.05")

    # Clamps to minSz
    sz_min = okx_adapter.normalize_size("BTC-USDT-SWAP", Decimal("0.001"))
    assert sz_min == Decimal("0.01")


def test_normalize_price_and_size_paper_client(paper_adapter, mock_paper_client):
    """Test price and size rounding against PaperExchangeClient get_instrument."""
    p = paper_adapter.normalize_price("BTC-USDT-SWAP", Decimal("50000.789"))
    assert p == Decimal("50000.7")
    mock_paper_client.get_instrument.assert_called_with("BTC-USDT-SWAP")


# --- Place & Cancel Order Tests ---

def test_place_order_with_okx_client(okx_adapter, mock_okx_client):
    """Test placing an order via real OKXClient passing snake_case kwargs and receiving OrderResponse."""
    mock_okx_client.place_order.return_value = OrderResponse(
        ord_id="11223344",
        cl_ord_id="strat_001_1",
        s_code="0",
        s_msg="",
    )

    spec = OrderSpec(
        symbol="BTC-USDT-SWAP",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        size=Decimal("0.5"),
        price=Decimal("65000.0"),
        client_order_id="strat_001_1",
        position_side=PositionSide.LONG,
        reduce_only=False,
    )

    result = okx_adapter.place_order(spec)

    assert result["ordId"] == "11223344"
    assert result["clOrdId"] == "strat_001_1"

    # Ensure OKXClient.place_order was called with correct snake_case keywords matching OKXClient signature
    mock_okx_client.place_order.assert_called_once_with(
        inst_id="BTC-USDT-SWAP",
        side="buy",
        ord_type="limit",
        size=0.5,
        price=65000.0,
        pos_side="long",
        reduce_only=False,
        cl_ord_id="strat_001_1",
        td_mode="cross",
    )


def test_place_order_with_paper_client(paper_adapter, mock_paper_client):
    """Test placing an order via PaperExchangeClient."""
    mock_paper_client.place_order.return_value = {
        "ordId": "paper_999",
        "clOrdId": "paper_c1",
        "state": "filled",
    }

    spec = OrderSpec(
        symbol="BTC-USDT-SWAP",
        order_type=OrderType.MARKET,
        side=OrderSide.SELL,
        size=Decimal("1.0"),
        client_order_id="paper_c1",
        position_side=PositionSide.SHORT,
    )

    result = paper_adapter.place_order(spec)
    assert result["ordId"] == "paper_999"
    assert result["clOrdId"] == "paper_c1"


def test_cancel_order_okx_client(okx_adapter, mock_okx_client):
    """Test cancelling an order via OKXClient."""
    mock_okx_client.cancel_order.return_value = {"ord_id": "11223344"}
    res = okx_adapter.cancel_order("BTC-USDT-SWAP", "11223344")
    assert res is True
    mock_okx_client.cancel_order.assert_called_once_with(
        inst_id="BTC-USDT-SWAP",
        ord_id="11223344",
    )


# --- Open Orders & Reconciliation Tests ---

def test_get_open_orders_okx_client(okx_adapter, mock_okx_client):
    """Test get_open_orders with OKXClient calling get_pending_orders and normalizing."""
    mock_okx_client.get_pending_orders = MagicMock(return_value=[
        {
            "ordId": "ord_1",
            "clOrdId": "client_1",
            "instId": "BTC-USDT-SWAP",
            "side": "buy",
            "posSide": "long",
            "ordType": "limit",
            "sz": "0.1",
            "px": "60000",
            "state": "live",
        }
    ])
    del mock_okx_client.get_open_orders

    orders = okx_adapter.get_open_orders("BTC-USDT-SWAP")
    assert len(orders) == 1
    assert orders[0]["ordId"] == "ord_1"
    assert orders[0]["instId"] == "BTC-USDT-SWAP"
    mock_okx_client.get_pending_orders.assert_called_once_with(inst_id="BTC-USDT-SWAP")


# --- Positions Handling Tests ---

def test_get_positions_okx_client_pydantic_models(okx_adapter, mock_okx_client):
    """Test get_positions when client returns list of OKXPosition Pydantic models."""
    mock_okx_client.get_positions.return_value = [
        OKXPosition(
            inst_id="BTC-USDT-SWAP",
            pos_side="long",
            pos="0.5",
            avg_px="62000.0",
            mark_px="63500.0",
            last="63510.0",
            upl="750.0",
            upl_ratio="0.024",
            lever="10",
            margin="3100.0",
            liq_px="56000.0",
        )
    ]

    positions = okx_adapter.get_positions("BTC-USDT-SWAP")
    assert len(positions) == 1
    p = positions[0]

    assert isinstance(p, dict)
    assert p["instId"] == "BTC-USDT-SWAP"
    assert p["posSide"] == "long"
    assert p["pos"] == "0.5"
    assert p["avgPx"] == "62000.0"
    assert p["markPx"] == "63500.0"
    assert p["upl"] == "750.0"
    assert p["lever"] == 10
    assert p["margin"] == "3100.0"
    assert p["liqPx"] == "56000.0"


def test_get_positions_paper_client_dicts(paper_adapter, mock_paper_client):
    """Test get_positions when client returns list of raw dicts."""
    mock_paper_client.get_positions.return_value = [
        {
            "instId": "BTC-USDT-SWAP",
            "posSide": "short",
            "pos": "0.2",
            "avgPx": "64000.0",
            "markPx": "63000.0",
            "upl": "200.0",
            "lever": "5",
        }
    ]

    positions = paper_adapter.get_positions("BTC-USDT-SWAP")
    assert len(positions) == 1
    p = positions[0]
    assert isinstance(p, dict)
    assert p["instId"] == "BTC-USDT-SWAP"
    assert p["posSide"] == "short"
    assert p["pos"] == "0.2"
    assert p["upl"] == "200.0"


# --- Balance Handling Tests ---

def test_get_balance_okx_client_pydantic_models(okx_adapter, mock_okx_client):
    """Test get_balance when client returns list of OKXBalance Pydantic models."""
    mock_okx_client.get_balance.return_value = [
        OKXBalance(
            ccy="USDT",
            availBal="5000.0",
            cashBal="5000.0",
            eq="8500.0",
            eqUsd="8500.0",
            upl="500.0",
        ),
        OKXBalance(
            ccy="BTC",
            availBal="0.1",
            cashBal="0.1",
            eq="0.1",
            eqUsd="6500.0",
            upl="0.0",
        ),
    ]

    balance = okx_adapter.get_balance()
    assert isinstance(balance, dict)
    assert "totalEq" in balance
    assert "availBal" in balance
    assert "upl" in balance
    assert "details" in balance

    assert balance["totalEq"] == "15000.0"
    assert balance["availBal"] == "5000.1"
    assert balance["upl"] == "500.0"
    assert len(balance["details"]) == 2


def test_get_balance_paper_client_dict(paper_adapter, mock_paper_client):
    """Test get_balance when client returns normalized dict."""
    mock_paper_client.get_balance.return_value = {
        "totalEq": "10000.0",
        "availBal": "8000.0",
        "upl": "100.0",
        "details": [{"ccy": "USDT", "availBal": "8000.0", "eq": "10000.0"}],
    }

    balance = paper_adapter.get_balance()
    assert isinstance(balance, dict)
    assert balance["totalEq"] == "10000.0"
    assert balance["availBal"] == "8000.0"


# --- Leverage Setting Tests ---

def test_set_leverage(okx_adapter, mock_okx_client):
    """Test set_leverage passing mgn_mode and integer leverage."""
    mock_okx_client.set_leverage.return_value = {"lever": "10"}
    res = okx_adapter.set_leverage("BTC-USDT-SWAP", 10, mode=TradingMode.CROSS)

    assert res is True
    mock_okx_client.set_leverage.assert_called_once_with(
        inst_id="BTC-USDT-SWAP",
        lever=10,
        mgn_mode="cross",
    )
