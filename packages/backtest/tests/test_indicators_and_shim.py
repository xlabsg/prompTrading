import unittest
import numpy as np
import pandas as pd
from backtest import indicators as ind
import ta


class TestIndicatorsAndShim(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 50
        self.df = pd.DataFrame({
            "close": np.cumsum(np.random.randn(n)) + 100,
            "high": np.cumsum(np.random.randn(n)) + 105,
            "low": np.cumsum(np.random.randn(n)) + 95,
            "volume": np.random.rand(n) * 100,
        })

    def test_indicator_aliases(self):
        rsi1 = ind.rsi(self.df["close"], window=14)
        rsi2 = ind.rsi(self.df["close"], timeperiod=14)
        rsi3 = ind.rsi(self.df["close"], length=14)
        pd.testing.assert_series_equal(rsi1, rsi2)
        pd.testing.assert_series_equal(rsi1, rsi3)

    def test_ta_shim(self):
        rsi_val = ta.rsi(self.df["close"], timeperiod=14)
        self.assertIsInstance(rsi_val, pd.Series)
        self.assertEqual(len(rsi_val), len(self.df))

        adx_val = ta.adx(self.df["high"], self.df["low"], self.df["close"], timeperiod=14)
        self.assertIsInstance(adx_val, pd.Series)
        self.assertIsInstance(adx_val["ADX"], pd.Series)

        up, mid, low = ta.bbands(self.df["close"], timeperiod=20, nbdevup=2, nbdevdn=2)
        self.assertEqual(len(up), len(self.df))
        self.assertEqual(len(mid), len(self.df))
        self.assertEqual(len(low), len(self.df))


if __name__ == "__main__":
    unittest.main()
