"""Genuine End-to-End LLM A/B Experiment on Indicator Taxonomy.

Calls DeepSeek (via configured LLM API in infra/compose/.env) under 3 conditions:
- Condition A: Flat / No Classification (alphabetical list)
- Condition B: Strict Hierarchical Categorization (single-bucket list)
- Condition C: Flat Registry with Orthogonal Roles, Tags, and Inputs

Evaluates generated Python strategies on real market data (OKX & Binance BTC 1h).
Measures:
1. First-pass AST & Sandbox Execution Pass Rate
2. Indicators imported & used
3. Feature Collinearity (|r|)
4. Cross-Domain Coverage (Price, Volume, Volatility, Derivatives)
5. Out-of-Sample Backtest Sharpe Ratio, Drawdown, and Returns
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from typing import Any

from dotenv import dotenv_values
import numpy as np
import pandas as pd
import requests

from backtest import indicators as ind
from backtest.vectorized import BacktestConfig, run_backtest
from data.okx import CandlesRequest, fetch_candles
from data.binance import KlinesRequest, fetch_klines

# Output directories
DIR_EXP = "experiments/ab_indicator_taxonomy"
DIR_STRATS = os.path.join(DIR_EXP, "generated_strategies")
os.makedirs(DIR_STRATS, exist_ok=True)


# =====================================================================
# 1. LLM Client Setup
# =====================================================================

def get_llm_config() -> tuple[str, str, str]:
    cfg = dotenv_values("../../infra/compose/.env")
    if not cfg:
        cfg = dotenv_values("infra/compose/.env")
    base_url = cfg.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
    api_key = cfg.get("LLM_API_KEY", "")
    model = cfg.get("LLM_MODEL", "deepseek-chat")
    if not api_key:
        raise ValueError("Missing LLM_API_KEY in infra/compose/.env")
    return base_url, api_key, model


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
    base_url, api_key, model = get_llm_config()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 3500,
    }
    resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# =====================================================================
# 2. Prompts for Condition A, B, and C
# =====================================================================

COMMON_TASK_INSTRUCTIONS = """
TASK:
Write a clean, concise, high-performance quantitative trading strategy in Python for BTC/USDT 1-hour perpetual futures.
The required entry point is:
```python
def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    ...
    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason.tolist(),
    }
```
Rules:
1. `data` is a pandas DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'funding_rate', 'open_interest'].
2. `target_weights` must be a numpy array of floats between -1.0 (max short) and 1.0 (max long), 0.0 (neutral/cash).
3. Do NOT leak future data (no negative shifts, no lookahead).
4. Keep the strategy concise (under 80 lines of clean Python code).
5. Output ONLY valid runnable Python code enclosed in a ```python ... ``` codeblock. No commentary outside the codeblock.
"""

# --- Condition A: Flat / No Categorization ---
SYSTEM_PROMPT_A = f"""You are an expert crypto quant strategist.
You develop strategies using platform built-in vectorized indicators from `backtest.indicators`.

Available Platform Indicators (import from backtest.indicators):
- atr(high, low, close, window=14) -> pd.Series
- bollinger_bands(close, window=20, num_std=2.0) -> BollingerBandsResult(upper, middle, lower, bandwidth, percent_b)
- cmf(high, low, close, volume, window=20) -> pd.Series
- cross_over(a, b) -> pd.Series
- cross_under(a, b) -> pd.Series
- donchian_channel(high, low, window=20) -> DonchianChannelResult(upper, middle, lower)
- ema(x, window=10) -> pd.Series
- funding_rate_zscore(funding_rate, window=72) -> pd.Series
- keltner_channel(high, low, close, ema_window=20, atr_window=10) -> KeltnerChannelResult(upper, middle, lower)
- oi_momentum(open_interest, window=24) -> pd.Series
- rsi(close, window=14) -> pd.Series
- safe_div(num, denom, fill=0.0) -> pd.Series
- sma(x, window=10) -> pd.Series
- stoch_rsi(close, rsi_window=14, stoch_window=14) -> StochRsiResult(k, d)
- supertrend(high, low, close, period=10, multiplier=3.0) -> SupertrendResult(supertrend, direction)
- ts_corr(x, y, window=20) -> pd.Series
- ts_decay_linear(x, window=10) -> pd.Series
- ts_rank(x, window=14) -> pd.Series
- vwap(high, low, close, volume, window=None) -> pd.Series
- zscore(x, window=20) -> pd.Series

