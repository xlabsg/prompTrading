import unittest
import numpy as np
import pandas as pd
from backtest import indicators as ind
import ta


class TestIndicatorsExtended(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 100
        close = 100.0 + np.cumsum(np.random.randn(n))
        high = close + np.abs(np.random.randn(n)) * 2
        low = close - np.abs(np.random.randn(n)) * 2
        open_p = close + np.random.randn(n) * 0.5
        volume = np.random.uniform(50, 500, n)
        funding_rate = np.random.normal(0.0001, 0.0002, n)
        open_interest = 10000.0 + np.cumsum(np.random.randn(n) * 100)

        self.df = pd.DataFrame({
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "funding_rate": funding_rate,
            "open_interest": open_interest,
        })

    def test_atomic_operators(self):
        # ts_rank
        rank = ind.ts_rank(self.df["close"], window=14)
        self.assertIsInstance(rank, pd.Series)
        valid_rank = rank.dropna()
        self.assertTrue((valid_rank >= 0.0).all())
        self.assertTrue((valid_rank <= 1.0).all())

        # ts_corr
        corr = ind.ts_corr(self.df["close"], self.df["volume"], window=20)
        self.assertIsInstance(corr, pd.Series)
        valid_corr = corr.dropna()
        self.assertTrue((valid_corr >= -1.0001).all())
        self.assertTrue((valid_corr <= 1.0001).all())

        # ts_cov
        cov = ind.ts_cov(self.df["close"], self.df["volume"], window=20)
        self.assertIsInstance(cov, pd.Series)

        # ts_decay_linear
        decay = ind.ts_decay_linear(self.df["close"], window=10)
        self.assertIsInstance(decay, pd.Series)
        self.assertEqual(len(decay), len(self.df))

        # ts_max & ts_min
        t_max = ind.ts_max(self.df["close"], window=10)
        t_min = ind.ts_min(self.df["close"], window=10)
        self.assertTrue((t_max.dropna() >= t_min.dropna()).all())

        # safe_div
        div = ind.safe_div(self.df["close"], pd.Series([0.0] * len(self.df)), fill=99.0)
        self.assertTrue((div == 99.0).all())

    def test_modern_indicators(self):
        # Supertrend
        st_res = ind.supertrend(self.df["high"], self.df["low"], self.df["close"], period=10, multiplier=3.0)
        self.assertIsInstance(st_res.supertrend, pd.Series)
        self.assertIsInstance(st_res.direction, pd.Series)
        valid_dirs = st_res.direction.dropna().unique()
        self.assertTrue(set(valid_dirs).issubset({-1.0, 1.0}))

        # VWAP (cumulative & rolling)
        cum_vwap = ind.vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"])
        self.assertIsInstance(cum_vwap, pd.Series)
        self.assertEqual(len(cum_vwap), len(self.df))

        roll_vwap = ind.vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], window=20)
        self.assertIsInstance(roll_vwap, pd.Series)

        # Keltner Channel
        kc = ind.keltner_channel(self.df["high"], self.df["low"], self.df["close"], ema_window=20, atr_window=10)
        self.assertTrue((kc.upper.dropna() >= kc.middle.dropna()).all())
        self.assertTrue((kc.middle.dropna() >= kc.lower.dropna()).all())

        # Donchian Channel
        dc = ind.donchian_channel(self.df["high"], self.df["low"], window=20, shift=True)
        self.assertTrue((dc.upper.dropna() >= dc.middle.dropna()).all())
        self.assertTrue((dc.middle.dropna() >= dc.lower.dropna()).all())

        # Stoch RSI
        srsi = ind.stoch_rsi(self.df["close"], rsi_window=14, stoch_window=14)
        self.assertIsInstance(srsi.k, pd.Series)
        self.assertIsInstance(srsi.d, pd.Series)

        # CMF
        cmf_val = ind.cmf(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], window=20)
        self.assertIsInstance(cmf_val, pd.Series)

        # Bollinger Bands
        bb = ind.bollinger_bands(self.df["close"], window=20, num_std=2.0)
        self.assertTrue((bb.upper.dropna() >= bb.middle.dropna()).all())
        self.assertTrue((bb.middle.dropna() >= bb.lower.dropna()).all())
        self.assertIsInstance(bb.bandwidth, pd.Series)
        self.assertIsInstance(bb.percent_b, pd.Series)

    def test_crypto_factors(self):
        # funding_rate_zscore
        fr_z = ind.funding_rate_zscore(self.df["funding_rate"], window=20)
        self.assertIsInstance(fr_z, pd.Series)

        # oi_momentum
        oi_mom = ind.oi_momentum(self.df["open_interest"], window=10)
        self.assertIsInstance(oi_mom, pd.Series)

    def test_ta_compatibility_layer(self):
        # Check that ta exposes the new functions seamlessly
        st = ta.supertrend(self.df["high"], self.df["low"], self.df["close"])
        self.assertIsInstance(st.supertrend, pd.Series)

        vw = ta.vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"])
        self.assertIsInstance(vw, pd.Series)

        corr = ta.ts_corr(self.df["close"], self.df["volume"], window=10)
        self.assertIsInstance(corr, pd.Series)


if __name__ == "__main__":
    unittest.main()
