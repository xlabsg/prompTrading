"""Command-line quant toolkit for Tau Agent and quant developers (`pt-quant`).

Provides high-speed, deterministic, low-token inspection and verification utilities:
1. `pt-quant inspect-data`: Analyze active or cached dataset characteristics without running backtests.
2. `pt-quant check <file>`: Static analysis for syntax, entry points, forbidden calls, and lookahead leaks.
3. `pt-quant dry-run <file>`: In-memory simulation with synthetic/sample data to verify output contract.
4. `pt-quant indicators [name]`: Introspect platform built-in vectorized indicators and their signatures.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import os
import sys
from typing import Any

import numpy as np
import pandas as pd


def _load_active_dataset(timeout_s: float = 3.0):
    """Load dataset based on AGENT_BACKTEST_* environment or fallback cleanly."""
    try:
        from agent.backtest_tool import BacktestDataset, load_dataset

        ds = BacktestDataset.from_env()
        # Fast check: if network guard blocks or remote call hangs, don't stall CLI
        df = load_dataset(ds)
        return ds, df
    except Exception:
        return None, None


def cmd_inspect_data(args: argparse.Namespace) -> int:
    """Inspect market dataset characteristics."""
    ds = None
    df = None
    if not args.offline:
        ds, df = _load_active_dataset()

    if df is None or len(df) == 0:
        # Fallback to current config display or synthetic preview
        exchange = os.getenv("AGENT_BACKTEST_EXCHANGE", "okx")
        symbol = os.getenv("AGENT_BACKTEST_SYMBOL", "BTC-USDT-SWAP")
        interval = os.getenv("AGENT_BACKTEST_INTERVAL", "1h")
        bars = int(os.getenv("AGENT_BACKTEST_BARS", "2000"))

        if args.json:
            print(json.dumps({
                "status": "offline_preview",
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "target_bars": bars,
            }, indent=2))
            return 0

        print("==================================================")
        print("        PT-QUANT DATASET CONFIG (OFFLINE)         ")
        print("==================================================")
        print(f"Target Symbol:    {symbol} ({exchange})")
        print(f"Bar Interval:     {interval}")
        print(f"Target Bars:      {bars}")
        print("Note: Live/cached bars not loaded in container offline mode.")
        print("Design Tip: Base your indicator lookback on the target bar interval above.")
        print("e.g. 1h interval -> 24 bars is 1 day; 15m interval -> 96 bars is 1 day.")
        print("==================================================")
        return 0

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float) if "volume" in df.columns else None

    # Calculate basic stats
    pct_change = close.pct_change().dropna()
    # Annualization factor depending on interval
    interval = (ds.interval if ds else "1h").lower()
    if "m" in interval:
        mins = int(interval.replace("m", "") or 1)
        ann_factor = np.sqrt(365 * 24 * 60 / mins)
    elif "h" in interval:
        hrs = int(interval.replace("h", "") or 1)
        ann_factor = np.sqrt(365 * 24 / hrs)
    elif "d" in interval:
        ann_factor = np.sqrt(365)
    else:
        ann_factor = np.sqrt(365 * 24)

    ann_vol = float(pct_change.std() * ann_factor)
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_14 = float(tr.rolling(14).mean().iloc[-1])
    atr_pct = (atr_14 / float(close.iloc[-1])) * 100.0 if float(close.iloc[-1]) > 0 else 0.0

    start_time = str(df["timestamp"].iloc[0]) if "timestamp" in df.columns else "N/A"
    end_time = str(df["timestamp"].iloc[-1]) if "timestamp" in df.columns else "N/A"

    if args.json:
        output = {
            "exchange": ds.exchange if ds else "unknown",
            "symbol": ds.symbol if ds else "unknown",
            "interval": ds.interval if ds else "1h",
            "bars": len(df),
            "start": start_time,
            "end": end_time,
            "last_close": float(close.iloc[-1]),
            "annualized_vol": round(ann_vol, 4),
            "atr_14": round(atr_14, 4),
            "atr_pct": round(atr_pct, 2),
            "price_min": float(close.min()),
            "price_max": float(close.max()),
            "nan_count": int(df.isna().sum().sum()),
        }
        print(json.dumps(output, indent=2))
        return 0

    print("==================================================")
    print("           PT-QUANT DATASET INSPECTION            ")
    print("==================================================")
    print(f"Target Symbol:    {ds.symbol if ds else 'N/A'} ({ds.exchange if ds else 'N/A'})")
    print(f"Bar Interval:     {ds.interval if ds else '1h'}")
    print(f"Total Bars:       {len(df)}")
    print(f"Time Range:       {start_time}  -->  {end_time}")
    print(f"Last Price:       {close.iloc[-1]:.4f} (Range: {close.min():.4f} - {close.max():.4f})")
    print(f"Annualized Vol:   {ann_vol * 100:.2f}%")
    print(f"ATR(14):          {atr_14:.4f} ({atr_pct:.2f}% of price)")
    if vol is not None:
        print(f"Avg Bar Volume:   {vol.mean():.2f}")
    nans = int(df.isna().sum().sum())
    print(f"NaN Values:       {'None (Clean)' if nans == 0 else f'{nans} NaNs detected!'}")
    print("==================================================")
    print("Design Tip: Base your indicator lookback on the bar interval above.")
    print("e.g., For 1h bars, a 24-period MA represents 1 day; for 15m bars, 96 periods = 1 day.")
    return 0


class LookaheadScanner(ast.NodeVisitor):
    """AST scanner detecting forward-looking (lookahead) leaks and unsafe calls."""

    def __init__(self):
        self.issues: list[str] = []
        self.prohibited_calls: list[str] = []

    def visit_Call(self, node: ast.Call):
        # 1. Check df.shift(-k)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "shift":
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                    self.issues.append(f"Line {node.lineno}: Lookahead bias: negative shift() call leaks future data.")
                elif isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)) and arg.value < 0:
                    self.issues.append(f"Line {node.lineno}: Lookahead bias: shift({arg.value}) leaks future data.")

        # 2. Check bfill() / fillna(method='bfill')
        if isinstance(node.func, ast.Attribute) and node.func.attr == "bfill":
            self.issues.append(f"Line {node.lineno}: Lookahead risk: bfill() propagates future values backward.")
        if isinstance(node.func, ast.Attribute) and node.func.attr == "fillna":
            for kw in node.keywords:
                if kw.arg == "method" and isinstance(kw.value, ast.Constant) and kw.value.value in ("bfill", "backfill"):
                    self.issues.append(f"Line {node.lineno}: Lookahead risk: backward fillna('{kw.value.value}') leaks future data.")

        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        forbidden = {"os", "sys", "subprocess", "socket", "urllib", "requests", "httpx", "aiohttp", "shutil"}
        for alias in node.names:
            base = alias.name.split(".")[0]
            if base in forbidden:
                self.prohibited_calls.append(f"Line {node.lineno}: Prohibited system/network import '{alias.name}'.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        forbidden = {"os", "sys", "subprocess", "socket", "urllib", "requests", "httpx", "aiohttp", "shutil"}
        if node.module:
            base = node.module.split(".")[0]
            if base in forbidden:
                self.prohibited_calls.append(f"Line {node.lineno}: Prohibited system/network from-import '{node.module}'.")
        self.generic_visit(node)


def cmd_check(args: argparse.Namespace) -> int:
    """Static analysis of strategy code."""
    file_path = args.file
    if not os.path.isfile(file_path):
        print(f"[pt-quant] Error: Strategy file not found: {file_path}", file=sys.stderr)
        return 1

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as exc:
        print(f"[pt-quant] Error reading file {file_path}: {exc}", file=sys.stderr)
        return 1

    # 1. AST Parse
    try:
        tree = ast.parse(code, filename=file_path)
    except SyntaxError as syn_err:
        print(f"[pt-quant] ❌ Syntax Error in {file_path}:")
        print(f"  Line {syn_err.lineno}, Col {syn_err.offset}: {syn_err.msg}")
        return 1

    # 2. Check generate_signals entry point
    has_fn = any(isinstance(n, ast.FunctionDef) and n.name == "generate_signals" for n in tree.body)
    if not has_fn:
        print("[pt-quant] ❌ Missing required entry point: def generate_signals(data, params)")
        return 1

    # 3. Scan for lookahead and prohibited imports
    scanner = LookaheadScanner()
    scanner.visit(tree)

    has_error = False
    if scanner.prohibited_calls:
        has_error = True
        print("[pt-quant] ❌ Prohibited System/Network calls found:")
        for item in scanner.prohibited_calls:
            print(f"  {item}")

    if scanner.issues:
        has_error = True
        print("[pt-quant] ❌ Potential Lookahead (Future) Leakage detected:")
        for issue in scanner.issues:
            print(f"  {issue}")

    # 4. Check for common anti-pattern: weight_reason = [""] * len(data) followed by mask assignment
    import re
    if re.search(r"weight_reason\s*=\s*\[\s*['\"]['\"]\s*\]\s*\*\s*len\(", code):
        print("[pt-quant] ⚠️ Warning: List indexing issue detected:")
        print("  Found `weight_reason = [''] * len(data)`. Standard Python lists cannot be sliced by boolean masks.")
        print("  Fix: Use `weight_reason = np.full(len(data), '', dtype=object)` instead.")

    if has_error:
        return 1

    print(f"[pt-quant] ✅ Strategy code '{file_path}' passed all static checks.")
    print("  - Syntax: Valid")
    print("  - Entry point: generate_signals(data, params) present")
    print("  - Lookahead bias: None detected")
    print("  - Security restrictions: Compliant")
    return 0


def cmd_dry_run(args: argparse.Namespace) -> int:
    """Run fast in-memory execution to verify data contract."""
    from agent.strategy_lint import dry_run_strategy

    file_path = args.file
    if not os.path.isfile(file_path):
        print(f"[pt-quant] Error: File not found: {file_path}", file=sys.stderr)
        return 1

    params = {}
    if args.params:
        try:
            params = json.loads(args.params)
        except Exception as exc:
            print(f"[pt-quant] Error parsing --params JSON: {exc}", file=sys.stderr)
            return 1

    bars = args.bars or 100
    ok, err = dry_run_strategy(file_path, params=params, bars=bars)
    if not ok:
        print(f"[pt-quant] ❌ Dry-run failed for '{file_path}':")
        print(f"  {err}")
        return 1

    print(f"[pt-quant] ✅ Dry-run succeeded on {bars} synthetic bars.")
    print("  - Returned dictionary with valid 'target_weights' and 'weight_reason'.")
    print("  - Signal array length perfectly matches input data length.")
    return 0


def cmd_indicators(args: argparse.Namespace) -> int:
    """List or inspect built-in technical indicators."""
    source = getattr(args, "source", "platform") or "platform"
    if source.lower() == "okx":
        print("==================================================")
        print("    OKX AGENT TRADE KIT TECHNICAL INDICATORS      ")
        print("==================================================")
        print("Source: OKX Agent Trade Kit (No auth required)")
        print("Domain skill: .tau/skills/okx-cex-market/SKILL.md\n")
        okx_indicators = [
            ("MA", "Moving Average: simple average of closing price over N bars"),
            ("EMA", "Exponential Moving Average: weighted average prioritizing recent bars"),
            ("RSI", "Relative Strength Index: momentum oscillator (default: period 14)"),
            ("MACD", "Moving Average Convergence Divergence: (12, 26, 9)"),
            ("BOLL", "Bollinger Bands: (period=20, std=2) with upper, middle, lower"),
            ("ATR", "Average True Range: volatility indicator across high/low/close"),
            ("KDJ", "Stochastic Oscillator: %K, %D, %J momentum overbought/oversold"),
            ("DMI / ADX", "Directional Movement Index: trend direction and strength"),
            ("SAR", "Parabolic Stop and Reverse: trailing stop price marker"),
            ("OBV", "On-Balance Volume: volume flow momentum indicator"),
            ("BTCRAINBOW", "Bitcoin Rainbow Logarithmic Valuation Bands"),
            ("AHR999", "AHR999 Bitcoin Accumulation & Valuation Ratio"),
        ]
        for name, desc in okx_indicators:
            print(f"  • {name:<12} : {desc}")
        print("==================================================")
        return 0

    try:
        from backtest import indicators as bt_ind
    except ImportError:
        print("[pt-quant] Error: Unable to import backtest.indicators", file=sys.stderr)
        return 1

    # If specific indicator requested
    target = (args.name or "").strip().lower()
    if target:
        fn = getattr(bt_ind, target, None)
        if fn is None or not callable(fn):
            print(f"[pt-quant] Indicator '{target}' not found in backtest.indicators.", file=sys.stderr)
            return 1

        print(f"Indicator: {target}")
        catalog = bt_ind.get_catalog() if hasattr(bt_ind, "get_catalog") else {}
        meta = catalog.get(target)
        if meta:
            print(f"Signature: {meta.signature}")
            print(f"Role:      {meta.role.upper()} ({meta.role})")
            print(f"Tags:      {', '.join(meta.tags)}")
            print(f"Inputs:    {', '.join(meta.inputs)}")
        else:
            try:
                sig = inspect.signature(fn)
                print(f"Signature: {target}{sig}")
            except Exception:
                pass
        doc = inspect.getdoc(fn)
        if doc:
            print(f"\nDocumentation:\n{doc}")
        print("\nExample import & usage:")
        print(f"  from backtest.indicators import {target}")
        print(f"  # e.g., result = {target}(data['close'], ...)")
        return 0

    # Flat registry with multi-dimensional filtering
    catalog = bt_ind.get_catalog() if hasattr(bt_ind, "get_catalog") else {}
    selected_tag = getattr(args, "tag", None) or getattr(args, "category", None)
    if selected_tag in ("all", None):
        selected_tag = None
    # Backward compatibility alias
    if selected_tag in ("core", "modern"):
        selected_tag = "trend"

    selected_role = getattr(args, "role", None)
    selected_input = getattr(args, "input", None)

    # Filter catalog
    filtered = {}
    for name, meta in catalog.items():
        if selected_tag and selected_tag.lower() not in [t.lower() for t in meta.tags]:
            continue
        if selected_role and meta.role.lower() != selected_role.lower():
            continue
        if selected_input and selected_input.lower() not in [i.lower() for i in meta.inputs]:
            continue
        filtered[name] = meta

    print("==================================================")
    print("      PLATFORM QUANTITATIVE INDICATOR REGISTRY    ")
    print("==================================================")
    print("Usage: from backtest.indicators import <name> (or import ta)")
    print("Run `pt-quant indicators <name>` for detailed signature.")
    print("Filter: --tag <tag>, --role [trigger|confirmation|filter|sizing|transform], --input <col>")
    print("Run `pt-quant indicators --source okx` for OKX Agent Trade Kit indicators.\n")

    filter_desc = []
    if selected_tag:
        filter_desc.append(f"tag='{selected_tag}'")
    if selected_role:
        filter_desc.append(f"role='{selected_role}'")
    if selected_input:
        filter_desc.append(f"input='{selected_input}'")

    if filter_desc:
        print(f"Showing {len(filtered)} indicators matching ({', '.join(filter_desc)}):\n")
    else:
        print(f"Total {len(filtered)} indicators registered in flat catalog:\n")

    for name in sorted(filtered.keys()):
        meta = filtered[name]
        tags_str = ", ".join(meta.tags)
        inputs_str = ", ".join(meta.inputs)
        print(f"  • {meta.signature or name}")
        print(f"      [role: {meta.role} | tags: {tags_str} | inputs: {inputs_str}]")
        if meta.doc:
            print(f"      {meta.doc}")
        print()

    if not filtered:
        print("  (No matching indicators found)")

    print("==================================================")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pt-quant",
        description="Quant Strategy Development Toolkit for Tau Agent & Researchers",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. inspect-data
    p_data = subparsers.add_parser("inspect-data", help="Inspect market data characteristics (volatility, ATR, bars)")
    p_data.add_argument("--json", action="store_true", help="Output in JSON format")
    p_data.add_argument("--offline", action="store_true", help="Skip remote network fetch and inspect local/environment profile")

    # 2. check
    p_check = subparsers.add_parser("check", help="Static code audit (AST, syntax, lookahead bias)")
    p_check.add_argument("file", nargs="?", default="strategy.py", help="Path to strategy.py")

    # 3. dry-run
    p_dry = subparsers.add_parser("dry-run", help="Run strategy on synthetic data to verify return schema")
    p_dry.add_argument("file", nargs="?", default="strategy.py", help="Path to strategy.py")
    p_dry.add_argument("--params", help="JSON string of parameter overrides")
    p_dry.add_argument("--bars", type=int, default=100, help="Number of bars to simulate")

    # 4. indicators
    p_ind = subparsers.add_parser("indicators", help="Introspect platform indicators")
    p_ind.add_argument("name", nargs="?", help="Specific indicator name to inspect")
    p_ind.add_argument("--source", choices=["platform", "okx"], default="platform", help="Indicator source (platform or okx)")
    p_ind.add_argument("--tag", help="Filter indicators by tag (e.g. trend, momentum, volume, crypto, atomic)")
    p_ind.add_argument("--category", help="Alias for --tag (backward compatibility)")
    p_ind.add_argument("--role", choices=["trigger", "confirmation", "filter", "sizing", "transform"], help="Filter by functional role")
    p_ind.add_argument("--input", help="Filter by required input column (e.g. volume, funding_rate, high, low, close)")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "inspect-data":
        return cmd_inspect_data(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "dry-run":
        return cmd_dry_run(args)
    if args.command == "indicators":
        return cmd_indicators(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
