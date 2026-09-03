import numpy as np
import pandas as pd
import pytest

from backtest.vectorized import BacktestConfig, run_backtest


def _sample_ohlcv(n: int = 100) -> pd.DataFrame:
    timestamps = [1700000000000 + i * 3600000 for i in range(n)]
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(n, 1000.0),
        }
    )


def test_sharpe_ratio_zero_when_cash():
    data = _sample_ohlcv(100)
    signals = {"target_weights": [0.0] * len(data)}
    res = run_backtest(data, signals=signals, interval="1h")

    assert res.metrics["total_return"] == 0.0
    assert res.metrics["sharpe_ratio"] == 0.0
    assert res.metrics["sortino_ratio"] == 0.0


def test_sharpe_ratio_positive_when_long_trend():
    data = _sample_ohlcv(100)
    signals = {"target_weights": [1.0] * len(data)}
    res = run_backtest(
        data,
        signals=signals,
        interval="1h",
        config=BacktestConfig(fee_rate=0.0, slippage_bps=0.0),
    )

    assert res.metrics["total_return"] > 50.0
    assert res.metrics["sharpe_ratio"] > 0.0
    assert "sortino_ratio" in res.metrics


def test_unclosed_final_trade_recorded():
    data = _sample_ohlcv(50)
    w = [0.0] * 10 + [1.0] * 40
    signals = {"target_weights": w}
    res = run_backtest(data, signals=signals, interval="1h")

    assert len(res.trades) == 1
    trade = res.trades.iloc[0]
    assert trade["entry_i"] == 10
    assert trade["exit_i"] == 49
    assert trade["pnl"] > 0
    assert res.metrics["total_trades"] == 1
    assert res.metrics["win_rate"] == 100.0
