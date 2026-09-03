"""Strategy static linting and sandbox dry-run execution."""
from __future__ import annotations

import ast
import os
import re
import sys
import traceback
from typing import Any

import numpy as np
import pandas as pd

# Common standard libraries and aliases used in quant trading
_KNOWN_MODULES = {
    "ta": "import ta",
    "np": "import numpy as np",
    "pd": "import pandas as pd",
    "talib": "import talib",
}


def lint_and_heal_strategy_code(code: str) -> tuple[str, list[str]]:
    """Scan AST for missing standard imports (ta, np, pd, talib) and heal if missing.

    Returns:
        (healed_code, list_of_fixes)
    """
    fixes: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, fixes

    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    loaded_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded_names.add(node.id)

    missing_imports: list[str] = []
    for sym, import_stmt in _KNOWN_MODULES.items():
        if sym in loaded_names and sym not in imported_names:
            missing_imports.append(import_stmt)
            fixes.append(f"Added missing '{import_stmt}'")

    if missing_imports:
        header = "\n".join(missing_imports) + "\n\n"
        code = header + code

    # Heal list indexing error for weight_reason (e.g. weight_reason[mask] = ...)
    if re.search(r"weight_reason\s*=\s*\[\s*['\"]['\"]\s*\]\s*\*\s*len\(", code):
        code = re.sub(
            r"weight_reason\s*=\s*\[\s*['\"]['\"]\s*\]\s*\*\s*len\(([^)]+)\)",
            r"weight_reason = np.full(len(\1), '', dtype=object)",
            code,
        )
        fixes.append("Replaced list weight_reason with numpy array for Series boolean indexing")

    # Heal chained assignment anti-patterns: data['col'][mask] = val -> data.loc[mask, 'col'] = val
    chained_matches = re.findall(r"data\s*\[\s*['\"]([^'\"]+)['\"]\s*\]\s*\[(.*?)\]\s*=", code)
    if chained_matches:
        code = re.sub(
            r"data\s*\[\s*['\"]([^'\"]+)['\"]\s*\]\s*\[(.*?)\]\s*=",
            r"data.loc[\2, '\1'] =",
            code,
        )
        fixes.append(f"Auto-healed chained assignment to .loc for: {chained_matches}")

    # Heal pandas 2.0 deprecated fillna(method='ffill') / fillna(method='bfill')
    if re.search(r"\.fillna\(\s*method\s*=\s*['\"](?:ffill|bfill)['\"]\s*\)", code):
        code = re.sub(r"\.fillna\(\s*method\s*=\s*['\"]ffill['\"]\s*\)", ".ffill()", code)
        code = re.sub(r"\.fillna\(\s*method\s*=\s*['\"]bfill['\"]\s*\)", ".bfill()", code)
        fixes.append("Auto-healed deprecated fillna(method=...) to .ffill() / .bfill()")

    return code, fixes


def dry_run_strategy(
    strategy_code_or_file: str,
    params: dict[str, Any] | None = None,
    bars: int = 100,
) -> tuple[bool, str]:
    """Execute strategy with synthetic data to verify syntax, imports, and output structure.

    Returns:
        (success, error_message)
    """
    if os.path.isfile(strategy_code_or_file):
        try:
            with open(strategy_code_or_file, "r", encoding="utf-8") as f:
                code = f.read()
        except OSError as e:
            return False, f"FileReadError: {e}"
    else:
        code = strategy_code_or_file

    # 1. Basic AST validation
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    has_fn = any(
        isinstance(n, ast.FunctionDef) and n.name == "generate_signals"
        for n in tree.body
    )
    if not has_fn:
        return False, "generate_signals(data, params) entry point missing"

    # 2. Synthetic OHLCV dataset
    np.random.seed(42)
    t0 = pd.Timestamp.now().floor("min")
    timestamps = [t0 - pd.Timedelta(minutes=15 * (bars - i)) for i in range(bars)]
    close = 3000.0 + np.cumsum(np.random.randn(bars) * 10)
    high = close + np.random.uniform(0, 15, bars)
    low = close - np.random.uniform(0, 15, bars)
    open_p = close + np.random.uniform(-5, 5, bars)
    vol = np.random.uniform(10, 100, bars)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": vol,
        "funding_rate": np.random.normal(0.0001, 0.0002, bars),
        "open_interest": 100000.0 + np.cumsum(np.random.randn(bars) * 500),
    })

    # 3. Prepare isolated execution namespace
    ns: dict[str, Any] = {
        "__name__": "__dry_run__",
        "pd": pd,
        "np": np,
    }
    try:
        import ta
        ns["ta"] = ta
        from backtest import indicators
        ns["indicators"] = indicators
    except Exception:
        pass

    try:
        exec(compile(code, "<strategy_dry_run>", "exec"), ns)
    except Exception as e:
        return False, f"ExecError: {type(e).__name__}: {e}"

    fn = ns.get("generate_signals")
    if not callable(fn):
        return False, "generate_signals is not callable"

    # 4. Invoke generate_signals
    try:
        result = fn(df.copy(), params or {})
    except Exception as e:
        tb = traceback.format_exc(limit=3)
        return False, f"RuntimeError in generate_signals: {type(e).__name__}: {e}\n{tb}"

    # 5. Validate output contract
    if not isinstance(result, dict):
        return False, f"generate_signals returned {type(result).__name__}, expected dict"

    if "target_weights" not in result:
        return False, "result missing required key 'target_weights'"

    weights = result["target_weights"]
    if hasattr(weights, "__len__"):
        if len(weights) != bars:
            return False, f"target_weights length {len(weights)} does not match input bars {bars}"
    else:
        return False, "target_weights must be a list or numpy array"

    if "weight_reason" not in result:
        return False, "result missing required key 'weight_reason'"

    return True, ""
