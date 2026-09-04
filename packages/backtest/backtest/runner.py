from __future__ import annotations

import json
import os
import sys
from typing import Any

import pandas as pd

from backtest.artifacts import RunMeta, write_run_artifacts
from backtest.network_guard import install_network_guard
from backtest.protocol import normalize_signals
from backtest.load_strategy import load_callable_from_file
from backtest.spec import load_strategy_spec
from backtest.vectorized import BacktestConfig, run_backtest
from data.binance import KlinesRequest, fetch_klines
from data.okx import CandlesRequest as OkxCandlesRequest
from data.okx import fetch_candles as fetch_okx_candles
from data.okx import interval_to_okx_bar
from data.us_stock import USStockDailyRequest, fetch_us_stock_daily


def _env(name: str, default: str | None = None) -> str:
    v = os.getenv(name)
    if v is None or v == "":
        if default is None:
            raise RuntimeError(f"missing_env:{name}")
        return default
    return v


def _env_int(name: str) -> int | None:
    v = os.getenv(name)
    if v is None or v == "":
        return None
    return int(v)


def _env_json_dict(name: str) -> dict[str, Any]:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return {}
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise ValueError(f"invalid_json_env:{name}") from e
    if not isinstance(obj, dict):
        raise ValueError(f"json_env_not_dict:{name}")
    return obj


def network_guard_enabled() -> bool:
    raw = (os.getenv("NETWORK_GUARD_ENABLED") or "").strip().lower()
    if not raw:
        return True
    return raw in ("1", "true", "yes")


