from __future__ import annotations

import ast
import json
import tempfile
import traceback
import subprocess
import sys
import os
import uuid
from typing import Any

import numpy as np
import pandas as pd

from agent.llm_openai_compat import ChatCompletionRequest, ChatMessage, chat_completion
from agent.middleware import LLMMiddleware
from backtest.load_strategy import load_callable_from_file
from backtest.protocol import normalize_signals
from backtest.vectorized import BacktestConfig, run_backtest


_BANNED_IMPORTS = {"os", "sys", "subprocess", "socket", "pathlib", "requests", "urllib", "http", "shutil"}
_BANNED_CALLS = {"open", "exec", "eval", "__import__"}


def _static_safety_check(code: str) -> None:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = (alias.name or "").split(".", 1)[0]
                if name in _BANNED_IMPORTS:
                    raise ValueError(f"banned_import:{name}")
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _BANNED_CALLS:
                raise ValueError(f"banned_call:{fn.id}")


def run_static_checks(code: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": None,
        "traceback": "",
        "warnings": [],
    }
    try:
        ast.parse(code)
        if "def generate_signals" not in code:
            raise ValueError("missing_generate_signals")
        _static_safety_check(code)
        payload["ok"] = True
        return payload
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc()
        return payload


def _synth_df(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rets = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.002, size=n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.002, size=n))
    volume = rng.uniform(1.0, 100.0, size=n)
    ts0 = 1700000000000
    ts = ts0 + np.arange(n, dtype=np.int64) * 3600_000
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _debug_series_count(signals: dict[str, Any]) -> int:
    required = {"target_weights", "weight_reason"}
    return len([k for k in signals.keys() if k not in required])


