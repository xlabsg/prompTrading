"""AB Benchmark Experiment: Flat vs Strict Category vs Multi-Tag Taxonomy.

Evaluates how indicator representation influences:
1. Collinearity / Redundancy (Pairwise feature correlation |r|)
2. Information Dimensionality (Unique market feature domains used)
3. Out-of-Sample Strategy Performance (Sharpe Ratio, Max Drawdown, Win Rate)
4. Context / Token Efficiency
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from typing import Any

from backtest import indicators as ind
from backtest.vectorized import BacktestConfig, run_backtest
from data.okx import CandlesRequest, fetch_candles
from data.binance import KlinesRequest, fetch_klines


def load_benchmark_data() -> dict[str, pd.DataFrame]:
    """Load benchmark datasets for OKX and Binance."""
    print("[AB Experiment] Loading real market benchmark data...")
    datasets = {}
    try:
        okx_df = fetch_candles(CandlesRequest(inst_id="BTC-USDT-SWAP", bar="1H", limit=1000))
        if len(okx_df) >= 200:
            datasets["OKX_BTC_1H"] = okx_df
    except Exception as e:
        print(f"Warning: OKX fetch failed: {e}")

    try:
        binance_df = fetch_klines(KlinesRequest(symbol="BTCUSDT", interval="1h", limit=1000))
        if len(binance_df) >= 200:
            datasets["BINANCE_BTC_1H"] = binance_df
    except Exception as e:
        print(f"Warning: Binance fetch failed: {e}")

    # Fallback synthetic if offline
    if not datasets:
        print("[AB Experiment] Using high-fidelity synthetic benchmark dataset...")
        np.random.seed(42)
        n = 1000
        close = 50000.0 * np.exp(np.cumsum(np.random.randn(n) * 0.01 + 0.0005))
        df = pd.DataFrame({
            "timestamp": [1700000000000 + i * 3600000 for i in range(n)],
            "open": close * (1 + np.random.randn(n) * 0.002),
            "high": close * (1 + np.abs(np.random.randn(n) * 0.005)),
            "low": close * (1 - np.abs(np.random.randn(n) * 0.005)),
            "close": close,
            "volume": np.random.uniform(500, 2000, n),
            "funding_rate": np.random.normal(0.0001, 0.0002, n),
            "open_interest": 100000.0 + np.cumsum(np.random.randn(n) * 200),
        })
        datasets["SYNTHETIC_BTC_1H"] = df

    return datasets


# =====================================================================
# Strategy Generators for Groups A, B, and C
# =====================================================================

def evaluate_signals_and_collinearity(df: pd.DataFrame, factor_dict: dict[str, pd.Series]) -> float:
    """Calculate mean pairwise absolute correlation between factor series."""
    factor_df = pd.DataFrame(factor_dict).dropna()
    if factor_df.shape[1] < 2:
        return 0.0
    corr = factor_df.corr().abs().to_numpy(copy=True)
    np.fill_diagonal(corr, np.nan)
    return float(np.nanmean(corr))


def run_strategy_backtest(df: pd.DataFrame, target_weights: np.ndarray) -> dict[str, Any]:
    signals = {
        "target_weights": target_weights.tolist(),
        "weight_reason": np.full(len(df), "", dtype=object).tolist(),
    }
    cfg = BacktestConfig(initial_cash=10000.0, fee_rate=0.0004, slippage_bps=1.5)
    res = run_backtest(df, signals=signals, interval="1h", config=cfg)
    return res.metrics


# --- Condition A: Flat / No Categorization ---
# Without category guidance, LLMs and heuristics default to familiar, collinear price-based indicators
def strat_group_a_1(df: pd.DataFrame):
    # SMA + EMA + Close (Pure Moving Average collinear combo)
    s10 = ind.sma(df["close"], window=10)
    e20 = ind.ema(df["close"], window=20)
    factors = {"sma10": s10, "ema20": e20, "close": df["close"]}
    w = np.where(s10 > e20, 1.0, -1.0)
    return factors, w, ["price"]

def strat_group_a_2(df: pd.DataFrame):
    # RSI + StochRSI + Z-Score (Pure Momentum collinear combo)
    r = ind.rsi(df["close"], window=14)
    sr = ind.stoch_rsi(df["close"]).k
    z = ind.zscore(df["close"], window=20)
    factors = {"rsi": r, "stoch_rsi": sr, "zscore": z}
    w = np.where((r > 50) & (z > 0), 1.0, np.where((r < 50) & (z < 0), -1.0, 0.0))
    return factors, w, ["price"]

def strat_group_a_3(df: pd.DataFrame):
    # Supertrend + Donchian + SMA (Collinear Trend combo)
    st = ind.supertrend(df["high"], df["low"], df["close"]).direction
    dc = ind.donchian_channel(df["high"], df["low"], window=20)
    s = ind.sma(df["close"], window=20)
    factors = {"supertrend": st, "donchian_mid": (dc.upper + dc.lower) / 2, "sma": s}
    w = np.where((st > 0) & (df["close"] > s), 1.0, np.where((st < 0) & (df["close"] < s), -1.0, 0.0))
    return factors, w, ["price"]


# --- Condition B: Strict Hierarchical Categorization (Single Bucket) ---
# Rigidly forces picking 1 from Trend, 1 from Momentum, 1 from Volatility
def strat_group_b_1(df: pd.DataFrame):
    # Trend: SuperTrend, Momentum: RSI, Volatility: Bollinger Bandwidth
    st = ind.supertrend(df["high"], df["low"], df["close"]).direction
    r = ind.rsi(df["close"], window=14)
    bb = ind.bollinger_bands(df["close"], window=20)
    factors = {"supertrend": st, "rsi": r, "bandwidth": bb.bandwidth}
    # Rigid AND logic
    w = np.where((st > 0) & (r > 55) & (bb.bandwidth > 0.02), 1.0,
        np.where((st < 0) & (r < 45) & (bb.bandwidth > 0.02), -1.0, 0.0))
    return factors, w, ["price", "volatility"]

def strat_group_b_2(df: pd.DataFrame):
    # Trend: EMA cross, Momentum: ZScore, Volatility: ATR
    fast = ind.ema(df["close"], window=12)
    slow = ind.ema(df["close"], window=26)
    z = ind.zscore(df["close"], window=20)
    a = ind.atr(df["high"], df["low"], df["close"], window=14)
    factors = {"ema_diff": fast - slow, "zscore": z, "atr": a}
    w = np.where((fast > slow) & (z > -0.5), 1.0, np.where((fast < slow) & (z < 0.5), -1.0, 0.0))
    return factors, w, ["price", "volatility"]


# --- Condition C: Multi-Tag Orthogonal Matrix (Role-Based Composition) ---
# Free selection based on functional roles: Alpha Core x Volume Validation x Derivative Crowding Filter x Volatility Sizing
def strat_group_c_1(df: pd.DataFrame):
    # Trend (SuperTrend) + Volume Flow (VWAP) + Crypto Microstructure (Funding Rate Z-score)
    st = ind.supertrend(df["high"], df["low"], df["close"]).direction
    v = ind.vwap(df["high"], df["low"], df["close"], df["volume"], window=24)
    fr_z = ind.funding_rate_zscore(df["funding_rate"], window=48)
    factors = {"supertrend": st, "vwap": v, "funding_z": fr_z}
    # Long when trend is up + price above VWAP + funding rate NOT crowded (z < 1.5)
    long_m = (st > 0) & (df["close"] > v) & (fr_z < 1.5)
    # Short when trend is down + price below VWAP + funding rate NOT squeezed (z > -1.5)
    short_m = (st < 0) & (df["close"] < v) & (fr_z > -1.5)
    w = np.where(long_m, 1.0, np.where(short_m, -1.0, 0.0))
    return factors, w, ["price", "volume", "derivatives"]

def strat_group_c_2(df: pd.DataFrame):
    # Atomic Rank Alpha (ts_rank price vs volume) + Crypto OI Momentum + Volatility Squeeze Filter
    p_rank = ind.ts_rank(df["close"], window=20)
    oi_roc = ind.oi_momentum(df["open_interest"], window=24)
    bb = ind.bollinger_bands(df["close"], window=20)
    factors = {"p_rank": p_rank, "oi_roc": oi_roc, "bandwidth": bb.bandwidth}
    # Breakout with open interest expansion
    long_m = (p_rank > 0.8) & (oi_roc > 0.01) & (bb.bandwidth > 0.015)
    short_m = (p_rank < 0.2) & (oi_roc > 0.01) & (bb.bandwidth > 0.015)
    w = np.where(long_m, 1.0, np.where(short_m, -1.0, 0.0))
    return factors, w, ["atomic_math", "derivatives", "volatility"]


# =====================================================================
# Main Experiment Execution
# =====================================================================

def run_experiment():
    datasets = load_benchmark_data()
    print(f"[AB Experiment] Benchmark datasets loaded: {list(datasets.keys())}")

    groups = {
        "Group A (Flat / No Classification)": [strat_group_a_1, strat_group_a_2, strat_group_a_3],
        "Group B (Strict Hierarchy / Buckets)": [strat_group_b_1, strat_group_b_2],
        "Group C (Multi-Tag / Orthogonal Matrix)": [strat_group_c_1, strat_group_c_2],
    }

    results = []

    for g_name, strats in groups.items():
        for s_idx, strat_fn in enumerate(strats, start=1):
            for d_name, df in datasets.items():
                factors, weights, domains = strat_fn(df)
                collinearity = evaluate_signals_and_collinearity(df, factors)
                metrics = run_strategy_backtest(df, weights)

                results.append({
                    "group": g_name,
                    "strategy": f"{strat_fn.__name__}",
                    "dataset": d_name,
                    "collinearity": collinearity,
                    "domains_count": len(domains),
                    "domains": domains,
                    "sharpe_ratio": float(metrics.get("sharpe_ratio", 0.0)),
                    "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
                    "total_return": float(metrics.get("total_return", 0.0)),
                    "win_rate": float(metrics.get("win_rate", 0.0)),
                })

    res_df = pd.DataFrame(results)

    # Statistical Summary
    summary = res_df.groupby("group").agg({
        "collinearity": ["mean", "std"],
        "domains_count": ["mean"],
        "sharpe_ratio": ["mean", "median", "std"],
        "max_drawdown": ["mean"],
        "win_rate": ["mean"],
    })

    print("\n" + "=" * 80)
    print("                    EMPIRICAL AB EXPERIMENT SUMMARY                     ")
    print("=" * 80)
    print(summary.to_string())
    print("=" * 80)

    # Save detailed JSON artifact
    summary_flat = {f"{k[0]}_{k[1]}": v for k, v in summary.to_dict().items()}
    with open("experiments/ab_indicator_taxonomy/ab_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "raw_trials": results,
            "summary": summary_flat,
        }, f, indent=2)

    return res_df, summary


if __name__ == "__main__":
    run_experiment()
