"""Tests for StopLoss strategies"""
import pytest
from decimal import Decimal
from trading_sdk import (
    TrailingStopLoss, FixedStopLoss, StopLossManager,
    TrailingStopConfig, ActivationConfig, DistanceConfig,
    ActivationType, DistanceType,
    Position, PositionSide, PositionStatus
)


@pytest.fixture
def trailing_config():
    """Create trailing stop configuration"""
    return TrailingStopConfig(
        enabled=True,
        activation=ActivationConfig(
            type=ActivationType.PROFIT_PCT,
            threshold=0.01  # 1% profit
        ),
        distance=DistanceConfig(
            type=DistanceType.PERCENTAGE,
            value=0.008  # 0.8%
        )
    )


@pytest.fixture
def sample_long_position():
    """Create a sample long position"""
    return Position(
        symbol="BTC-USDT-SWAP",
        side=PositionSide.LONG,
        size=Decimal("1.0"),
        entry_price=Decimal("50000"),
        current_price=Decimal("50000"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        leverage=5,
        margin=Decimal("10000"),
        stop_loss=Decimal("49000"),
        status=PositionStatus.OPEN,
    )


def test_fixed_stop_loss_trigger(sample_long_position):
    """Test fixed stop loss triggering"""
    strategy = FixedStopLoss()

    # Price above stop loss - should not trigger
    assert not strategy.should_trigger(sample_long_position, Decimal("50000"))

    # Price at stop loss - should trigger
    assert strategy.should_trigger(sample_long_position, Decimal("49000"))

    # Price below stop loss - should trigger
    assert strategy.should_trigger(sample_long_position, Decimal("48900"))


def test_trailing_stop_activation(trailing_config, sample_long_position):
    """Test trailing stop activation"""
    strategy = TrailingStopLoss(trailing_config)

    # Initial state - not activated
    assert not strategy.activated

    # Price moves up 0.5% - should not activate (threshold is 1%)
    strategy.update(sample_long_position, Decimal("50250"))
    assert not strategy.activated

    # Price moves up 1.5% - should activate
    strategy.update(sample_long_position, Decimal("50750"))
    assert strategy.activated
    assert strategy.trail_stop_price is not None


def test_trailing_stop_updates(trailing_config, sample_long_position):
    """Test trailing stop price updates"""
    strategy = TrailingStopLoss(trailing_config)

    # Activate at 51000 (2% profit)
    strategy.update(sample_long_position, Decimal("51000"))
    assert strategy.activated

    initial_stop = strategy.trail_stop_price

    # Price continues to rise
    strategy.update(sample_long_position, Decimal("52000"))

    # Stop should move up
    assert strategy.trail_stop_price > initial_stop

    # Price drops slightly
    strategy.update(sample_long_position, Decimal("51500"))

    # Stop should not move down
    assert strategy.trail_stop_price >= initial_stop


def test_trailing_stop_trigger(trailing_config, sample_long_position):
    """Test trailing stop triggering"""
    strategy = TrailingStopLoss(trailing_config)

    # Activate
    strategy.update(sample_long_position, Decimal("51000"))
    assert strategy.activated

    stop_price = strategy.trail_stop_price

    # Price above stop - should not trigger
    assert not strategy.should_trigger(sample_long_position, Decimal("51000"))

    # Price hits stop - should trigger
    assert strategy.should_trigger(sample_long_position, stop_price)


def test_stop_loss_manager():
    """Test StopLossManager"""
    manager = StopLossManager()

    # Register a position
    config = TrailingStopConfig(enabled=True)
    position = Position(
        symbol="BTC-USDT-SWAP",
        side=PositionSide.LONG,
        size=Decimal("1.0"),
        entry_price=Decimal("50000"),
        current_price=Decimal("50000"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        leverage=5,
        margin=Decimal("10000"),
        stop_loss=Decimal("49000"),
        status=PositionStatus.OPEN,
    )

    manager.register_position("pos1", position, config)

    # Update and check
    manager.update("pos1", position, Decimal("51000"))
    assert not manager.should_trigger("pos1", position, Decimal("51000"))

    # Remove
    manager.remove_position("pos1")
    assert "pos1" not in manager.strategies


def test_trailing_stop_state_persistence(trailing_config, sample_long_position):
    """Test state persistence"""
    strategy = TrailingStopLoss(trailing_config)

    # Activate and update
    strategy.update(sample_long_position, Decimal("51000"))
    strategy.update(sample_long_position, Decimal("52000"))

    # Get state
    state = strategy.get_state()

    # Create new strategy and restore
    new_strategy = TrailingStopLoss(trailing_config)
    new_strategy.restore_state(state)

    # Verify state
    assert new_strategy.activated == strategy.activated
    assert new_strategy.trail_stop_price == strategy.trail_stop_price
