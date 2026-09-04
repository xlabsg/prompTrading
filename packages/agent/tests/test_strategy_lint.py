import unittest
from agent.strategy_lint import lint_and_heal_strategy_code, dry_run_strategy


class TestStrategyLintAndDryRun(unittest.TestCase):
    def test_lint_and_heal_missing_ta_and_weight_reason(self):
        buggy_code = """
import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    data['rsi'] = ta.rsi(data['close'], timeperiod=14)
    target_weights = np.zeros(len(data))
    weight_reason = [''] * len(data)
    long_signal = data['rsi'] < 30
    target_weights[long_signal] = 1.0
    weight_reason[long_signal] = 'long'
    return {
        'target_weights': target_weights,
        'weight_reason': weight_reason,
    }
"""
        healed, fixes = lint_and_heal_strategy_code(buggy_code)
        self.assertIn("import ta", healed)
        self.assertIn("np.full(len(data), '', dtype=object)", healed)
        self.assertEqual(len(fixes), 2)

        # Dry run should pass on healed code
        ok, err = dry_run_strategy(healed)
        self.assertTrue(ok, f"Dry-run failed: {err}")

    def test_dry_run_catches_runtime_error(self):
        broken_code = """
import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    1 / 0
    return {}
"""
        ok, err = dry_run_strategy(broken_code)
        self.assertFalse(ok)
        self.assertIn("ZeroDivisionError", err)

    def test_dry_run_catches_missing_target_weights(self):
        incomplete_code = """
import pandas as pd

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    return {"foo": "bar"}
"""
        ok, err = dry_run_strategy(incomplete_code)
        self.assertFalse(ok)
        self.assertIn("missing required key 'target_weights'", err)

    def test_dry_run_with_quant_indicators_and_crypto_factors(self):
        code = """
import numpy as np
import pandas as pd
from backtest.indicators import (
    supertrend,
    ts_corr,
    vwap,
    funding_rate_zscore,
    oi_momentum,
    donchian_channel,
)

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    st = supertrend(data["high"], data["low"], data["close"], period=10)
    pv_corr = ts_corr(data["close"], data["volume"], window=14)
    v_line = vwap(data["high"], data["low"], data["close"], data["volume"])
    fr_z = funding_rate_zscore(data["funding_rate"], window=20)
    oi_roc = oi_momentum(data["open_interest"], window=10)
    dc = donchian_channel(data["high"], data["low"], window=20, shift=True)

    long_cond = (st.direction == 1.0) & (data["close"] > v_line) & (fr_z < 1.5)
    short_cond = (st.direction == -1.0) & (data["close"] < v_line) & (fr_z > -1.5)

    target_weights = np.zeros(len(data), dtype=float)
    weight_reason = np.full(len(data), "Cash", dtype=object)

    target_weights[long_cond] = 1.0
    weight_reason[long_cond] = "Bullish Trend"

    target_weights[short_cond] = -1.0
    weight_reason[short_cond] = "Bearish Trend"

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason.tolist(),
    }
"""
        ok, err = dry_run_strategy(code)
        self.assertTrue(ok, f"Dry-run failed: {err}")

    def test_dry_run_catches_lookahead_bias_shift(self):
        peeking_code = """
import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    data['future_close'] = data['close'].shift(-1)
    target_weights = np.where(data['future_close'] > data['close'], 1.0, 0.0)
    return {
        'target_weights': target_weights,
        'weight_reason': [''] * len(data),
    }
"""
        ok, err = dry_run_strategy(peeking_code, strict_lookahead=True)
        self.assertFalse(ok)
        self.assertIn("LookaheadBiasError", err)
        self.assertIn("Negative shift", err)

    def test_dry_run_catches_centered_rolling(self):
        centered_code = """
import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    data['sma'] = data['close'].rolling(10, center=True).mean()
    target_weights = np.where(data['close'] > data['sma'], 1.0, 0.0)
    return {
        'target_weights': target_weights,
        'weight_reason': [''] * len(data),
    }
"""
        ok, err = dry_run_strategy(centered_code, strict_lookahead=True)
        self.assertFalse(ok)
        self.assertIn("LookaheadBiasError", err)
        self.assertIn("Rolling with center=True", err)

    def test_lint_and_heal_alpha_library(self):
        code = """
import pandas as pd

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    st = calc_supertrend(data, period=10, multiplier=3.0)
    target_weights = st['trend_direction']
    return {
        'target_weights': target_weights,
        'weight_reason': ['supertrend'] * len(data),
    }
"""
        healed, fixes = lint_and_heal_strategy_code(code)
        self.assertIn("from backtest.alpha_library import calc_supertrend", healed)
        ok, err = dry_run_strategy(healed)
        self.assertTrue(ok, f"Dry run failed: {err}")


if __name__ == "__main__":
    unittest.main()