def run_smoke_validation(
    code: str,
    *,
    n_bars: int = 200,
    interval: str = "1h",
    signal_mode: str = "target_weights",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": None,
        "traceback": "",
        "warnings": [],
    }

    try:
        ast.parse(code)
        if "def generate_signals" not in code:
            raise ValueError("missing_generate_signals")
        _static_safety_check(code)

        with tempfile.TemporaryDirectory(prefix="agent-smoke-") as td:
            strategy_path = f"{td}/strategy.py"
            harness_path = f"{td}/harness.py"
            with open(strategy_path, "w", encoding="utf-8") as f:
                f.write(code.strip() + "\n")

            harness = f"""
import json
import traceback
import numpy as np
import pandas as pd

from backtest.load_strategy import load_callable_from_file
from backtest.protocol import normalize_signals
from backtest.vectorized import BacktestConfig, run_backtest
from backtest.network_guard import install_network_guard


def _synth_df(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rets = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.002, size=n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.002, size=n))
    volume = rng.uniform(1.0, 100.0, size=n)
    ts0 = 1700000000000
    ts = ts0 + np.arange(n, dtype=np.int64) * 3600_000
    return pd.DataFrame({{
        "timestamp": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }})


def _debug_series_count(signals: dict) -> int:
    required = {{"target_weights", "weight_reason"}}
    return len([k for k in signals.keys() if k not in required])


def main() -> int:
    try:
        install_network_guard(allowlist=[], enabled=True)
        fn = load_callable_from_file({strategy_path!r}, "generate_signals")
        data = _synth_df(int({int(n_bars)}))
        out = fn(data.copy(), {{}})
        if not isinstance(out, dict):
            raise RuntimeError("signals_not_dict")
        # Count debug fields BEFORE normalization (which strips them to only required fields)
        debug_count = _debug_series_count(out)
        if debug_count < 2 or debug_count > 6:
            raise RuntimeError("debug_series_count_invalid")
        signals = normalize_signals(out, n=len(data), mode={signal_mode!r})
        result = run_backtest(
            data,
            signals=signals,
            interval={interval!r},
            config=BacktestConfig(),
        )
        print(json.dumps({{"ok": True, "metrics": result.metrics}}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({{"ok": False, "error": str(exc), "traceback": traceback.format_exc()}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
"""
            with open(harness_path, "w", encoding="utf-8") as f:
                f.write(harness.strip() + "\n")

            env = os.environ.copy()
            env["NETWORK_GUARD_ENABLED"] = "1"
            env["NETWORK_ALLOWLIST"] = ""
            proc = subprocess.run(
                [sys.executable, harness_path],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            try:
                result = json.loads(stdout.splitlines()[-1]) if stdout else {"ok": False, "error": "no_output"}
            except Exception:
                result = {"ok": False, "error": "invalid_json_output", "stdout": stdout, "stderr": stderr}
            if not result.get("ok"):
                payload["error"] = result.get("error") or "smoke_failed"
                payload["traceback"] = result.get("traceback") or stderr
                return payload

            payload["ok"] = True
            payload["metrics"] = result.get("metrics") or {}
            return payload
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc()
        return payload


def summarize_validation(validation: dict[str, Any]) -> dict[str, Any]:
    error = str(validation.get("error") or "").strip()
    category = "unknown"
    suggestion = "Inspect the traceback and fix the reported issue."

    if error.startswith("missing_generate_signals"):
        category = "missing_entrypoint"
        suggestion = "Ensure strategy.py defines generate_signals(data, params)."
    elif error.startswith("signals_not_dict"):
        category = "signals_schema"
        suggestion = "Return a dict with target_weights and weight_reason fields."
    elif error.startswith("signals_missing_target_weights"):
        category = "signals_schema"
        suggestion = "Return target_weights array with length n."
    elif error.startswith("signals_length_mismatch") or "length mismatch" in error:
        category = "signals_length"
        suggestion = "Ensure all signal arrays/lists match the data length."
    elif error.startswith("signals_reason_length_mismatch"):
        category = "signals_length"
        suggestion = "Ensure weight_reason list matches data length."
    elif error.startswith("signals_weights_out_of_range"):
        category = "signals_schema"
        suggestion = "Ensure target_weights stay within [-1, 1]."
    elif error.startswith("signals_symbol_required_for_multi_targets"):
        category = "signals_schema"
        suggestion = "Provide symbol context or return single-symbol target_weights."
    elif error.startswith("signals_decision_expired"):
        category = "signals_schema"
        suggestion = "Refresh decision_ts/expires_at so decisions are not stale."
    elif error.startswith("signals_duplicate_decision_id"):
        category = "signals_schema"
        suggestion = "Use a unique decision_id for each new decision."
    elif error.startswith("debug_series_count_invalid"):
        category = "debug_series"
        suggestion = "Return 2-6 debug series aligned to bars."
    elif error.startswith("pytest_failed"):
        category = "pytest"
        suggestion = "Fix the failing assertions in pytest output."
    elif error.startswith("pytest_not_installed"):
        category = "pytest"
        suggestion = "Install pytest in the agent environment (required)."
    elif error.startswith("lint_failed"):
        category = "lint"
        suggestion = "Fix the lint errors reported by ruff."
    elif error.startswith("lint_not_installed"):
        category = "lint"
        suggestion = "Install ruff in the agent environment (required)."
    elif error.startswith("mypy_failed"):
        category = "mypy"
        suggestion = "Fix the mypy type errors reported."
    elif error.startswith("mypy_not_installed"):
        category = "mypy"
        suggestion = "Install mypy in the agent environment (required)."
    elif error.startswith("network_blocked"):
        category = "network"
        suggestion = "Network access is blocked in the sandbox; remove network calls."
    elif error.startswith("real_backtest_failed"):
        category = "real_backtest"
        suggestion = "Check data availability and exchange/symbol/interval settings."
    elif error.startswith("banned_import") or error.startswith("banned_call"):
        category = "safety"
        suggestion = "Remove banned imports/calls (os, subprocess, open, eval, etc.)."
    elif error.startswith("not_enough_bars"):
        category = "data"
        suggestion = "Use more bars in the smoke dataset."

    return {
        "category": category,
        "message": error or "validation_failed",
        "suggestion": suggestion,
    }


def build_smoke_script(*, default_n_bars: int = 200, interval: str = "1h") -> str:
    content = f"""import json
import os

import numpy as np
import pandas as pd

from backtest.load_strategy import load_callable_from_file
from backtest.protocol import normalize_signals
from backtest.vectorized import BacktestConfig, run_backtest


def synth_df(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rets = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.002, size=n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.002, size=n))
    volume = rng.uniform(1.0, 100.0, size=n)
    ts0 = 1700000000000
    ts = ts0 + np.arange(n, dtype=np.int64) * 3600_000
    return pd.DataFrame({{
        "timestamp": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }})


def main() -> int:
    n_bars = int(os.getenv("N_BARS", "{default_n_bars}"))
    interval = os.getenv("INTERVAL", "{interval}")
    strategy_path = os.getenv("STRATEGY_PATH", "strategy.py")

    fn = load_callable_from_file(strategy_path, "generate_signals")
    data = synth_df(n_bars)
    signals = fn(data.copy(), {{}})
    signals = normalize_signals(signals, n=len(data), mode="target_weights")

    result = run_backtest(data, signals=signals, interval=interval, config=BacktestConfig())
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    return content


def run_pytest_smoke(code: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": None,
        "traceback": "",
        "warnings": [],
    }
    try:
        import pytest  # type: ignore
    except Exception:
        payload["error"] = "pytest_not_installed"
        return payload

    with tempfile.TemporaryDirectory(prefix="agent-pytest-") as td:
        strategy_path = f"{td}/strategy.py"
        test_path = f"{td}/test_strategy_smoke.py"
        with open(strategy_path, "w", encoding="utf-8") as f:
            f.write(code.strip() + "\n")

        test_code = f"""
import numpy as np
import pandas as pd

from backtest.load_strategy import load_callable_from_file
from backtest.protocol import normalize_signals


def _synth_df(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rets = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.002, size=n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.002, size=n))
    volume = rng.uniform(1.0, 100.0, size=n)
    ts0 = 1700000000000
    ts = ts0 + np.arange(n, dtype=np.int64) * 3600_000
    return pd.DataFrame({{
        "timestamp": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }})


