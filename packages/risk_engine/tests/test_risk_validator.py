"""Tests for RiskValidator"""
import pytest
from decimal import Decimal
from trading_sdk import (
    RiskValidator, RiskConfig, OrderSpec, Position, Balance,
    OrderSide, OrderType, PositionSide, PositionStatus
)


@pytest.fixture
def risk_config():
    """Create a test risk configuration"""
    return RiskConfig(
        max_position_pct=100.0,
        max_leverage=10,
        stop_loss_pct=0.02,
        max_daily_loss_pct=5.0,
        max_drawdown_pct=10.0,
        require_stop_loss=True,
        min_order_size=0.01,
        max_order_size=10.0,
    )


@pytest.fixture
def risk_validator(risk_config):
    """Create a RiskValidator instance"""
    return RiskValidator(risk_config)


@pytest.fixture
def sample_balance():
    """Create a sample balance"""
    return Balance(
        total_equity=Decimal("10000"),
        available_balance=Decimal("5000"),
        margin_used=Decimal("5000"),
        unrealized_pnl=Decimal("0"),
    )


@pytest.fixture
def sample_order_spec():
    """Create a sample order spec"""
    return OrderSpec(
        symbol="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.1"),
        price=Decimal("50000"),
        position_side=PositionSide.LONG,
        stop_loss=Decimal("49000"),
        take_profit=Decimal("51000"),
    )


def test_validate_order_success(risk_validator, sample_order_spec, sample_balance):
    """Test successful order validation"""
    result = risk_validator.validate_order(
        order_spec=sample_order_spec,
        current_positions=[],
        balance=sample_balance,
    )

    assert result.approved is True
    assert len(result.violations) == 0


def test_validate_order_missing_stop_loss(risk_validator, sample_balance):
    """Test order rejection when stop loss is missing"""
    order_spec = OrderSpec(
        symbol="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.1"),
        price=Decimal("50000"),
        position_side=PositionSide.LONG,
    )

    result = risk_validator.validate_order(
        order_spec=order_spec,
        current_positions=[],
        balance=sample_balance,
    )

    assert result.approved is False
    assert any("stop loss" in v.lower() for v in result.violations)


def test_validate_order_insufficient_balance(risk_validator, sample_order_spec):
    """Test order rejection when balance is insufficient"""
    poor_balance = Balance(
        total_equity=Decimal("100"),
        available_balance=Decimal("50"),
        margin_used=Decimal("50"),
        unrealized_pnl=Decimal("0"),
    )

    result = risk_validator.validate_order(
        order_spec=sample_order_spec,
        current_positions=[],
        balance=poor_balance,
    )

    assert result.approved is False
    assert any("balance" in v.lower() for v in result.violations)


def test_validate_order_size_limits(risk_validator, sample_balance):
    """Test order size validation"""
    # Too small
    small_order = OrderSpec(
        symbol="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.001"),
        price=Decimal("50000"),
        position_side=PositionSide.LONG,
        stop_loss=Decimal("49000"),
    )

    result = risk_validator.validate_order(
        order_spec=small_order,
        current_positions=[],
        balance=sample_balance,
    )

    assert result.approved is False

    # Too large
    large_order = OrderSpec(
        symbol="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("20"),
        price=Decimal("50000"),
        position_side=PositionSide.LONG,
        stop_loss=Decimal("49000"),
    )

    result = risk_validator.validate_order(
        order_spec=large_order,
        current_positions=[],
        balance=sample_balance,
    )

    assert result.approved is False


def test_daily_loss_tracking(risk_validator, sample_order_spec, sample_balance):
    """Test daily loss tracking"""
    # Set initial equity
    risk_validator.daily_pnl_start = Decimal("10000")

    # Simulate a large loss
    loss_balance = Balance(
        total_equity=Decimal("9000"),  # 10% loss
        available_balance=Decimal("4000"),
        margin_used=Decimal("5000"),
        unrealized_pnl=Decimal("-1000"),
    )

    result = risk_validator.validate_order(
        order_spec=sample_order_spec,
        current_positions=[],
        balance=loss_balance,
    )

    assert result.approved is False
    assert any("daily loss" in v.lower() for v in result.violations)


def test_max_drawdown_tracking(risk_validator, sample_order_spec, sample_balance):
    """Test max drawdown tracking"""
    # Set peak equity
    risk_validator.peak_equity = Decimal("10000")

    # Current equity is 11% lower
    drawdown_balance = Balance(
        total_equity=Decimal("8900"),
        available_balance=Decimal("4000"),
        margin_used=Decimal("4900"),
        unrealized_pnl=Decimal("-1100"),
    )

    result = risk_validator.validate_order(
        order_spec=sample_order_spec,
        current_positions=[],
        balance=drawdown_balance,
    )

    assert result.approved is False
    assert any("drawdown" in v.lower() for v in result.violations)


def test_reset_daily_stats(risk_validator):
    """Test resetting daily statistics"""
    risk_validator.daily_pnl_start = Decimal("10000")
    risk_validator.daily_pnl_current = Decimal("-500")

    risk_validator.reset_daily_stats()

    assert risk_validator.daily_pnl_start is None
    assert risk_validator.daily_pnl_current == Decimal("0")
