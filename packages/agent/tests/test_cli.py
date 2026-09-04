"""Tests for pt-quant CLI tool (agent.cli)."""

import os
import tempfile
import pytest

from agent import cli


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "pt-quant" in captured.out
    assert "inspect-data" in captured.out
    assert "check" in captured.out
    assert "dry-run" in captured.out
    assert "indicators" in captured.out


def test_cli_inspect_data_offline(capsys, monkeypatch):
    monkeypatch.setenv("AGENT_BACKTEST_EXCHANGE", "okx")
    monkeypatch.setenv("AGENT_BACKTEST_SYMBOL", "ETH-USDT-SWAP")
    monkeypatch.setenv("AGENT_BACKTEST_INTERVAL", "1h")
    # If no real data cache connection, it falls back cleanly without crash
    ret = cli.main(["inspect-data"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "ETH-USDT-SWAP" in captured.out or "PT-QUANT" in captured.out


def test_cli_indicators_list(capsys):
    ret = cli.main(["indicators"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "sma" in captured.out
    assert "ema" in captured.out
    assert "rsi" in captured.out
    assert "atr" in captured.out


def test_cli_indicators_specific(capsys):
    ret = cli.main(["indicators", "rsi"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "rsi" in captured.out
    assert "Relative Strength Index" in captured.out or "window" in captured.out


def test_cli_check_valid_strategy(capsys):
    code = """import numpy as np
import pandas as pd
from backtest.indicators import ema

def generate_signals(data, params):
    close = data["close"]
    fast = ema(close, window=10)
    slow = ema(close, window=30)
    weights = np.where(fast > slow, 1.0, 0.0)
    reasons = np.full(len(data), "EMA Trend", dtype=object)
    return {"target_weights": weights.tolist(), "weight_reason": reasons.tolist()}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name

    try:
        ret = cli.main(["check", path])
        assert ret == 0
        captured = capsys.readouterr()
        assert "passed all static checks" in captured.out
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cli_check_lookahead_leak(capsys):
    code = """import numpy as np
import pandas as pd

def generate_signals(data, params):
    future_close = data["close"].shift(-1)
    weights = np.where(future_close > data["close"], 1.0, 0.0)
    return {"target_weights": weights.tolist(), "weight_reason": ["leak"] * len(data)}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name

    try:
        ret = cli.main(["check", path])
        assert ret == 1
        captured = capsys.readouterr()
        assert "Lookahead" in captured.out
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cli_dry_run_success(capsys):
    code = """import numpy as np
import pandas as pd

def generate_signals(data, params):
    weights = np.ones(len(data), dtype=float)
    reasons = np.full(len(data), "Long", dtype=object)
    return {"target_weights": weights.tolist(), "weight_reason": reasons.tolist()}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name

    try:
        ret = cli.main(["dry-run", path, "--bars", "50"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Dry-run succeeded" in captured.out
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cli_indicators_okx_source(capsys):
    ret = cli.main(["indicators", "--source", "okx"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "OKX AGENT TRADE KIT TECHNICAL INDICATORS" in captured.out
    assert "BTCRAINBOW" in captured.out
    assert "AHR999" in captured.out
