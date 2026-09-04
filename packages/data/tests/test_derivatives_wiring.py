import unittest
import pandas as pd
from data.derivatives import (
    align_derivatives_onto_ohlcv,
    _normalize_binance_symbol,
    _normalize_okx_inst_id,
    _extract_base_ccy,
)


class TestDerivativesWiring(unittest.TestCase):
    def test_symbol_helpers(self):
        self.assertEqual(_normalize_binance_symbol("BTC-USDT"), "BTCUSDT")
        self.assertEqual(_normalize_binance_symbol("eth/usdt"), "ETHUSDT")

        self.assertEqual(_normalize_okx_inst_id("BTC-USDT"), "BTC-USDT-SWAP")
        self.assertEqual(_normalize_okx_inst_id("ETH-USDT-SWAP"), "ETH-USDT-SWAP")

        self.assertEqual(_extract_base_ccy("BTC-USDT-SWAP"), "BTC")
        self.assertEqual(_extract_base_ccy("ETHUSDT"), "ETH")

    def test_align_derivatives_zero_lookahead(self):
        # Bar timestamps: 100, 200, 300, 400
        ohlcv = pd.DataFrame({
            "timestamp": [100, 200, 300, 400],
            "open": [10.0, 11.0, 12.0, 13.0],
            "high": [11.0, 12.0, 13.0, 14.0],
            "low": [9.0, 10.0, 11.0, 12.0],
            "close": [10.5, 11.5, 12.5, 13.5],
            "volume": [100.0, 120.0, 110.0, 130.0],
        })

        # Funding rate settled at timestamp 150 and 350
        fr_df = pd.DataFrame({
            "timestamp": [150, 350],
            "funding_rate": [0.0001, 0.0005],
        })

        # Open interest recorded at timestamp 50 and 250
        oi_df = pd.DataFrame({
            "timestamp": [50, 250],
            "open_interest": [1000.0, 2000.0],
        })

        aligned = align_derivatives_onto_ohlcv(ohlcv, funding_df=fr_df, oi_df=oi_df)
        self.assertIn("funding_rate", aligned.columns)
        self.assertIn("open_interest", aligned.columns)

        # Bar 100 (<= 150): fr should be 0.0001 (bfill from first known), OI at 100 is 1000.0 (from 50)
        self.assertEqual(aligned.loc[aligned["timestamp"] == 100, "open_interest"].iloc[0], 1000.0)

        # Bar 200 (>= 150, < 350): fr must be 0.0001 (NOT 0.0005)
        self.assertEqual(aligned.loc[aligned["timestamp"] == 200, "funding_rate"].iloc[0], 0.0001)

        # Bar 300 (>= 250): OI must be 2000.0
        self.assertEqual(aligned.loc[aligned["timestamp"] == 300, "open_interest"].iloc[0], 2000.0)

        # Bar 400 (>= 350): fr must be 0.0005
        self.assertEqual(aligned.loc[aligned["timestamp"] == 400, "funding_rate"].iloc[0], 0.0005)


if __name__ == "__main__":
    unittest.main()
