from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from typing import Any
from datetime import datetime

import numpy as np
import pandas as pd

from backtest.execution_core import describe_weight_transition


@dataclass(frozen=True)
class RunMeta:
    strategy_id: str
    version_id: str
    run_id: str
    dataset: dict[str, Any]
    params: dict[str, Any]
    engine_type: str
    signal_mode: str | None = None
    protocol_version: str | None = None
    decision_id: str | None = None
    signal_symbol: str | None = None


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)


def write_parquet(df: pd.DataFrame, path: str) -> None:
    df.to_parquet(path, index=False)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _py_scalar(x: Any) -> Any:
    """Convert common numpy/pandas scalars into JSON-safe Python scalars."""
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _to_bar_series(x: Any, n: int) -> list[Any] | None:
    """Try to convert `x` into a JSON-safe 1D list aligned to bars (length n)."""
    if x is None:
        return None

    if isinstance(x, pd.Series):
        x = x.to_numpy()

    if isinstance(x, np.ndarray):
        arr = x
    elif isinstance(x, (list, tuple)):
        if len(x) != n:
            return None
        return [_py_scalar(v) for v in x]
    else:
        return None

    arr = np.asarray(arr)
    if arr.ndim != 1 or int(arr.shape[0]) != int(n):
        return None
    return [_py_scalar(v) for v in arr.tolist()]


def serialize_signals(signals: dict[str, Any], n: int) -> dict[str, Any]:
    """Serialize `generate_signals` output into a compact, JSON-safe payload.

    Only includes bar-aligned 1D arrays (length n) under `series`.
    Scalars are kept under `meta`. Everything else is dropped to keep artifacts small/robust.
    """
    series: dict[str, list[Any]] = {}
    meta: dict[str, Any] = {}

    for k, v in (signals or {}).items():
        key = str(k)
        bar_series = _to_bar_series(v, n)
        if bar_series is not None:
            series[key] = bar_series
            continue

        if v is None or isinstance(v, (str, bool, int, float, np.generic)):
            meta[key] = _py_scalar(v)

    payload: dict[str, Any] = {"schema": "signals_v1", "n": int(n), "series": series}
    if meta:
        payload["meta"] = meta
    return payload


def _format_trades_for_frontend(trades: pd.DataFrame) -> list[dict[str, Any]]:
    """Format trades DataFrame for frontend consumption."""
    formatted_trades = []
    
    for _, trade in trades.iterrows():
        # Convert timestamps to readable dates
        entry_time = datetime.fromtimestamp(int(trade["entry_ts"]) / 1000)
        exit_time = datetime.fromtimestamp(int(trade["exit_ts"]) / 1000)

        # Calculate duration
        duration_hours = (exit_time - entry_time).total_seconds() / 3600
        if duration_hours < 1:
            duration = f"{int(duration_hours * 60)}m"
        elif duration_hours < 24:
            duration = f"{int(duration_hours)}h"
        else:
            duration = f"{int(duration_hours / 24)}d"

        formatted_trades.append({
            "side": str(trade["side"]),
            "entry_time": entry_time.strftime("%m/%d/%Y, %I:%M:%S %p"),
            "exit_time": exit_time.strftime("%m/%d/%Y, %I:%M:%S %p"),
            "entry_time_ms": int(trade["entry_ts"]),
            "exit_time_ms": int(trade["exit_ts"]),
            "entry_price": round(float(trade["entry_price"]), 2),
            "exit_price": round(float(trade["exit_price"]), 2),
            "return_pct": round(float(trade["return"]) * 100, 2),
            "pnl": round(float(trade["pnl"]), 2),
            "duration": duration,
            "holding_time_ms": int(int(trade["exit_ts"]) - int(trade["entry_ts"])),
        })

    return formatted_trades