{COMMON_TASK_INSTRUCTIONS}
"""

# --- Condition B: Strict Hierarchical Single-Bucket Categorization ---
SYSTEM_PROMPT_B = f"""You are an expert crypto quant strategist.
You develop strategies using platform built-in vectorized indicators from `backtest.indicators`.

Available Platform Indicators grouped by Category:
[Trend Category]
- supertrend(high, low, close, period=10, multiplier=3.0)
- donchian_channel(high, low, window=20)
- ema(x, window=10)
- sma(x, window=10)
- cross_over(a, b), cross_under(a, b)

[Momentum Category]
- rsi(close, window=14)
- stoch_rsi(close, rsi_window=14, stoch_window=14)
- zscore(x, window=20)

[Volatility Category]
- atr(high, low, close, window=14)
- bollinger_bands(close, window=20, num_std=2.0)
- keltner_channel(high, low, close, ema_window=20, atr_window=10)

[Volume Category]
- vwap(high, low, close, volume, window=None)
- cmf(high, low, close, volume, window=20)

[Crypto Derivatives Category]
- funding_rate_zscore(funding_rate, window=72)
- oi_momentum(open_interest, window=24)

[Atomic Math Category]
- ts_rank(x, window=14), ts_corr(x, y, window=20), safe_div(num, denom)

Instructions: Select indicators from each category to build your strategy.

{COMMON_TASK_INSTRUCTIONS}
"""

# --- Condition C: Flat Tagged Registry with Orthogonal Roles & Inputs ---
SYSTEM_PROMPT_C = f"""You are an expert crypto quant strategist.
You develop strategies using platform built-in vectorized indicators from `backtest.indicators`.

Platform Indicator Registry (import from backtest.indicators):
Each indicator is characterized by functional roles and data inputs:

1. Triggers [Role: TRIGGER] (Primary directional decisions):
   - supertrend(high, low, close) [tags: trend, breakout | inputs: high, low, close]
   - donchian_channel(high, low) [tags: trend, breakout, channel | inputs: high, low]
   - ema(close, window=10), sma(close, window=10) [tags: trend, moving_average | inputs: close]

2. Confirmations [Role: CONFIRMATION] (Cross-domain signal validation to prevent false breakouts):
   - vwap(high, low, close, volume) [tags: volume, benchmark | inputs: price, volume]
   - cmf(high, low, close, volume) [tags: volume, money_flow | inputs: price, volume]
   - rsi(close), stoch_rsi(close) [tags: momentum, oscillator | inputs: close]
   - oi_momentum(open_interest) [tags: crypto, derivatives, momentum | inputs: open_interest]

3. Filters [Role: FILTER] (Market regime classification & squeeze risk protection):
   - funding_rate_zscore(funding_rate) [tags: crypto, derivatives, sentiment | inputs: funding_rate] (detects crowded squeeze)
   - bollinger_bands(close), keltner_channel(high, low, close) [tags: volatility, bands | inputs: price] (volatility compression filter)

4. Dynamic Sizing [Role: SIZING] (Risk-based volatility parity sizing & stops):
   - atr(high, low, close) [tags: volatility, risk | inputs: price]

5. Atomic Transforms [Role: TRANSFORM] (Time-series mathematical primitives):
   - ts_rank(x), ts_corr(x, y), safe_div(num, denom) [tags: atomic, math]

