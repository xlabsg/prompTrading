import unittest
import numpy as np
import pandas as pd
from backtest.vectorized import BacktestConfig, run_backtest
from backtest.indicators import supertrend, vwap, funding_rate_zscore, oi_momentum


class TestVectorizedStrategyWithDerivatives(unittest.TestCase):
    """End-to-end test of the vectorized backtesting engine with derivative factors."""

    def setUp(self):
        np.random.seed(42)
        n = 200
        timestamps = [1700000000000 + i * 3600000 for i in range(n)]

        # Simulated trending and fluctuating price series
        returns = np.random.randn(n) * 0.01 + 0.001
        close = 50000.0 * np.exp(np.cumsum(returns))
        high = close * (1 + np.abs(np.random.randn(n) * 0.005))
        low = close * (1 - np.abs(np.random.randn(n) * 0.005))
        open_p = close * (1 + np.random.randn(n) * 0.002)
        volume = np.random.uniform(100, 1000, n)
        funding = np.random.normal(0.0001, 0.0002, n)
        oi = 100000.0 + np.cumsum(np.random.randn(n) * 500)

        self.df = pd.DataFrame({
            "timestamp": timestamps,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "funding_rate": funding,
            "open_interest": oi,
        })

    def test_e2e_vectorized_multi_factor_strategy(self):
        # 1. Compute multi-factor signals
        st = supertrend(self.df["high"], self.df["low"], self.df["close"], period=10)
        v = vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], window=24)
        fr_z = funding_rate_zscore(self.df["funding_rate"], window=48)
        oi_roc = oi_momentum(self.df["open_interest"], window=12)

        # Signal rules:
        # Long: Bullish supertrend + price above VWAP + funding rate not overcrowded (< 1.5)
        long_mask = (st.direction == 1.0) & (self.df["close"] > v) & (fr_z < 1.5)
        # Short: Bearish supertrend + price below VWAP + funding rate not negative squeeze (> -1.5)
        short_mask = (st.direction == -1.0) & (self.df["close"] < v) & (fr_z > -1.5)

        target_weights = np.zeros(len(self.df), dtype=float)
        target_weights[long_mask] = 1.0
        target_weights[short_mask] = -1.0

        signals = {
            "target_weights": target_weights.tolist(),
            "weight_reason": np.full(len(self.df), "", dtype=object).tolist(),
        }

        # 2. Run vectorized backtest
        config = BacktestConfig(initial_cash=10000.0, fee_rate=0.0004, slippage_bps=1.0)
        result = run_backtest(self.df, signals=signals, interval="1h", config=config)

        # 3. Assertions
        self.assertEqual(len(result.equity), len(self.df))
        self.assertEqual(len(result.positions), len(self.df))
        self.assertIn("sharpe_ratio", result.metrics)
        self.assertIn("max_drawdown", result.metrics)
        self.assertIn("total_return", result.metrics)
        self.assertIn("win_rate", result.metrics)

        # Equity must be finite positive numbers
        self.assertTrue((result.equity["equity"].to_numpy() > 0).all())
        self.assertFalse(np.isnan(result.metrics["sharpe_ratio"]))
        self.assertFalse(np.isnan(result.metrics["max_drawdown"]))


if __name__ == "__main__":
    unittest.main()
