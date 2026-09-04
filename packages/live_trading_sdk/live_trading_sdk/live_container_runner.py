"""Isolated Live Trading Container Runner.

Runs inside an ephemeral/daemon Docker sandbox.
Loads user strategy code, ingests public market candles, and dispatches
trading intents (Broker Protocol) back to the platform risk gateway.
Never holds exchange API secrets, encryption keys, or database credentials.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import signal
import sys
import time
from typing import Any, Callable, Optional

import pandas as pd
import requests

from live_trading_sdk.strategy import Broker, LiveStrategy
from live_trading_sdk.types import Bar, StrategyContext


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [live-container] %(message)s",
)
logger = logging.getLogger("live_container_runner")


class ContainerBroker(Broker):
    """Broker implementation that sends trading intents to the API risk gateway."""

    def __init__(self, api_base_url: str, session_id: str, default_symbol: str) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.session_id = session_id
        self.default_symbol = default_symbol
        self._last_price_cache: dict[str, float] = {}

    def set_last_price(self, symbol: str, price: float) -> None:
        if price > 0:
            self._last_price_cache[symbol] = price

    def set_target_allocation(
        self,
        target: float,
        *,
        reason: str | None = None,
        symbol: str | None = None,
    ) -> None:
        sym = symbol or self.default_symbol
        url = f"{self.api_base_url}/api/internal/trading/{self.session_id}/intent"
        payload = {
            "action": "set_target_allocation",
            "target": float(target),
            "reason": reason or "",
            "symbol": sym,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10.0)
            if not resp.ok:
                logger.warning(f"Intent submission failed: {resp.status_code} {resp.text}")
            else:
                logger.info(f"Target allocation intent submitted: {sym} -> {target} ({reason})")
        except Exception as e:
            logger.error(f"Failed to submit target allocation intent: {e}")

    def market_order(
        self,
        side: str,
        size: float,
        *,
        reason: str | None = None,
        symbol: str | None = None,
    ) -> None:
        sym = symbol or self.default_symbol
        url = f"{self.api_base_url}/api/internal/trading/{self.session_id}/intent"
        payload = {
            "action": "market_order",
            "side": str(side).lower(),
            "size": float(size),
            "reason": reason or "",
            "symbol": sym,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10.0)
            if not resp.ok:
                logger.warning(f"Market order intent failed: {resp.status_code} {resp.text}")
            else:
                logger.info(f"Market order intent submitted: {side} {size} {sym} ({reason})")
        except Exception as e:
            logger.error(f"Failed to submit market order intent: {e}")

    def current_position(self, symbol: str | None = None) -> float:
        sym = symbol or self.default_symbol
        url = f"{self.api_base_url}/api/internal/trading/{self.session_id}/state"
        try:
            resp = requests.get(url, params={"symbol": sym}, timeout=5.0)
            if resp.ok:
                data = resp.json()
                return float(data.get("position_size", 0.0) or 0.0)
        except Exception as e:
            logger.debug(f"Failed to fetch position state: {e}")
        return 0.0

    def last_price(self, symbol: str | None = None) -> float:
        sym = symbol or self.default_symbol
        cached = self._last_price_cache.get(sym)
        if cached is not None and cached > 0:
            return cached
        url = f"{self.api_base_url}/api/internal/trading/{self.session_id}/state"
        try:
            resp = requests.get(url, params={"symbol": sym}, timeout=5.0)
            if resp.ok:
                data = resp.json()
                price = float(data.get("last_price", 0.0) or 0.0)
                if price > 0:
                    self._last_price_cache[sym] = price
                    return price
        except Exception:
            pass
        return 0.0


def _fetch_candles(exchange: str, symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
    """Fetch public market candles without needing API keys."""
    ex = (exchange or "okx").lower()
    if ex == "binance":
        from data.binance import KlinesRequest, fetch_klines

        norm_sym = symbol.upper().replace("-SWAP", "").replace("/", "").replace("-", "")
        df = fetch_klines(KlinesRequest(symbol=norm_sym, interval=interval, limit=limit))
        return df.tail(limit).reset_index(drop=True)

    # OKX default
    from data.okx import CandlesRequest, fetch_candles, interval_to_okx_bar

    bar = interval_to_okx_bar(interval)
    df = fetch_candles(CandlesRequest(inst_id=symbol, bar=bar, limit=limit))
    return df.tail(limit).reset_index(drop=True)


def _load_user_strategy(strategy_dir: str) -> tuple[Optional[LiveStrategy], Optional[Callable], dict[str, Any]]:
    """Inspect and load strategy_live.py or strategy.py."""
    live_file = os.path.join(strategy_dir, "strategy_live.py")
    base_file = os.path.join(strategy_dir, "strategy.py")
    spec_file = os.path.join(strategy_dir, "strategy_spec.yaml")

    params: dict[str, Any] = {}
    if os.path.isfile(spec_file):
        try:
            import yaml

            with open(spec_file, "r", encoding="utf-8") as f:
                spec_data = yaml.safe_load(f) or {}
            params = spec_data.get("params") or {}
        except Exception as e:
            logger.warning(f"Could not parse strategy_spec.yaml: {e}")

    target_file = live_file if os.path.isfile(live_file) else base_file
    if not os.path.isfile(target_file):
        raise FileNotFoundError(f"Strategy file not found in {strategy_dir}")

    module_name = "user_strategy"
    spec = importlib.util.spec_from_file_location(module_name, target_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {target_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Check for LiveStrategy object or factory
    candidates = []
    for name in ("create_live_strategy", "build_live_strategy", "create_strategy"):
        fn = getattr(mod, name, None)
        if callable(fn):
            try:
                candidates.append(fn())
            except Exception:
                pass
    for name in ("LiveStrategy", "Strategy", "ExampleLiveStrategy"):
        obj = getattr(mod, name, None)
        if isinstance(obj, type):
            try:
                candidates.append(obj())
            except Exception:
                pass

    for candidate in candidates:
        if candidate and hasattr(candidate, "on_bar"):
            logger.info("Loaded LiveStrategy class/instance")
            return candidate, None, params

    # Check for functional generate_signals
    fn = getattr(mod, "generate_signals", None)
    if callable(fn):
        logger.info("Loaded functional generate_signals entrypoint")
        return None, fn, params

    raise ValueError("Strategy has neither on_bar hook nor generate_signals function")


def main() -> None:
    session_id = os.getenv("SESSION_ID")
    strategy_id = os.getenv("STRATEGY_ID")
    api_url = os.getenv("API_INTERNAL_URL", "http://api:8000")
    workspaces_dir = os.getenv("WORKSPACES_DIR", "/workspaces")
    exchange = os.getenv("EXCHANGE", "okx")
    symbol = os.getenv("SYMBOL", "BTC-USDT")
    interval = os.getenv("INTERVAL", "1m")
    poll_seconds = float(os.getenv("POLL_SECONDS", "5.0"))

    if not session_id or not strategy_id:
        logger.error("Missing required environment variables: SESSION_ID, STRATEGY_ID")
        sys.exit(1)

    logger.info(f"Starting live container runner for session={session_id}, strategy={strategy_id}, symbol={symbol}/{interval}")

    strategy_dir = os.path.join(workspaces_dir, strategy_id, "strategy")
    live_strategy, signals_fn, params = _load_user_strategy(strategy_dir)

    broker = ContainerBroker(api_url, session_id, default_symbol=symbol)

    if live_strategy and hasattr(live_strategy, "initialize"):
        ctx = StrategyContext(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            symbols=[symbol],
            intervals=[interval],
            params=params,
        )
        try:
            live_strategy.initialize(ctx)
            logger.info("Strategy initialized successfully")
        except Exception as e:
            logger.error(f"Strategy initialize failed: {e}")

    stop_requested = False

    def _sig_handler(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        stop_requested = True

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)

    last_bar_ts = 0
    last_heartbeat = 0.0

    while not stop_requested:
        now = time.time()
        # Periodic heartbeat and session status verification
        if now - last_heartbeat >= 15.0:
            try:
                state_resp = requests.get(
                    f"{api_url}/api/internal/trading/{session_id}/state",
                    timeout=3.0,
                )
                if state_resp.status_code == 404:
                    logger.info("Session no longer exists, exiting container runner.")
                    break
                if state_resp.ok:
                    status = state_resp.json().get("status", "")
                    if status and status not in ("RUNNING", "STARTING", "TradingSessionStatus.RUNNING", "TradingSessionStatus.STARTING"):
                        logger.info(f"Session is {status}, exiting container runner.")
                        break

                requests.post(
                    f"{api_url}/api/internal/trading/{session_id}/heartbeat",
                    json={"timestamp": int(now * 1000)},
                    timeout=3.0,
                )
                last_heartbeat = now
            except Exception as e:
                logger.debug(f"Heartbeat check error: {e}")

        try:
            candles = _fetch_candles(exchange, symbol, interval, limit=100)
            if not candles.empty:
                latest_row = candles.iloc[-1]
                bar_ts = int(latest_row["timestamp"])
                close_price = float(latest_row["close"])
                broker.set_last_price(symbol, close_price)

                if bar_ts > last_bar_ts:
                    last_bar_ts = bar_ts
                    bar = Bar(
                        symbol=symbol,
                        interval=interval,
                        timestamp=bar_ts,
                        open=float(latest_row["open"]),
                        high=float(latest_row["high"]),
                        low=float(latest_row["low"]),
                        close=close_price,
                        volume=float(latest_row["volume"]),
                    )

                    if live_strategy:
                        try:
                            live_strategy.on_bar(bar, candles.copy(), broker)
                        except Exception as e:
                            logger.error(f"Error in on_bar: {e}")
                            if hasattr(live_strategy, "on_error"):
                                try:
                                    live_strategy.on_error(e, broker)
                                except Exception:
                                    pass
                    elif signals_fn:
                        try:
                            raw_signals = signals_fn(candles.copy(), dict(params))
                            weights = None
                            if isinstance(raw_signals, dict):
                                weights = raw_signals.get("target_weights", raw_signals.get("target_weight"))
                            elif isinstance(raw_signals, pd.DataFrame):
                                for col in ("target_weight", "target_weights", "signal"):
                                    if col in raw_signals.columns:
                                        weights = raw_signals[col].to_numpy()
                                        break
                            if weights is not None and len(weights) > 0:
                                w = float(weights[-1])
                                broker.set_target_allocation(w, reason="signals_target_weights", symbol=symbol)
                        except Exception as e:
                            logger.error(f"Error in generate_signals: {e}")
        except Exception as e:
            logger.warning(f"Error during market poll cycle: {e}")

        time.sleep(poll_seconds)

    logger.info("Live container runner stopped cleanly")


if __name__ == "__main__":
    main()
