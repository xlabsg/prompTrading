import pytest
from live_trading_sdk.paper_broker import PaperBroker
from live_trading_sdk.strategy import Broker


def test_paper_broker_satisfies_protocol():
    broker = PaperBroker()
    assert isinstance(broker, Broker)


def test_paper_broker_order_execution_and_slippage():
    broker = PaperBroker(initial_cash=10_000.0, fee_rate=0.0004, slippage_bps=2.0)
    broker.update_price(100.0)

    # Buy 10 units at price 100. Slippage = 100 * (1 + 0.0002) = 100.02
    broker.market_order("buy", 10.0, reason="test_entry")
    assert broker.current_position() == 10.0
    assert len(broker.trades) == 1
    assert broker.trades[0].price == pytest.approx(100.02)
    assert broker.trades[0].fee == pytest.approx(10.0 * 100.02 * 0.0004)

    # Price moves to 110.0
    broker.update_price(110.0)
    assert broker.unrealized_pnl() == pytest.approx(10.0 * (110.0 - 100.02))

    # Close position (sell 10 units)
    # Sell slippage: 110 * (1 - 0.0002) = 109.978
    broker.market_order("sell", 10.0, reason="test_exit")
    assert broker.current_position() == 0.0
    assert len(broker.trades) == 2
    assert broker.trades[1].realized_pnl > 0


def test_paper_broker_set_target_allocation():
    broker = PaperBroker(initial_cash=10_000.0)
    broker.update_price(50.0)

    # Target 50% allocation ($5,000 / 50 = 100 units)
    broker.set_target_allocation(0.5, reason="rebalance_50")
    assert broker.current_position() > 95.0
    assert broker.current_position() < 105.0

    # Target flat (0%)
    broker.set_target_allocation(0.0, reason="close_all")
    assert broker.current_position() == 0.0
