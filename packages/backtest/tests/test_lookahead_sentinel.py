import unittest
import numpy as np
import pandas as pd
from backtest import indicators as ind


class TestLookaheadSentinel(unittest.TestCase):
    """Rigorous Sentinel Test: guarantees that no indicator leaks future data.

    Given data D and altered future data D' (where bars t > cut are changed),
    all indicator values for bars t <= cut MUST remain exactly identical.
    """

    def setUp(self):
        np.random.seed(42)
        self.n = 120
        self.cut = 60

        close = 100.0 + np.cumsum(np.random.randn(self.n))
        high = close + np.abs(np.random.randn(self.n)) * 2
        low = close - np.abs(np.random.randn(self.n)) * 2
        volume = np.random.uniform(10, 100, self.n)
        funding = np.random.normal(0.0001, 0.0002, self.n)
        oi = 10000.0 + np.cumsum(np.random.randn(self.n) * 50)

        self.df = pd.DataFrame({
            "open": close + np.random.randn(self.n) * 0.5,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "funding_rate": funding,
            "open_interest": oi,
        })

        # Future-corrupted DataFrame: bars after `cut` are heavily modified
        self.df_corrupted = self.df.copy()
        self.df_corrupted.loc[self.cut + 1 :, "close"] *= 5.0
        self.df_corrupted.loc[self.cut + 1 :, "high"] *= 6.0
        self.df_corrupted.loc[self.cut + 1 :, "low"] *= 0.2
        self.df_corrupted.loc[self.cut + 1 :, "volume"] *= 100.0
        self.df_corrupted.loc[self.cut + 1 :, "funding_rate"] = 0.05
        self.df_corrupted.loc[self.cut + 1 :, "open_interest"] *= 10.0

    def _assert_no_lookahead(self, s1: pd.Series, s2: pd.Series, name: str):
        # Slice up to cut
        val1 = s1.iloc[: self.cut].dropna()
        val2 = s2.iloc[: self.cut].dropna()
        self.assertEqual(len(val1), len(val2), f"Length mismatch in {name}")
        np.testing.assert_allclose(
            val1.to_numpy(),
            val2.to_numpy(),
            rtol=1e-7,
            atol=1e-7,
            err_msg=f"Lookahead leak detected in {name}!",
        )

    def test_atomic_operators_sentinel(self):
        # ts_rank
        r1 = ind.ts_rank(self.df["close"], window=14)
        r2 = ind.ts_rank(self.df_corrupted["close"], window=14)
        self._assert_no_lookahead(r1, r2, "ts_rank")

        # ts_corr
        c1 = ind.ts_corr(self.df["close"], self.df["volume"], window=20)
        c2 = ind.ts_corr(self.df_corrupted["close"], self.df_corrupted["volume"], window=20)
        self._assert_no_lookahead(c1, c2, "ts_corr")

        # ts_decay_linear
        d1 = ind.ts_decay_linear(self.df["close"], window=10)
        d2 = ind.ts_decay_linear(self.df_corrupted["close"], window=10)
        self._assert_no_lookahead(d1, d2, "ts_decay_linear")

        # ts_max & ts_min
        m1 = ind.ts_max(self.df["close"], window=15)
        m2 = ind.ts_max(self.df_corrupted["close"], window=15)
        self._assert_no_lookahead(m1, m2, "ts_max")

    def test_modern_indicators_sentinel(self):
        # SuperTrend
        st1 = ind.supertrend(self.df["high"], self.df["low"], self.df["close"], period=10, multiplier=3.0)
        st2 = ind.supertrend(self.df_corrupted["high"], self.df_corrupted["low"], self.df_corrupted["close"], period=10, multiplier=3.0)
        self._assert_no_lookahead(st1.supertrend, st2.supertrend, "supertrend.supertrend")
        self._assert_no_lookahead(st1.direction, st2.direction, "supertrend.direction")

        # Rolling VWAP
        v1 = ind.vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], window=20)
        v2 = ind.vwap(self.df_corrupted["high"], self.df_corrupted["low"], self.df_corrupted["close"], self.df_corrupted["volume"], window=20)
        self._assert_no_lookahead(v1, v2, "rolling_vwap")

        # Cumulative VWAP
        cv1 = ind.vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"])
        cv2 = ind.vwap(self.df_corrupted["high"], self.df_corrupted["low"], self.df_corrupted["close"], self.df_corrupted["volume"])
        self._assert_no_lookahead(cv1, cv2, "cumulative_vwap")

        # Keltner Channel
        kc1 = ind.keltner_channel(self.df["high"], self.df["low"], self.df["close"], ema_window=20, atr_window=10)
        kc2 = ind.keltner_channel(self.df_corrupted["high"], self.df_corrupted["low"], self.df_corrupted["close"], ema_window=20, atr_window=10)
        self._assert_no_lookahead(kc1.upper, kc2.upper, "keltner_channel.upper")
        self._assert_no_lookahead(kc1.lower, kc2.lower, "keltner_channel.lower")

        # Donchian Channel
        dc1 = ind.donchian_channel(self.df["high"], self.df["low"], window=20, shift=True)
        dc2 = ind.donchian_channel(self.df_corrupted["high"], self.df_corrupted["low"], window=20, shift=True)
        self._assert_no_lookahead(dc1.upper, dc2.upper, "donchian_channel.upper")
        self._assert_no_lookahead(dc1.lower, dc2.lower, "donchian_channel.lower")

        # Stoch RSI
        sr1 = ind.stoch_rsi(self.df["close"], rsi_window=14, stoch_window=14)
        sr2 = ind.stoch_rsi(self.df_corrupted["close"], rsi_window=14, stoch_window=14)
        self._assert_no_lookahead(sr1.k, sr2.k, "stoch_rsi.k")
        self._assert_no_lookahead(sr1.d, sr2.d, "stoch_rsi.d")

        # CMF
        cmf1 = ind.cmf(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], window=20)
        cmf2 = ind.cmf(self.df_corrupted["high"], self.df_corrupted["low"], self.df_corrupted["close"], self.df_corrupted["volume"], window=20)
        self._assert_no_lookahead(cmf1, cmf2, "cmf")

        # Bollinger Bands
        bb1 = ind.bollinger_bands(self.df["close"], window=20, num_std=2.0)
        bb2 = ind.bollinger_bands(self.df_corrupted["close"], window=20, num_std=2.0)
        self._assert_no_lookahead(bb1.upper, bb2.upper, "bollinger_bands.upper")
        self._assert_no_lookahead(bb1.bandwidth, bb2.bandwidth, "bollinger_bands.bandwidth")

    def test_derivative_factors_sentinel(self):
        # funding_rate_zscore
        fr1 = ind.funding_rate_zscore(self.df["funding_rate"], window=20)
        fr2 = ind.funding_rate_zscore(self.df_corrupted["funding_rate"], window=20)
        self._assert_no_lookahead(fr1, fr2, "funding_rate_zscore")

        # oi_momentum
        oi1 = ind.oi_momentum(self.df["open_interest"], window=10)
        oi2 = ind.oi_momentum(self.df_corrupted["open_interest"], window=10)
        self._assert_no_lookahead(oi1, oi2, "oi_momentum")


if __name__ == "__main__":
    unittest.main()
