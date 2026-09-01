"""
Stable5 screening job for strategy templates.

Runs real backtests on OKX perpetuals (BTC/ETH) using both 1h and 4h data,
then stores per-run metrics and an aggregated Stable5 summary on the template.
"""

from __future__ import annotations

import importlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd

from sqlalchemy.orm import Session

from backtest.live_strategy_adapter import LiveAdapterConfig, generate_signals_from_live_strategy
from backtest.presets import Stable5Preset
from backtest.screening import ScreeningConfig, passes_stable5_gate, summarize_backtest_for_screening
from backtest.vectorized import BacktestConfig, run_backtest
from data.okx import CandlesRequest, fetch_candles, interval_to_okx_bar

from control_plane.models import Job, StrategyTemplate, TemplatePerformanceRun

logger = logging.getLogger(__name__)

_BUILTIN_GENERATE_SIGNALS_CODE: dict[str, str] = {
    "tmpl-moving-average-crossover": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Moving Average Crossover Strategy"""
    close = data["close"]

    short_window = int(params.get("short_window", 20))
    long_window = int(params.get("long_window", 50))

    short_ma = close.rolling(short_window).mean()
    long_ma = close.rolling(long_window).mean()

    entries = (short_ma > long_ma) & (short_ma.shift(1) <= long_ma.shift(1))
    exits = (short_ma < long_ma) & (short_ma.shift(1) >= long_ma.shift(1))

    return {
        "entries": entries.fillna(False).to_numpy(),
        "exits": exits.fillna(False).to_numpy()
    }
''',
    "tmpl-rsi-oversold": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """RSI Mean Reversion Strategy"""
    close = data["close"]

    rsi_period = int(params.get("rsi_period", 14))
    oversold = float(params.get("oversold", 30))
    overbought = float(params.get("overbought", 70))

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    entries = (rsi < oversold) & (rsi.shift(1) >= oversold)
    exits = (rsi > overbought) & (rsi.shift(1) <= overbought)

    return {
        "entries": entries.fillna(False).to_numpy(),
        "exits": exits.fillna(False).to_numpy()
    }
''',
    "tmpl-bollinger-breakout": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Bollinger Band Breakout Strategy"""
    close = data["close"]

    bb_period = int(params.get("bb_period", 20))
    bb_std = float(params.get("bb_std", 2))

    sma = close.rolling(bb_period).mean()
    std = close.rolling(bb_period).std()
    upper = sma + (bb_std * std)

    entries = (close > upper) & (close.shift(1) <= upper.shift(1))
    exits = (close < sma) & (close.shift(1) >= sma.shift(1))

    return {
        "entries": entries.fillna(False).to_numpy(),
        "exits": exits.fillna(False).to_numpy()
    }
''',
}


def _import_factory(code_snapshot: dict[str, Any]) -> Callable[[], Any]:
    module_path = str(code_snapshot.get("module") or "").strip()
    entrypoint = str(code_snapshot.get("entrypoint") or "").strip()
    if not module_path or not entrypoint:
        raise ValueError("template_missing_code_snapshot")
    module = importlib.import_module(module_path)
    factory = getattr(module, entrypoint, None)
    if not callable(factory):
        raise ValueError(f"template_entrypoint_not_callable:{module_path}:{entrypoint}")
    return factory


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_number(value: Any, *, digits: int = 2, suffix: str = "", na: str = "NA") -> str:
    if value is None:
        return f"{na}{suffix}"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return f"{na}{suffix}"
    return f"{number:.{digits}f}{suffix}"


def run_template_stable5_screening(db: Session, rds, job: Job) -> None:
    preset = Stable5Preset()
    screening_cfg = ScreeningConfig(max_drawdown_pct=5.0, min_years=1.0, rolling_window_days=30)
    run_date = _now_utc()

    end_time = run_date - timedelta(days=1)
    start_time = end_time - timedelta(days=int(preset.min_days))
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    template_ids = job.payload.get("template_ids") if isinstance(job.payload, dict) else None
    limit = job.payload.get("limit") if isinstance(job.payload, dict) else None

    q = (
        db.query(StrategyTemplate)
        .filter(StrategyTemplate.is_public == True)
        .order_by(StrategyTemplate.updated_at.desc())
    )
    if isinstance(template_ids, list) and template_ids:
        q = q.filter(StrategyTemplate.id.in_([str(x) for x in template_ids]))
    if isinstance(limit, int) and limit > 0:
        q = q.limit(int(limit))
    templates = q.all()

    _publish_log(rds, job.id, f"[STABLE5] Screening templates={len(templates)} range_days={preset.min_days}")

    candles_cache: dict[tuple[str, str], pd.DataFrame] = {}
    for symbol in preset.symbols:
        for interval in preset.intervals:
            bar = interval_to_okx_bar(interval)
            approx_limit = _estimate_limit(interval=interval, start_ms=start_ms, end_ms=end_ms)
            _publish_log(rds, job.id, f"[STABLE5] Fetching candles {symbol} {interval} (limit≈{approx_limit})")
            try:
                candles = fetch_candles(
                    CandlesRequest(
                        inst_id=symbol,
                        bar=bar,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        limit=approx_limit,
                    )
                )
            except Exception as exc:
                _publish_log(
                    rds,
                    job.id,
                    f"[STABLE5] ERROR fetching candles {symbol} {interval}: {type(exc).__name__}: {exc}",
                )
                candles = pd.DataFrame()
            candles_cache[(symbol, interval)] = candles

    for template in templates:
        try:
            supports_builtin = template.template_type == "builtin" and template.id in _BUILTIN_GENERATE_SIGNALS_CODE
            if not template.code_snapshot and not supports_builtin:
                continue
            if isinstance(template.supported_exchanges, list) and "okx" not in (template.supported_exchanges or []):
                continue

            _publish_log(rds, job.id, f"[STABLE5] Template: {template.id} {template.name}")

            factory = _import_factory(template.code_snapshot) if template.code_snapshot else None
            template_params = dict(template.config_snapshot or {})

            adapter_base = LiveAdapterConfig(
                exchange=preset.exchange,
                symbol=preset.symbols[0],
                interval=preset.intervals[0],
                history_bars=int(template_params.get("live_history_bars", 200)),
                max_position_pct=float(template_params.get("default_max_position_pct", 10.0)),
                stop_loss_pct=float(template_params.get("default_stop_loss_pct", 5.0)),
            )

            per_symbol: dict[str, dict[str, dict[str, Any]]] = {}
            run_summaries: list[dict[str, Any]] = []

            for symbol in preset.symbols:
                per_symbol[symbol] = {}
                for interval in preset.intervals:
                    candles = candles_cache.get((symbol, interval))

                    if candles.empty:
                        summary = {"is_valid": False, "reason": "no_data"}
                        per_symbol[symbol][interval] = summary
                        continue

                    adapter = LiveAdapterConfig(
                        exchange=adapter_base.exchange,
                        symbol=symbol,
                        interval=interval,
                        history_bars=adapter_base.history_bars,
                        max_position_pct=adapter_base.max_position_pct,
                        stop_loss_pct=adapter_base.stop_loss_pct,
                    )
                    if factory is not None:
                        signals = generate_signals_from_live_strategy(factory, candles, params=template_params, adapter=adapter)
                    else:
                        signals = _generate_signals_from_builtin(template_id=template.id, data=candles, params=template_params)
                        signals = _scale_signals(signals, scale=adapter.max_position_pct / 100.0)
                    bt = run_backtest(
                        candles,
                        signals=signals,
                        interval=interval,
                        config=BacktestConfig(
                            initial_cash=10_000.0,
                            fee_rate=preset.fee_rate,
                            slippage_bps=preset.slippage_bps,
                        ),
                    )

                    summary = summarize_backtest_for_screening(
                        bt.equity,
                        bt.metrics,
                        interval=interval,
                        config=screening_cfg,
                    )
                    summary["stable5_pass"] = passes_stable5_gate(summary, max_drawdown_pct=screening_cfg.max_drawdown_pct)
                    per_symbol[symbol][interval] = summary
                    run_summaries.append(summary)

                    metrics = dict(bt.metrics or {})
                    metrics["equity_curve"] = _extract_equity_curve(bt.equity, max_points=1500)
                    metrics["trades"] = _extract_trades(bt.trades, max_trades=500)
                    metrics.update(
                        {
                            "annualized_return_pct": summary.get("annualized_return_pct"),
                            "calmar_ratio": summary.get("calmar_ratio"),
                            "rolling_positive_ratio": summary.get("rolling_positive_ratio"),
                            "stable5_pass": summary.get("stable5_pass"),
                        }
                    )

                    perf = TemplatePerformanceRun(
                        id=str(uuid.uuid4()),
                        template_id=template.id,
                        run_date=run_date,
                        exchange=preset.exchange,
                        symbol=symbol,
                        interval=interval,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        metrics=metrics,
                        status="succeeded" if summary.get("is_valid") else "failed",
                    )
                    db.add(perf)
                    db.flush()

                    _publish_log(
                        rds,
                        job.id,
                        f"[STABLE5] {template.name} {symbol} {interval} "
                        f"ret={_fmt_number(summary.get('total_return_pct'), suffix='%')} "
                        f"dd={_fmt_number(summary.get('max_drawdown_pct'), suffix='%')} "
                        f"pass={bool(summary.get('stable5_pass'))}",
                    )

            stable5_summary = _aggregate_stable5(
                per_symbol=per_symbol,
                preset=preset,
                screening_cfg=screening_cfg,
                run_date=run_date,
            )

            template.backtest_summary = dict(template.backtest_summary or {})
            template.backtest_summary["stable5"] = stable5_summary
            template.updated_at = _now_utc()
            db.flush()
            db.commit()

        except Exception as exc:
            logger.error("Stable5 screening failed for template %s: %s", template.id, exc, exc_info=True)
            _publish_log(rds, job.id, f"[STABLE5] ERROR template={template.id}: {type(exc).__name__}: {exc}")
            db.rollback()


def _generate_signals_from_builtin(*, template_id: str, data, params: dict[str, Any]) -> dict[str, Any]:
    code = _BUILTIN_GENERATE_SIGNALS_CODE.get(template_id)
    if not code:
        raise ValueError(f"unsupported_builtin_template:{template_id}")
    namespace: dict[str, Any] = {}
    exec(code, namespace, namespace)  # trusted builtin snippets
    fn = namespace.get("generate_signals")
    if not callable(fn):
        raise RuntimeError(f"builtin_generate_signals_missing:{template_id}")
    return fn(data.copy(), dict(params))


def _scale_signals(signals: dict[str, Any], *, scale: float) -> dict[str, Any]:
    scale = max(0.0, min(1.0, float(scale)))
    if scale == 1.0:
        return signals
    if "target_weights" in signals:
        w = np.asarray(signals["target_weights"], dtype=np.float64)
        return {"target_weights": np.clip(w, -1.0, 1.0) * scale}
    if "entries" in signals and "exits" in signals:
        entries = np.asarray(signals["entries"], dtype=bool)
        exits = np.asarray(signals["exits"], dtype=bool)
        n = int(len(entries))
        w = np.zeros(n, dtype=np.float64)
        in_pos = False
        for i in range(n):
            if not in_pos and bool(entries[i]):
                in_pos = True
            elif in_pos and bool(exits[i]):
                in_pos = False
            w[i] = 1.0 if in_pos else 0.0
        return {"target_weights": w * scale}
    return signals


def _aggregate_stable5(
    *,
    per_symbol: dict[str, dict[str, dict[str, Any]]],
    preset: Stable5Preset,
    screening_cfg: ScreeningConfig,
    run_date: datetime,
) -> dict[str, Any]:
    symbol_gates: dict[str, dict[str, Any]] = {}
    calmar_min = None
    pos_ratio_min = None
    dd_worst = 0.0
    return_worst = None

    qualifies = True
    for symbol, interval_map in per_symbol.items():
        summaries = [interval_map.get(i) for i in preset.intervals]
        valid = all(s and s.get("is_valid") for s in summaries)
        if not valid:
            qualifies = False
            symbol_gates[symbol] = {"passes": False, "reason": "invalid_run"}
            continue

        mdd_symbol = max(float(interval_map[i]["max_drawdown_pct"]) for i in preset.intervals)
        ret_min_symbol = min(float(interval_map[i]["total_return_pct"]) for i in preset.intervals)
        passes = (mdd_symbol <= screening_cfg.max_drawdown_pct) and (ret_min_symbol > 0.0)
        if not passes:
            qualifies = False

        symbol_gates[symbol] = {
            "passes": passes,
            "mdd_pct": mdd_symbol,
            "min_return_pct": ret_min_symbol,
        }

        dd_worst = max(dd_worst, mdd_symbol)
        return_worst = ret_min_symbol if return_worst is None else min(return_worst, ret_min_symbol)

        for i in preset.intervals:
            cal = float(interval_map[i].get("calmar_ratio") or 0.0)
            pos = float(interval_map[i].get("rolling_positive_ratio") or 0.0)
            calmar_min = cal if calmar_min is None else min(calmar_min, cal)
            pos_ratio_min = pos if pos_ratio_min is None else min(pos_ratio_min, pos)

    calmar_min = float(calmar_min or 0.0)
    pos_ratio_min = float(pos_ratio_min or 0.0)
    score = float(np.log1p(max(calmar_min, 0.0)) * (0.5 + 0.5 * pos_ratio_min))

    return {
        "generated_at": run_date.isoformat(),
        "exchange": preset.exchange,
        "symbols": list(preset.symbols),
        "intervals": list(preset.intervals),
        "fee_rate": preset.fee_rate,
        "slippage_bps": preset.slippage_bps,
        "gate": {
            "max_drawdown_pct": screening_cfg.max_drawdown_pct,
            "min_days": preset.min_days,
        },
        "per_symbol": per_symbol,
        "symbol_gates": symbol_gates,
        "qualifies": qualifies,
        "worst": {
            "max_drawdown_pct": dd_worst,
            "min_return_pct": return_worst,
            "calmar_min": calmar_min,
            "rolling_positive_ratio_min": pos_ratio_min,
        },
        "score": score,
    }


def _estimate_limit(*, interval: str, start_ms: int, end_ms: int) -> int:
    s = (interval or "").strip()
    if not s or end_ms <= start_ms:
        return 1000
    unit = s[-1]
    try:
        n = int(s[:-1])
    except Exception:
        return 1000
    if n <= 0:
        return 1000
    if unit == "h":
        interval_ms = n * 60 * 60 * 1000
    elif unit == "m":
        interval_ms = n * 60 * 1000
    elif unit == "d":
        interval_ms = n * 24 * 60 * 60 * 1000
    else:
        return 1000
    approx = int((end_ms - start_ms) / interval_ms) + 10
    return max(500, min(approx, 50_000))


def _extract_equity_curve(equity_df: pd.DataFrame, *, max_points: int = 1500) -> list[list[int | float]]:
    if equity_df is None or equity_df.empty:
        return []
    ts = equity_df["timestamp"].to_numpy(dtype=np.int64)
    eq = equity_df["equity"].to_numpy(dtype=np.float64)
    n = int(len(ts))
    if n <= 0:
        return []
    max_points = int(max(50, max_points))
    if n <= max_points:
        return [[int(ts[i]), float(eq[i])] for i in range(n)]
    step = max(1, int(np.ceil(n / max_points)))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return [[int(ts[i]), float(eq[i])] for i in idx]


def _extract_trades(trades_df: pd.DataFrame, *, max_trades: int = 500) -> list[dict[str, Any]]:
    if trades_df is None or trades_df.empty:
        return []
    max_trades = int(max(0, max_trades))
    df = trades_df
    if max_trades and len(df) > max_trades:
        df = df.tail(max_trades).copy()
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            ret = float(row.get("return", 0.0))
        except Exception:
            ret = 0.0
        out.append(
            {
                "side": str(row.get("side") or ""),
                "entry_time_ms": int(row.get("entry_ts")),
                "exit_time_ms": int(row.get("exit_ts")),
                "entry_price": float(row.get("entry_price")),
                "exit_price": float(row.get("exit_price")),
                "return_pct": float(ret) * 100.0,
                "pnl": float(row.get("pnl", 0.0)),
                "duration_bars": int(row.get("duration_bars", 0)),
            }
        )
    return out


def _publish_log(rds, job_id: str, message: str) -> None:
    try:
        from control_plane.queue import job_log_channel

        rds.publish(job_log_channel(job_id), message)
        rds.publish(f"job:{job_id}:logs", message)
        tail_key = f"jobs:logtail:v1:{job_id}"
        rds.rpush(tail_key, message)
        rds.ltrim(tail_key, -200, -1)
        rds.expire(tail_key, 86400)
        rds.setex(f"jobs:lastlog:v1:{job_id}", 86400, message)
    except Exception:
        pass
