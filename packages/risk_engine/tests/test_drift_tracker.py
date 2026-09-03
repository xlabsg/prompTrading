import pytest
from risk_engine.monitoring.drift_tracker import BacktestExpectation, DriftTracker


def test_drift_tracker_normal_performance():
    exp = BacktestExpectation(
        expected_sharpe=2.0,
        max_drawdown=0.10,
        win_rate=0.55,
        daily_mean_return=0.002,
        daily_volatility=0.01,
    )
    tracker = DriftTracker(exp)
    tracker.reset(10_000.0)

    # Perform near expectation
    tracker.record_step_return(0.002)
    tracker.record_step_return(0.003)
    status = tracker.update_equity(10_050.0)

    assert not status.is_drifting
    assert status.drift_severity == "normal"
    assert status.alert_message is None


def test_drift_tracker_detects_severe_drawdown_drift():
    exp = BacktestExpectation(
        expected_sharpe=1.5,
        max_drawdown=0.08,  # 8% backtest max drawdown
        win_rate=0.50,
        daily_mean_return=0.001,
        daily_volatility=0.015,
    )
    tracker = DriftTracker(exp, drawdown_tolerance_mult=1.2)
    tracker.reset(10_000.0)

    # Drops by 20% (drawdown = 0.20, exceeds 8% * 1.2 = 9.6%)
    for _ in range(5):
        tracker.record_step_return(-0.04)

    status = tracker.update_equity(8_000.0)
    assert status.is_drifting
    assert status.drift_severity in ("moderate", "critical")
    assert status.alert_message is not None
    assert "drawdown" in status.alert_message