def test_generate_signals_smoke():
    fn = load_callable_from_file({strategy_path!r}, "generate_signals")
    data = _synth_df(200)
    out = fn(data.copy(), {{}})
    signals = normalize_signals(out, n=len(data), mode="target_weights")
    assert "target_weights" in signals and "weight_reason" in signals
"""
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code.strip() + "\n")

        ret = pytest.main([test_path, "-q"])
        if ret != 0:
            payload["error"] = "pytest_failed"
            return payload

    payload["ok"] = True
    return payload


def run_ruff_lint(code: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": None, "traceback": "", "warnings": []}
    try:
        import ruff  # type: ignore
    except Exception:
        payload["error"] = "lint_not_installed"
        return payload

    with tempfile.TemporaryDirectory(prefix="agent-lint-") as td:
        strategy_path = f"{td}/strategy.py"
        with open(strategy_path, "w", encoding="utf-8") as f:
            f.write(code.strip() + "\n")
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--select=F,E9", "--no-cache", strategy_path],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            payload["error"] = "lint_failed"
            payload["traceback"] = (proc.stdout or "")[-4000:] + (proc.stderr or "")[-4000:]
            return payload

    payload["ok"] = True
    return payload


def run_mypy_check(code: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": None, "traceback": "", "warnings": []}
    try:
        import mypy  # type: ignore
    except Exception:
        payload["error"] = "mypy_not_installed"
        return payload

    with tempfile.TemporaryDirectory(prefix="agent-mypy-") as td:
        strategy_path = f"{td}/strategy.py"
        with open(strategy_path, "w", encoding="utf-8") as f:
            f.write(code.strip() + "\n")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--ignore-missing-imports",
                "--allow-untyped-defs",
                strategy_path,
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            payload["error"] = "mypy_failed"
            payload["traceback"] = (proc.stdout or "")[-4000:] + (proc.stderr or "")[-4000:]
            return payload

    payload["ok"] = True
    return payload


def run_real_backtest(
    *,
    workspaces_dir: str,
    strategy_id: str,
    version_id: str,
    exchange: str,
    symbol: str,
    interval: str,
    fee_rate: float,
    slippage_bps: float,
    initial_cash: float,
    run_params: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": None, "traceback": "", "warnings": []}
    run_id = f"real-{uuid.uuid4().hex[:8]}"

    env = os.environ.copy()
    env.update(
        {
            "STRATEGY_ID": strategy_id,
            "VERSION_ID": version_id,
            "RUN_ID": run_id,
            "WORKSPACES_DIR": workspaces_dir,
            "EXCHANGE": exchange,
            "SYMBOL": symbol,
            "INTERVAL": interval,
            "FEE_RATE": str(fee_rate),
            "SLIPPAGE_BPS": str(slippage_bps),
            "INITIAL_CASH": str(initial_cash),
            "RUN_PARAMS_JSON": json.dumps(run_params or {}),
        }
    )
    env.setdefault("NETWORK_GUARD_ENABLED", "1")
    env.setdefault("NETWORK_ALLOWLIST", "api.binance.com,www.okx.com")

    proc = subprocess.run(
        [sys.executable, "-m", "backtest.runner"],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        payload["error"] = "real_backtest_failed"
        payload["traceback"] = (stderr or stdout)[-4000:]
        return payload

    try:
        metrics = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except Exception:
        metrics = {}

    payload["ok"] = True
    payload["metrics"] = metrics
    payload["run_id"] = run_id
    return payload


def decide_smoke_settings(
    *,
    llm: Any | None,
    prompt: str,
    current_code: str,
) -> dict[str, Any]:
    """Decide smoke test settings using rule-based approach.

    Previously used LLM call; now uses LLMMiddleware for faster,
    cheaper decision making.

    Args:
        llm: LLM configuration (unused, kept for compatibility).
        prompt: User request prompt.
        current_code: Generated/modified strategy code.

    Returns:
        Dictionary with smoke test settings:
        - run: bool - whether to run smoke test
        - max_attempts: int - maximum validation attempts
        - n_bars: int - number of bars in synthetic data
        - interval: str - bar interval
    """
    # Use rule-based decision from LLMMiddleware
    settings = LLMMiddleware.decide_smoke_settings(prompt, current_code)

    # Ensure values are within bounds
    max_attempts = max(1, min(settings.get("max_attempts", 2), 3))
    n_bars = max(100, min(settings.get("n_bars", 200), 500))
    interval = settings.get("interval", "1h")
    if interval not in ("1m", "5m", "15m", "1h", "4h", "1d"):
        interval = "1h"

    return {
        "run": settings.get("run", True),
        "max_attempts": max_attempts,
        "n_bars": n_bars,
        "interval": interval,
    }


__all__ = [
    "build_smoke_script",
    "decide_smoke_settings",
    "run_mypy_check",
    "run_pytest_smoke",
    "run_real_backtest",
    "run_ruff_lint",
    "run_static_checks",
    "run_smoke_validation",
    "summarize_validation",
]