def _format_orders_for_frontend(
    equity: pd.DataFrame,
    positions: pd.DataFrame,
    *,
    fee_rate: float,
    initial_cash: float,
    signals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build a simple rebalance 'orders' stream from weight transitions.

    Notes:
    - This vectorized engine models target weights and applies fees on weight deltas.
    - Orders are synthesized at bar close when weight changes (rebalance).
    """
    if len(equity) == 0:
        return []

    ts = positions["timestamp"].to_numpy(dtype=np.int64)
    close = positions["close"].to_numpy(dtype=np.float64)
    w = equity["weight"].to_numpy(dtype=np.float64)
    r = equity["returns"].to_numpy(dtype=np.float64)
    eq = equity["equity"].to_numpy(dtype=np.float64)

    # Default context features at signal bars (useful even when strategy doesn't return debug series).
    try:
        from backtest.indicators import rsi as _rsi, sma as _sma
    except Exception:  # pragma: no cover
        _rsi = _sma = None  # type: ignore[assignment]
    close_s = pd.Series(close)
    sma10 = _sma(close_s, 10) if _sma else pd.Series([np.nan] * len(close_s))
    sma30 = _sma(close_s, 30) if _sma else pd.Series([np.nan] * len(close_s))
    rsi14 = _rsi(close_s, 14) if _rsi else pd.Series([np.nan] * len(close_s))

    def _default_context(i: int) -> dict[str, Any]:
        return {
            "close": round(float(close[i]), 6),
            "ret_1": _py_scalar(float(r[i])) if i < len(r) else None,
            "sma10": _py_scalar(float(sma10.iloc[i])) if i < len(sma10) else None,
            "sma30": _py_scalar(float(sma30.iloc[i])) if i < len(sma30) else None,
            "rsi14": _py_scalar(float(rsi14.iloc[i])) if i < len(rsi14) else None,
        }

    orders: list[dict[str, Any]] = []

    def fmt_time(ms: int) -> str:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%m/%d/%Y, %I:%M:%S %p")

    signal_source = "unknown"
    if isinstance(signals, dict):
        if "target_weights" in signals:
            signal_source = "target_weights"
    decision_id = str((signals or {}).get("decision_id") or "") if isinstance(signals, dict) else ""
    protocol_version = str((signals or {}).get("protocol_version") or "") if isinstance(signals, dict) else ""
    signal_symbol = str((signals or {}).get("signal_symbol") or "") if isinstance(signals, dict) else ""
    decision_ts = _py_scalar((signals or {}).get("decision_ts")) if isinstance(signals, dict) else None
    expires_at = _py_scalar((signals or {}).get("expires_at")) if isinstance(signals, dict) else None

    def _bar_scalar(v: Any, idx: int, n: int) -> Any | None:
        if v is None:
            return None
        if isinstance(v, pd.Series):
            v = v.to_numpy()
        if isinstance(v, np.ndarray):
            arr = np.asarray(v)
            if arr.ndim != 1 or int(arr.shape[0]) != int(n):
                return None
            return _py_scalar(arr[idx])
        if isinstance(v, (list, tuple)):
            if len(v) != n:
                return None
            return _py_scalar(v[idx])
        return None

    def _extra_features(idx: int, n: int) -> dict[str, Any] | None:
        if not isinstance(signals, dict):
            return None
        reserved = {
            "target_weights",
            "weight_reason",
            "rebalance_reason",
            "decision_id",
            "protocol_version",
            "decision_ts",
            "expires_at",
            "signal_symbol",
            "diagnostics",
            "decision",
            "targets",
        }
        feats: dict[str, Any] = {}
        for k, v in signals.items():
            key = str(k)
            if key in reserved:
                continue
            val = _bar_scalar(v, idx, n)
            if val is None:
                continue
            feats[key] = val
        return feats or None

    def add_order(
        *,
        i: int,
        weight_from: float,
        weight_to: float,
        equity_before: float,
        equity_after: float,
        units_before: float,
        units_after: float,
        fee: float,
    ) -> None:
        qty_delta = float(units_after - units_before)
        if abs(qty_delta) < 1e-12:
            return
        px = float(close[i])
        side = "buy" if qty_delta > 0 else "sell"
        qty = abs(qty_delta)
        transition = describe_weight_transition(weight_from, weight_to, signal_source=signal_source)

        n = len(ts)
        weight_reason = None
        if isinstance(signals, dict):
            wr = signals.get("weight_reason")
            rr = signals.get("rebalance_reason")
            weight_reason = _bar_scalar(wr if wr is not None else rr, i, n)
        entries_raw = _bar_scalar(signals.get("entries") if isinstance(signals, dict) else None, i, n)  # type: ignore[arg-type]
        exits_raw = _bar_scalar(signals.get("exits") if isinstance(signals, dict) else None, i, n)  # type: ignore[arg-type]
        tgt_w = _bar_scalar(signals.get("target_weights") if isinstance(signals, dict) else None, i, n)  # type: ignore[arg-type]

        detail = weight_reason
        if detail is None:
            if tgt_w is not None:
                detail = f"target_weight={tgt_w} dw={round(float(weight_to) - float(weight_from), 6)}"
            else:
                detail = f"dw={round(float(weight_to) - float(weight_from), 6)}"

        feats = _extra_features(i, n) or {}
        # Merge in default context (do not overwrite strategy-provided fields).
        for k, v in _default_context(i).items():
            feats.setdefault(k, v)

        orders.append(
            {
                "time_ms": int(ts[i]),
                "time": fmt_time(int(ts[i])),
                "side": side,
                "position_side": transition.position_side,
                "signal_source": signal_source,
                "signal_type": transition.signal_type,
                "signal_reason": transition.signal_reason,
                "signal_detail": detail,
                "decision_id": decision_id or None,
                "protocol_version": protocol_version or None,
                "signal_symbol": signal_symbol or None,
                "decision_ts": decision_ts,
                "expires_at": expires_at,
                "qty": round(qty, 8),
                "price": round(px, 2),
                "notional": round(qty * px, 2),
                "fee": round(float(fee), 6),
                "weight_from": round(float(weight_from), 6),
                "weight_to": round(float(weight_to), 6),
                "units_before": round(float(units_before), 8),
                "units_after": round(float(units_after), 8),
                "equity_before": round(float(equity_before), 6),
                "equity_after": round(float(equity_after), 6),
                "entries_raw": bool(entries_raw) if entries_raw is not None else None,
                "exits_raw": bool(exits_raw) if exits_raw is not None else None,
                "target_weight": _py_scalar(tgt_w),
                "features": feats or None,
            }
        )

    # Initial rebalance (from flat).
    w0 = float(w[0])
    if abs(w0) > 1e-12:
        fee0 = float(initial_cash) * float(fee_rate) * abs(w0 - 0.0)
        eq_after = float(initial_cash) - fee0
        units_after = eq_after * w0 / float(close[0]) if float(close[0]) != 0 else 0.0
        add_order(
            i=0,
            weight_from=0.0,
            weight_to=w0,
            equity_before=float(initial_cash),
            equity_after=eq_after,
            units_before=0.0,
            units_after=units_after,
            fee=fee0,
        )

    # Subsequent rebalances.
    for i in range(1, len(w)):
        weight_from = float(w[i - 1])
        weight_to = float(w[i])
        dw = weight_to - weight_from
        if abs(dw) < 1e-12:
            continue

        # Equity at close before paying rebalance fee (matches engine computation).
        equity_before = float(eq[i - 1]) * (1.0 + weight_from * float(r[i]))
        fee = float(equity_before) * float(fee_rate) * abs(dw)
        equity_after = float(equity_before) - float(fee)

        px = float(close[i])
        if px == 0:
            continue
        units_before = equity_before * weight_from / px
        units_after = equity_after * weight_to / px
        add_order(
            i=i,
            weight_from=weight_from,
            weight_to=weight_to,
            equity_before=equity_before,
            equity_after=equity_after,
            units_before=units_before,
            units_after=units_after,
            fee=fee,
        )

    return orders


def _format_signal_events_for_frontend(
    positions: pd.DataFrame,
    equity: pd.DataFrame,
    signals: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Create a compact, time-ordered list of signal events (entry/exit/rebalance/flip)."""
    if signals is None or len(positions) == 0 or len(equity) == 0:
        return []

    ts = positions["timestamp"].to_numpy(dtype=np.int64)
    close = positions["close"].to_numpy(dtype=np.float64)
    w = equity["weight"].to_numpy(dtype=np.float64)
    if len(w) != len(ts):
        return []

    # Default context features at signal bars (useful even when strategy doesn't return debug series).
    try:
        from backtest.indicators import rsi as _rsi, sma as _sma
    except Exception:  # pragma: no cover
        _rsi = _sma = None  # type: ignore[assignment]
    close_s = pd.Series(close)
    sma10 = _sma(close_s, 10) if _sma else pd.Series([np.nan] * len(close_s))
    sma30 = _sma(close_s, 30) if _sma else pd.Series([np.nan] * len(close_s))
    rsi14 = _rsi(close_s, 14) if _rsi else pd.Series([np.nan] * len(close_s))

    def _ret_1(i: int) -> float | None:
        if i <= 0 or i >= len(close):
            return None
        p0 = float(close[i - 1])
        if p0 == 0.0:
            return None
        return float(close[i] / p0 - 1.0)

    def _default_context(i: int) -> dict[str, Any]:
        return {
            "close": round(float(close[i]), 6),
            "ret_1": _py_scalar(_ret_1(i)),
            "sma10": _py_scalar(float(sma10.iloc[i])) if i < len(sma10) else None,
            "sma30": _py_scalar(float(sma30.iloc[i])) if i < len(sma30) else None,
            "rsi14": _py_scalar(float(rsi14.iloc[i])) if i < len(rsi14) else None,
        }

    signal_source = "unknown"
    if isinstance(signals, dict):
        if "target_weights" in signals:
            signal_source = "target_weights"
    decision_id = str((signals or {}).get("decision_id") or "") if isinstance(signals, dict) else ""
    protocol_version = str((signals or {}).get("protocol_version") or "") if isinstance(signals, dict) else ""
    signal_symbol = str((signals or {}).get("signal_symbol") or "") if isinstance(signals, dict) else ""
    decision_ts = _py_scalar((signals or {}).get("decision_ts")) if isinstance(signals, dict) else None
    expires_at = _py_scalar((signals or {}).get("expires_at")) if isinstance(signals, dict) else None

    def _bar_scalar(v: Any, idx: int, n: int) -> Any | None:
        if v is None:
            return None
        if isinstance(v, pd.Series):
            v = v.to_numpy()
        if isinstance(v, np.ndarray):
            arr = np.asarray(v)
            if arr.ndim != 1 or int(arr.shape[0]) != int(n):
                return None
            return _py_scalar(arr[idx])
        if isinstance(v, (list, tuple)):
            if len(v) != n:
                return None
            return _py_scalar(v[idx])
        return None

    def _extra_features(idx: int, n: int) -> dict[str, Any] | None:
        if not isinstance(signals, dict):
            return None
        reserved = {
            "target_weights",
            "weight_reason",
            "rebalance_reason",
            "decision_id",
            "protocol_version",
            "decision_ts",
            "expires_at",
            "signal_symbol",
            "diagnostics",
            "decision",
            "targets",
        }
        feats: dict[str, Any] = {}
        for k, v in signals.items():
            key = str(k)
            if key in reserved:
                continue
            val = _bar_scalar(v, idx, n)
            if val is None:
                continue
            feats[key] = val
        return feats or None

    def fmt_time(ms: int) -> str:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%m/%d/%Y, %I:%M:%S %p")

    events: list[dict[str, Any]] = []
    prev = 0.0
    for i in range(len(w)):
        cur = float(w[i])
        if i == 0:
            prev = 0.0
        else:
            prev = float(w[i - 1])
        if abs(cur - prev) < 1e-12:
            continue

        n = len(w)
        entries_raw = _bar_scalar(signals.get("entries") if isinstance(signals, dict) else None, i, n)  # type: ignore[arg-type]
        exits_raw = _bar_scalar(signals.get("exits") if isinstance(signals, dict) else None, i, n)  # type: ignore[arg-type]
        tgt_w = _bar_scalar(signals.get("target_weights") if isinstance(signals, dict) else None, i, n)  # type: ignore[arg-type]
        # Fix: Use 'is not None' check to avoid numpy array ambiguity error
        wr = (signals or {}).get("weight_reason")
        rr = (signals or {}).get("rebalance_reason")
        weight_reason = _bar_scalar(wr if wr is not None else rr, i, n) if isinstance(signals, dict) else None
        transition = describe_weight_transition(prev, cur, signal_source=signal_source)
        typ = transition.signal_type
        side = transition.position_side
        reason = transition.signal_reason
        if weight_reason is not None:
            detail = weight_reason
        elif tgt_w is not None:
            detail = f"target_weight={tgt_w} dw={round(float(cur) - float(prev), 6)}"
        else:
            detail = f"dw={round(float(cur) - float(prev), 6)}"

        feats = _extra_features(i, n) or {}
        for k, v in _default_context(i).items():
            feats.setdefault(k, v)

        events.append(
            {
                "i": int(i),
                "time_ms": int(ts[i]),
                "time": fmt_time(int(ts[i])),
                "type": typ,
                "side": side,
                "signal_source": signal_source,
                "signal_reason": reason,
                "signal_detail": detail,
                "decision_id": decision_id or None,
                "protocol_version": protocol_version or None,
                "signal_symbol": signal_symbol or None,
                "decision_ts": decision_ts,
                "expires_at": expires_at,
                "price": round(float(close[i]), 2),
                "weight_from": round(float(prev), 6),
                "weight_to": round(float(cur), 6),
                "entries_raw": bool(entries_raw) if entries_raw is not None else None,
                "exits_raw": bool(exits_raw) if exits_raw is not None else None,
                "target_weight": _py_scalar(tgt_w),
                "features": feats or None,
            }
        )

    return events


def _format_positions_for_frontend(
    trades: pd.DataFrame,
    positions: pd.DataFrame,
    equity: pd.DataFrame,
    signals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Summarize each non-flat holding period as a 'position' record."""
    if len(trades) == 0:
        return []

    ts = positions["timestamp"].to_numpy(dtype=np.int64)
    units = positions["units"].to_numpy(dtype=np.float64)
    w = equity["weight"].to_numpy(dtype=np.float64)

    def fmt_time(ms: int) -> str:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%m/%d/%Y, %I:%M:%S %p")

    out: list[dict[str, Any]] = []
    for _, trade in trades.iterrows():
        entry_i = int(trade["entry_i"])
        exit_i = int(trade["exit_i"])
        if entry_i < 0 or exit_i <= entry_i or exit_i >= len(ts):
            continue

        entry_ts = int(trade["entry_ts"])
        exit_ts = int(trade["exit_ts"])
        holding_ms = int(exit_ts - entry_ts)

        abs_units_slice = np.abs(units[entry_i : exit_i + 1])
        entry_qty = float(abs_units_slice[0]) if len(abs_units_slice) else 0.0
        max_qty = float(abs_units_slice.max()) if len(abs_units_slice) else entry_qty
        avg_qty = float(abs_units_slice.mean()) if len(abs_units_slice) else entry_qty

        # How many weight changes happened while in position (scale in/out).
        rebalance_count = 0
        for j in range(entry_i + 1, exit_i + 1):
            if abs(float(w[j]) - float(w[j - 1])) > 1e-12:
                rebalance_count += 1

        scale_in_qty = max(0.0, max_qty - entry_qty)

        signal_source = "unknown"
        if isinstance(signals, dict):
            if "target_weights" in signals:
                signal_source = "target_weights"

        out.append(
            {
                "side": str(trade["side"]),
                "entry_time": fmt_time(entry_ts),
                "exit_time": fmt_time(exit_ts),
                "entry_time_ms": entry_ts,
                "exit_time_ms": exit_ts,
                "signal_source": signal_source,
                "entry_price": round(float(trade["entry_price"]), 2),
                "exit_price": round(float(trade["exit_price"]), 2),
                "entry_qty": round(entry_qty, 8),
                "max_qty": round(max_qty, 8),
                "avg_qty": round(avg_qty, 8),
                "scale_in_qty": round(scale_in_qty, 8),
                "rebalance_count": int(rebalance_count),
                "pnl": round(float(trade["pnl"]), 2),
                "return_pct": round(float(trade["return"]) * 100, 2),
                "duration_bars": int(trade.get("duration_bars") or (exit_i - entry_i)),
                "holding_time_ms": holding_ms,
            }
        )

    return out


def write_run_artifacts(
    run_dir: str,
    *,
    candles: pd.DataFrame,
    equity: pd.DataFrame,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    signals: dict[str, Any] | None = None,
    metrics: dict[str, Any],
    run_meta: RunMeta,
) -> None:
    ensure_dir(run_dir)
    write_json(os.path.join(run_dir, "metrics.json"), metrics)
    write_json(os.path.join(run_dir, "run_meta.json"), asdict(run_meta))
    # Keep raw market bars as the single source of truth for charting/analysis.
    candle_cols = [col for col in ("timestamp", "open", "high", "low", "close", "volume") if col in candles.columns]
    if not candle_cols:
        raise ValueError("candles_missing_ohlcv_columns")
    write_parquet(candles[candle_cols], os.path.join(run_dir, "candles.parquet"))
    write_parquet(equity, os.path.join(run_dir, "equity.parquet"))
    write_parquet(positions, os.path.join(run_dir, "positions.parquet"))
    write_parquet(trades, os.path.join(run_dir, "trades.parquet"))

    # Convenience JSON for web UI (small runs only; MVP fetches <=1000 bars).
    # Format equity curve for frontend (wrapped in { data: [...] })
    equity_data = []
    for idx, row in equity.iterrows():
        ts_value = row["timestamp"] if "timestamp" in equity.columns else idx
        item: dict[str, Any] = {
            "timestamp": int(ts_value),
            "equity": round(float(row["equity"]), 2),
            "drawdown": round(abs(float(row["drawdown"])) * 100, 2),  # Convert to positive percentage
        }
        if "benchmark_equity" in equity.columns and pd.notna(row["benchmark_equity"]):
            item["benchmark_equity"] = round(float(row["benchmark_equity"]), 2)
        equity_data.append(item)
    write_json(os.path.join(run_dir, "equity_curve.json"), {"data": equity_data})

    # Format trades for frontend (wrapped in { trades: [...] })
    formatted_trades = _format_trades_for_frontend(trades) if len(trades) > 0 else []
    write_json(os.path.join(run_dir, "trades.json"), {"trades": formatted_trades})

    # Orders & positions summaries for UI debugging.
    try:
        fee_rate = float(metrics.get("fee_rate") or 0.0)
        initial_cash = float(metrics.get("initial_cash") or 0.0)
        if initial_cash <= 0:
            initial_cash = float(metrics.get("final_equity") or 0.0) or 10_000.0
        orders = _format_orders_for_frontend(equity, positions, fee_rate=fee_rate, initial_cash=initial_cash, signals=signals)
        write_json(os.path.join(run_dir, "orders.json"), {"orders": orders})
        positions_summary = _format_positions_for_frontend(trades, positions, equity, signals)
        write_json(os.path.join(run_dir, "positions.json"), {"positions": positions_summary})
        if signals is not None:
            signal_events = _format_signal_events_for_frontend(positions, equity, signals)
            write_json(os.path.join(run_dir, "signal_events.json"), {"events": signal_events})
    except Exception:
        # Don't fail the run if formatting fails.
        pass

    if signals is not None:
        write_json(os.path.join(run_dir, "signals.json"), serialize_signals(signals, len(equity)))
