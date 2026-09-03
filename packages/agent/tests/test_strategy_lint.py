import unittest
import numpy as np
import pandas as pd
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


if __name__ == "__main__":
    unittest.main()