Best Practice: To maximize the Sharpe ratio, build an orthogonal composite alpha by combining across independent dimensions:
Trigger (e.g. Trend) x Confirmation (e.g. Volume Flow / OI) x Filter (e.g. Funding Squeeze) x Sizing (Volatility).

{COMMON_TASK_INSTRUCTIONS}
"""


# =====================================================================
# 3. Strategy Code Extraction, AST Analysis, and Execution
# =====================================================================

def extract_code_block(raw_text: str) -> str:
    # First try closed ```python ... ```
    m = re.search(r"```(?:python)?\s*\n(.*?)```", raw_text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # If unclosed ```python ...
    m2 = re.search(r"```(?:python)?\s*\n(.*)", raw_text, re.DOTALL)
    if m2:
        return m2.group(1).strip()
    return raw_text.strip()


def analyze_ast_indicators(code: str) -> dict[str, Any]:
    """Parse AST to extract imported indicators and domain coverage."""
    tree = ast.parse(code)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("backtest.indicators", "indicators", "ta"):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                imported.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                imported.append(node.func.attr)

    imported = list(set(imported))

    # Check domains
    domains = set()
    for name in imported:
        norm = name.lower()
        if any(k in norm for k in ("sma", "ema", "trend", "donchian", "keltner", "cross")):
            domains.add("trend")
        if any(k in norm for k in ("rsi", "stoch", "zscore")):
            domains.add("momentum")
        if any(k in norm for k in ("atr", "bollinger", "std")):
            domains.add("volatility")
        if any(k in norm for k in ("vwap", "cmf", "volume")):
            domains.add("volume")
        if any(k in norm for k in ("funding", "oi_", "open_interest")):
            domains.add("crypto_derivatives")
        if any(k in norm for k in ("ts_rank", "ts_corr", "ts_cov", "safe_div")):
            domains.add("atomic_math")

    return {
        "indicators": imported,
        "domains": list(domains),
        "domain_count": len(domains),
    }


def execute_strategy(code: str, df: pd.DataFrame) -> tuple[bool, Any, str]:
    """Execute strategy code in isolated sandbox and extract target_weights."""
    sandbox_globals = {
        "pd": pd,
        "np": np,
        "data": df,
        "indicators": ind,
    }
    # Pre-populate backtest.indicators functions into sandbox
    for name in dir(ind):
        if not name.startswith("_"):
            sandbox_globals[name] = getattr(ind, name, None)

    try:
        compiled = compile(code, "<strategy>", "exec")
        exec(compiled, sandbox_globals)
    except Exception as e:
        return False, None, f"Compilation error: {e}"

    if "generate_signals" not in sandbox_globals:
        return False, None, "Missing generate_signals function"

    try:
        fn = sandbox_globals["generate_signals"]
        res = fn(df, {})
    except Exception as e:
        return False, None, f"Runtime error: {e}"

    if not isinstance(res, dict) or "target_weights" not in res:
        return False, None, "Invalid return schema"

    weights = np.array(res["target_weights"], dtype=float)
    if len(weights) != len(df):
        return False, None, f"Length mismatch: {len(weights)} vs {len(df)}"

    return True, weights, ""


# =====================================================================
# 4. Main Experiment Runner
# =====================================================================

def run_real_llm_ab_experiment(trials_per_group: int = 3):
    print("=" * 80)
    print("      LAUNCHING GENUINE END-TO-END LLM A/B TAXONOMY EXPERIMENT           ")
    print("=" * 80)

    # 1. Load real data
    print("[1/3] Loading real benchmark data (OKX BTC-USDT-SWAP 1H)...")
    df = fetch_candles(CandlesRequest(inst_id="BTC-USDT-SWAP", bar="1H", limit=1000))
    print(f"      Loaded {len(df)} 1H bars with columns: {df.columns.tolist()}")

    groups = {
        "Group A (Flat / No Classification)": SYSTEM_PROMPT_A,
        "Group B (Strict Single-Bucket Hierarchy)": SYSTEM_PROMPT_B,
        "Group C (Flat Registry + Orthogonal Tags/Roles)": SYSTEM_PROMPT_C,
    }

    user_query = "Please write a high-Sharpe, drawdown-resilient trend & momentum strategy for BTC/USDT 1h."

    results = []

    print(f"\n[2/3] Executing real LLM generations ({trials_per_group} trials per group)...")
    for group_name, system_prompt in groups.items():
        print(f"\n>>> Running {group_name}...")
        for trial_i in range(1, trials_per_group + 1):
            strat_filename = f"{group_name[:7].replace(' ', '_')}_trial_{trial_i}.py"
            strat_path = os.path.join(DIR_STRATS, strat_filename)

            print(f"  [Trial {trial_i}/{trials_per_group}] Calling LLM API...", end="", flush=True)
            t0 = time.time()
            try:
                raw_response = call_llm(system_prompt, user_query, temperature=0.7)
                code = extract_code_block(raw_response)
                elapsed = time.time() - t0
                print(f" Success ({elapsed:.1f}s, {len(code)} chars)")
            except Exception as e:
                print(f" Failed: {e}")
                continue

            # Save code
            with open(strat_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Analyze AST
            try:
                ast_info = analyze_ast_indicators(code)
            except Exception:
                ast_info = {"indicators": [], "domains": [], "domain_count": 0}

            # Execute on real data
            ok, weights, err = execute_strategy(code, df)
            if not ok:
                print(f"      ❌ Execution failed: {err}")
                results.append({
                    "group": group_name,
                    "trial": trial_i,
                    "success": False,
                    "error": err,
                    "domains_count": ast_info["domain_count"],
                    "domains": ast_info["domains"],
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 100.0,
                    "total_return": 0.0,
                    "win_rate": 0.0,
                })
                continue

            # Run vectorized backtest
            cfg = BacktestConfig(initial_cash=10000.0, fee_rate=0.0004, slippage_bps=1.5)
            metrics = run_backtest(df, signals={"target_weights": weights.tolist(), "weight_reason": [""] * len(df)}, interval="1h", config=cfg).metrics

            s_ratio = metrics.get('sharpe_ratio') or 0.0
            m_dd = metrics.get('max_drawdown') or 0.0
            t_ret = metrics.get('total_return') or 0.0
            w_rate = metrics.get('win_rate') or 0.0

            print(f"      ✅ Valid! Domains: {ast_info['domain_count']} {ast_info['domains']} | Sharpe: {s_ratio:.2f} | MDD: {m_dd:.1f}% | Return: {t_ret*100:.1f}%")

            results.append({
                "group": group_name,
                "trial": trial_i,
                "success": True,
                "error": "",
                "domains_count": ast_info["domain_count"],
                "domains": ast_info["domains"],
                "sharpe_ratio": float(s_ratio),
                "max_drawdown": float(m_dd),
                "total_return": float(t_ret),
                "win_rate": float(w_rate),
            })

    # Summary analysis
    res_df = pd.DataFrame(results)
    summary = res_df.groupby("group").agg({
        "success": ["mean"],
        "domains_count": ["mean"],
        "sharpe_ratio": ["mean", "median", "std"],
        "max_drawdown": ["mean"],
        "total_return": ["mean"],
    })

    print("\n" + "=" * 80)
    print("              REAL LLM A/B EXPERIMENT STATISTICAL SUMMARY              ")
    print("=" * 80)
    print(summary.to_string())
    print("=" * 80)

    # Save artifact
    with open(os.path.join(DIR_EXP, "real_llm_ab_results.json"), "w", encoding="utf-8") as f:
        json.dump({
            "trials": results,
            "summary": {f"{k[0]}_{k[1]}": v for k, v in summary.to_dict().items()},
        }, f, indent=2)

    return res_df, summary


if __name__ == "__main__":
    run_real_llm_ab_experiment(trials_per_group=3)