def _split_allowlist(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _merge_allowlist(*lists: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for lst in lists:
        for item in lst:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item.strip())
    return merged


def _us_stock_allowlist() -> list[str]:
    provider = (os.getenv("US_STOCK_PROVIDER") or "yfinance").strip().lower()
    fallback_provider = (os.getenv("US_STOCK_FALLBACK_PROVIDER") or "stooq").strip().lower()
    allow_fallback = (os.getenv("US_STOCK_FALLBACK", "1") or "").strip().lower() not in ("0", "false", "no")

    allow: list[str] = []
    if provider == "stooq":
        allow.append("stooq.com")
    else:
        allow.extend(
            [
                "query1.finance.yahoo.com",
                "query2.finance.yahoo.com",
                "finance.yahoo.com",
                "fc.yahoo.com",
            ]
        )
        if allow_fallback and fallback_provider == "stooq":
            allow.append("stooq.com")
    return allow


def build_backtest_allowlist(exchange: str) -> list[str]:
    s = (exchange or "").strip().lower()
    if s == "binance":
        return ["api.binance.com", "api.binance.us", "fapi.binance.com"]
    if s == "okx":
        return ["www.okx.com", "okx.com"]
    if s == "us_stock":
        return _us_stock_allowlist()
    return []


def _interval_ms(interval: str) -> int | None:
    s = (interval or "").strip()
    if not s:
        return None
    unit = s[-1]
    try:
        n = int(s[:-1])
    except Exception:
        return None
    if n <= 0:
        return None
    if unit == "m":
        return n * 60 * 1000
    if unit == "h":
        return n * 60 * 60 * 1000
    if unit == "d":
        return n * 24 * 60 * 60 * 1000
    if unit == "w":
        return n * 7 * 24 * 60 * 60 * 1000
    return None


def _fetch_data(exchange: str, symbol: str, interval: str, start_ms: int | None, end_ms: int | None) -> pd.DataFrame:
    if exchange == "binance":
        # MVP: single call (up to 1000 bars). Later we can paginate.
        return fetch_klines(KlinesRequest(symbol=symbol, interval=interval, start_ms=start_ms, end_ms=end_ms))

    if exchange == "okx":
        bar = interval_to_okx_bar(interval)
        est_limit = 1000
        if start_ms is not None and end_ms is not None and end_ms > start_ms:
            interval_ms = _interval_ms(interval)
            if interval_ms:
                est_limit = int((end_ms - start_ms) / interval_ms) + 10
        est_limit = max(500, min(est_limit, 50_000))
        return fetch_okx_candles(
            OkxCandlesRequest(inst_id=symbol, bar=bar, start_ms=start_ms, end_ms=end_ms, limit=est_limit)
        )

    if exchange == "us_stock":
        if interval != "1d":
            raise ValueError("us_stock_only_supports_1d")
        return fetch_us_stock_daily(USStockDailyRequest(symbol=symbol, start_ms=start_ms, end_ms=end_ms))

    raise ValueError(f"unsupported_exchange:{exchange}")


def main() -> int:
    strategy_id = _env("STRATEGY_ID")
    version_id = _env("VERSION_ID")
    run_id = _env("RUN_ID")

    exchange = _env("EXCHANGE", "binance")
    symbol = _env("SYMBOL", "BTCUSDT")
    interval = _env("INTERVAL", "1h")
    start_ms = _env_int("START_MS")
    end_ms = _env_int("END_MS")

    extra_hosts = _split_allowlist(os.getenv("NETWORK_ALLOWLIST", ""))
    allowlist = _merge_allowlist(build_backtest_allowlist(exchange), extra_hosts)
    if allowlist:
        os.environ["NETWORK_ALLOWLIST"] = ",".join(allowlist)
    install_network_guard(allowlist=allowlist, enabled=network_guard_enabled())

    fee_rate = float(os.getenv("FEE_RATE", "0.0004"))
    slippage_bps = float(os.getenv("SLIPPAGE_BPS", "0"))
    initial_cash = float(os.getenv("INITIAL_CASH", "10000"))
    run_params = _env_json_dict("RUN_PARAMS_JSON")

    workspaces_dir = _env("WORKSPACES_DIR", "/workspaces")

    version_dir = os.path.join(workspaces_dir, strategy_id, "versions", version_id)
    run_dir = os.path.join(workspaces_dir, strategy_id, "runs", run_id)

    spec_path = os.path.join(version_dir, "strategy_spec.yaml")
    strategy_path = os.path.join(version_dir, "strategy.py")

    print(f"[runner] strategy_id={strategy_id} version_id={version_id} run_id={run_id}")
    print(f"[runner] data={exchange}:{symbol}:{interval} start_ms={start_ms} end_ms={end_ms}")
    print(f"[runner] version_dir={version_dir}")
    print(f"[runner] run_dir={run_dir}")

    spec = load_strategy_spec(spec_path)
    if spec.engine_type != "vectorized":
        raise ValueError(f"unsupported_engine_type:{spec.engine_type}")

    data = _fetch_data(exchange, symbol, interval, start_ms, end_ms)
    data = data.sort_values("timestamp").reset_index(drop=True)
    if len(data) < 3:
        if exchange == "us_stock":
            raise ValueError("us_stock_no_data_or_not_enough_bars")
        raise ValueError("not_enough_bars")

    generate_signals = load_callable_from_file(strategy_path, spec.entrypoint.function)
    merged_params = dict(spec.params)
    merged_params.update(run_params)
    signals = generate_signals(data.copy(), dict(merged_params))  # user code may mutate
    if not isinstance(signals, dict):
        raise ValueError("strategy_return_must_be_dict")
    signals = normalize_signals(
        signals,
        n=len(data),
        mode=spec.signal_mode,
        symbol=symbol,
        now_ts_ms=end_ms,
    )

    result = run_backtest(
        data,
        signals=signals,
        interval=interval,
        config=BacktestConfig(initial_cash=initial_cash, fee_rate=fee_rate, slippage_bps=slippage_bps),
    )

    run_meta = RunMeta(
        strategy_id=strategy_id,
        version_id=version_id,
        run_id=run_id,
        dataset={"exchange": exchange, "symbol": symbol, "interval": interval, "start_ms": start_ms, "end_ms": end_ms},
        params=dict(merged_params),
        engine_type=spec.engine_type,
        signal_mode=spec.signal_mode,
        protocol_version=str(signals.get("protocol_version") or ""),
        decision_id=str(signals.get("decision_id") or ""),
        signal_symbol=str(signals.get("signal_symbol") or symbol),
    )

    write_run_artifacts(
        run_dir,
        candles=data,
        equity=result.equity,
        positions=result.positions,
        trades=result.trades,
        signals=signals,
        metrics=result.metrics,
        run_meta=run_meta,
    )

    print("[runner] wrote artifacts")
    print(json.dumps(result.metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[runner] error: {type(e).__name__}: {e}", file=sys.stderr)
        raise
