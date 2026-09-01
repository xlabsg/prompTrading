"""Background runner that executes user strategies in real time."""

from __future__ import annotations

import importlib.util
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Optional, List

import pandas as pd
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from backtest.execution_core import describe_weight_transition
from backtest.protocol import normalize_signals
from backtest.spec import load_strategy_spec
from control_plane.enums import LogLevel, SignalStatus, TradingSessionStatus
from control_plane.models import StrategyExchangeAccount, StrategySignal, TradingConfig, TradingSession
from app.crypto import decrypt_credential
from app.settings import settings
from app.trading_engine.executor import OrderExecutor
from app.trading_engine.live_broker import LiveBroker
from app.trading_engine.logging_utils import log_trading_event
from app.trading_engine.okx_ws import CandleBuffer, OKXWSManager
from data.okx import CandlesRequest, fetch_candles, interval_to_okx_bar

logger = logging.getLogger(__name__)

try:  # SDK is vendored inside the repo, but be defensive during upgrades.
    from live_trading_sdk import LiveStrategy as LiveStrategyProtocol, StrategyContext
except Exception:  # pragma: no cover - fallback for CI without SDK install
    LiveStrategyProtocol = None  # type: ignore
    StrategyContext = None  # type: ignore


DEFAULT_BAR_INTERVAL = os.getenv("LIVE_TRADING_DEFAULT_BAR", "1m")
DEFAULT_HISTORY_BARS = int(os.getenv("LIVE_TRADING_HISTORY_BARS", "150"))
MIN_POLL_SECONDS = float(os.getenv("LIVE_TRADING_MIN_POLL_SECONDS", "5"))


def _safe_module_name(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    return "strategy_" + "".join(ch if ch.isalnum() else "_" for ch in base)


@dataclass
class StrategyArtifacts:
    module: ModuleType
    signals_fn: Optional[Callable[[pd.DataFrame, dict[str, Any]], dict[str, Any]]]
    live_strategy: Optional[Any]
    params: dict[str, Any]
    entry_fn: str


@dataclass(frozen=True)
class CandleEvent:
    symbol: str
    interval: str
    timestamp: int


def _fetch_recent_candles(inst_id: str, interval: str, limit: int) -> pd.DataFrame:
    if limit <= 0:
        raise ValueError("limit must be positive")

    def interval_ms(value: str) -> int | None:
        s = (value or "").strip()
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

    bar = interval_to_okx_bar(interval)
    end_ms = int(time.time() * 1000)
    start_ms = None
    step_ms = interval_ms(interval)
    if step_ms:
        start_ms = end_ms - int(step_ms * (limit + 5))

    df = fetch_candles(
        CandlesRequest(
            inst_id=inst_id,
            bar=bar,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=int(limit),
        )
    )
    return df.tail(int(limit)).reset_index(drop=True)


class StrategyRunner:
    """Runs per-session strategy logic in a dedicated thread."""

    def __init__(self, session_id: str, config: TradingConfig, account: StrategyExchangeAccount):
        self.session_id = session_id
        self.strategy_id = config.strategy_id
        self.config = config
        self.account = account
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._artifacts: Optional[StrategyArtifacts] = None
        self._workspaces_dir = settings.workspaces_dir
        self._bar_interval = DEFAULT_BAR_INTERVAL
        self._history_bars = DEFAULT_HISTORY_BARS
        self._symbols: list[str] = []
        self._intervals: list[str] = []
        self._event_queue: queue.Queue[CandleEvent] = queue.Queue()
        self._streams: dict[tuple[str, str], CandleBuffer] = {}
        self._ws_manager = OKXWSManager.instance()
        self._last_bar_ts: dict[tuple[str, str], int] = {}
        self._subscriptions: dict[tuple[str, str], tuple[Any, Callable[[List[Any]], None]]] = {}
        self._last_target_by_stream: dict[tuple[str, str], float] = {}
        self._seen_decision_ids: set[str] = set()
        self._broker = LiveBroker(
            strategy_id=self.strategy_id,
            session_id=session_id,
            config=config,
            okx_client=self._create_okx_client(account),
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name=f"strategy-runner-{self.session_id[:8]}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._stop_streams()

    # ------------------------------------------------------------------
    def _create_okx_client(self, account: StrategyExchangeAccount):
        from okx_sdk import OKXClient

        api_key = (account.api_key_encrypted or "").strip()
        secret = decrypt_credential(account.api_secret_encrypted).strip()
        passphrase = decrypt_credential(account.api_passphrase_encrypted or "").strip()
        logger.warning({
            "event": "runner_credentials",
            "strategy_id": self.strategy_id,
            "session_id": self.session_id,
            "api_key_len": len(api_key),
            "secret_len": len(secret),
            "passphrase_len": len(passphrase),
        })
        return OKXClient(
            api_key=api_key,
            secret_key=secret,
            passphrase=passphrase,
            simulated=settings.okx_simulated_trading,
        )

    def _load_strategy(self) -> StrategyArtifacts:
        strategy_dir = os.path.join(self._workspaces_dir, self.strategy_id, "strategy")
        spec_path = os.path.join(strategy_dir, "strategy_spec.yaml")
        strategy_path = os.path.join(strategy_dir, "strategy.py")
        strategy_live_path = os.path.join(strategy_dir, "strategy_live.py")
        spec = load_strategy_spec(spec_path)

        active_strategy_path = strategy_live_path if os.path.isfile(strategy_live_path) else strategy_path
        module_name = _safe_module_name(active_strategy_path)
        spec_obj = importlib.util.spec_from_file_location(module_name, active_strategy_path)
        if spec_obj is None or spec_obj.loader is None:
            raise RuntimeError(f"failed_to_load_strategy:{active_strategy_path}")
        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)  # type: ignore[union-attr]

        live_strategy = self._build_live_strategy(module)
        signals_fn = None
        if live_strategy is None:
            candidate = getattr(module, spec.entrypoint.function, None)
            if not callable(candidate):
                raise AttributeError(f"strategy_missing_entrypoint:{spec.entrypoint.function}")
            signals_fn = candidate

        params = dict(spec.params or {})
        bar_interval = params.get("live_bar_interval") or DEFAULT_BAR_INTERVAL
        history_bars = int(params.get("live_history_bars") or DEFAULT_HISTORY_BARS)
        self._bar_interval = str(bar_interval)
        self._history_bars = max(50, history_bars)
        self._symbols = [s for s in (self.config.symbols or [self.config.symbol]) if s]
        if not self._symbols:
            self._symbols = [self.config.symbol]
        self._intervals = [i for i in (self.config.intervals or [self._bar_interval]) if i]
        if not self._intervals:
            self._intervals = [self._bar_interval]

        if StrategyContext and live_strategy and hasattr(live_strategy, "initialize"):
            ctx = StrategyContext(
                exchange=self.config.exchange,
                symbol=self._symbols[0] if self._symbols else self.config.symbol,
                interval=self._intervals[0] if self._intervals else self._bar_interval,
                symbols=self._symbols,
                intervals=self._intervals,
                params=params,
                max_position_pct=self.config.max_position_pct,
                stop_loss_pct=self.config.stop_loss_pct,
            )
            live_strategy.initialize(ctx)

        return StrategyArtifacts(
            module=module,
            signals_fn=signals_fn,
            live_strategy=live_strategy,
            params=params,
            entry_fn=spec.entrypoint.function,
        )

    def _build_live_strategy(self, module: ModuleType) -> Optional[Any]:
        candidates = []
        for name in ("create_live_strategy", "build_live_strategy", "create_strategy"):
            fn = getattr(module, name, None)
            if callable(fn):
                try:
                    candidates.append(fn())
                except Exception:
                    continue
        for name in ("LiveStrategy", "Strategy", "ExampleLiveStrategy"):
            obj = getattr(module, name, None)
            if isinstance(obj, type):
                try:
                    candidates.append(obj())
                except Exception:
                    continue
            elif callable(obj):
                try:
                    candidates.append(obj())
                except Exception:
                    continue

        for candidate in candidates:
            if candidate is None:
                continue
            if LiveStrategyProtocol and isinstance(candidate, LiveStrategyProtocol):
                return candidate
            if hasattr(candidate, "on_bar") and hasattr(candidate, "initialize"):
                return candidate
        return None

    def _start_streams(self) -> None:
        for symbol in self._symbols:
            for interval in self._intervals:
                key = (symbol, interval)
                if key in self._streams:
                    continue
                buffer = CandleBuffer(inst_id=symbol, interval=interval, max_candles=max(self._history_bars, 200))
                try:
                    history = _fetch_recent_candles(symbol, interval, self._history_bars)
                    if not history.empty:
                        buffer.load_history(history.to_dict("records"))
                    buffer.mark_initialized()
                except Exception as exc:
                    logger.error("Failed to seed candles for %s/%s: %s", symbol, interval, exc)
                    buffer.mark_initialized()
                self._streams[key] = buffer

                channel = self._ws_manager.build_candle_channel(interval)
                conn = self._ws_manager.get_connection(symbol)

                def _callback(records: List[Any], stream_key: tuple[str, str] = key) -> None:
                    self._handle_ws_records(stream_key, records)

                sub_key = conn.subscribe(channel, symbol, _callback)
                self._subscriptions[key] = (sub_key, _callback)

    def _stop_streams(self) -> None:
        for key, (sub_key, callback) in list(self._subscriptions.items()):
            symbol, _interval = key
            conn = self._ws_manager.get_connection(symbol)
            conn.unsubscribe(sub_key, callback)
            self._subscriptions.pop(key, None)
        self._ws_manager.release_if_idle()
        self._streams.clear()
        self._last_target_by_stream.clear()
        self._seen_decision_ids.clear()

    def _handle_ws_records(self, key: tuple[str, str], records: List[Any]) -> None:
        buffer = self._streams.get(key)
        if not buffer:
            return
        confirmed = buffer.on_ws_update(records)
        for candle in confirmed:
            self._event_queue.put(CandleEvent(symbol=key[0], interval=key[1], timestamp=candle.timestamp))

    def _build_history_frame(self, key: tuple[str, str]) -> pd.DataFrame:
        buffer = self._streams.get(key)
        if not buffer:
            return pd.DataFrame()
        candles = buffer.get_candles(self._history_bars)
        if not candles:
            return pd.DataFrame()
        data = {
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
        return pd.DataFrame(data)

    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        from app.main import app

        session_factory = app.state.session_factory
        streams_started = False
        while not self._stop_event.is_set():
            try:
                try:
                    event = self._event_queue.get(timeout=MIN_POLL_SECONDS)
                except queue.Empty:
                    event = None

                with session_factory() as db:
                    session = db.get(TradingSession, self.session_id)
                    if session is None or session.status not in (TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING):
                        break
                    if self._artifacts is None:
                        self._artifacts = self._load_strategy()
                        log_trading_event(
                            db,
                            strategy_id=self.strategy_id,
                            session_id=self.session_id,
                            level=LogLevel.INFO,
                            message="Live strategy loaded",
                            metadata={"mode": "live" if self._artifacts.live_strategy else "signals"},
                        )

                    if not streams_started:
                        self._start_streams()
                        streams_started = True

                    if event is None:
                        continue

                    history = self._build_history_frame((event.symbol, event.interval))
                    if history.empty:
                        continue

                    executor = OrderExecutor(self.config, self.session_id, db, self.account)
                    self._broker.attach(executor, db)
                    try:
                        if self._artifacts.live_strategy:
                            self._run_live_strategy(event.symbol, event.interval, history, db)
                        else:
                            self._run_signal_strategy(event.symbol, event.interval, history, db)
                    finally:
                        self._broker.detach()
            except Exception as exc:  # pragma: no cover
                with session_factory() as db:
                    log_trading_event(
                        db,
                        strategy_id=self.strategy_id,
                        session_id=self.session_id,
                        level=LogLevel.ERROR,
                        message="Live runner error",
                        metadata={"error": str(exc)},
                    )
        self._stop_streams()

    # ------------------------------------------------------------------
    def _run_live_strategy(self, symbol: str, interval: str, candles: pd.DataFrame, db: Session) -> None:
        if not self._artifacts or not self._artifacts.live_strategy or candles.empty:
            return
        live_strategy = self._artifacts.live_strategy
        row = candles.iloc[-1]
        ts = int(row["timestamp"])
        key = (symbol, interval)
        last_ts = self._last_bar_ts.get(key)
        if last_ts and ts <= last_ts:
            return
        bar = self._build_bar(row, symbol=symbol, interval=interval)
        history = candles.copy()
        try:
            live_strategy.on_bar(bar, history, self._broker)
        except Exception as exc:
            log_trading_event(
                db,
                strategy_id=self.strategy_id,
                session_id=self.session_id,
                level=LogLevel.ERROR,
                message="Strategy on_bar failed",
                metadata={"error": str(exc), "symbol": symbol, "interval": interval},
            )
            if hasattr(live_strategy, "on_error"):
                try:
                    live_strategy.on_error(exc, self._broker)
                except Exception:
                    pass
        finally:
            self._last_bar_ts[key] = ts

    def _run_signal_strategy(self, symbol: str, interval: str, candles: pd.DataFrame, db: Session) -> None:
        if not self._artifacts or not self._artifacts.signals_fn or candles.empty:
            return
        raw_signals = self._artifacts.signals_fn(candles.copy(), dict(self._artifacts.params))
        if not isinstance(raw_signals, dict):
            raise ValueError("strategy_signals_must_be_dict")
        try:
            now_ts = int(candles.iloc[-1]["timestamp"])
            signals = normalize_signals(
                raw_signals,
                n=len(candles),
                mode="target_weights",
                symbol=symbol,
                now_ts_ms=now_ts,
                seen_decision_ids=self._seen_decision_ids,
            )
        except Exception as exc:
            log_trading_event(
                db,
                strategy_id=self.strategy_id,
                session_id=self.session_id,
                level=LogLevel.WARNING,
                message="Signals validation failed; skipping",
                metadata={"error": str(exc), "symbol": symbol, "interval": interval},
            )
            return
        if len(self._seen_decision_ids) > 20_000:
            self._seen_decision_ids.clear()

        target = self._infer_target(signals)
        if target is None:
            log_trading_event(
                db,
                strategy_id=self.strategy_id,
                session_id=self.session_id,
                level=LogLevel.WARNING,
                message="Signals missing target; skipping",
                metadata={"keys": list(signals.keys()), "symbol": symbol, "interval": interval},
            )
            return
        try:
            price = float(candles.iloc[-1]["close"])
            confidence = float(signals.get("confidence", 0.0) or 0.0)
        except Exception:
            price = 0.0
            confidence = 0.0

        try:
            target_value = float(target)
        except Exception:
            log_trading_event(
                db,
                strategy_id=self.strategy_id,
                session_id=self.session_id,
                level=LogLevel.WARNING,
                message="Signals target invalid; skipping",
                metadata={"target": target, "symbol": symbol, "interval": interval},
            )
            return
        key = (symbol, interval)
        prev_target = float(self._last_target_by_stream.get(key, 0.0))
        transition = describe_weight_transition(prev_target, target_value, signal_source="target_weights")
        if not transition.changed:
            return

        side = transition.order_side or ("buy" if target_value >= prev_target else "sell")
        weight_reasons = signals.get("weight_reason")
        weight_reason = ""
        if hasattr(weight_reasons, "__len__") and len(weight_reasons) > 0:  # type: ignore[arg-type]
            try:
                weight_reason = str(weight_reasons[-1])  # type: ignore[index]
            except Exception:
                weight_reason = ""
        reason = weight_reason or str(signals.get("reason") or transition.signal_reason)
        params_snapshot = dict(signals.get("params_snapshot") or dict(self._artifacts.params))
        params_snapshot["decision_id"] = signals.get("decision_id")
        params_snapshot["protocol_version"] = signals.get("protocol_version")
        params_snapshot["signal_symbol"] = signals.get("signal_symbol") or symbol
        indicators = signals.get("indicators")
        if not isinstance(indicators, dict):
            indicators = {}
        indicators["decision"] = {
            "decision_id": signals.get("decision_id"),
            "protocol_version": signals.get("protocol_version"),
            "decision_ts": signals.get("decision_ts"),
            "expires_at": signals.get("expires_at"),
            "signal_type": transition.signal_type,
            "position_side": transition.position_side,
        }
        diagnostics = signals.get("diagnostics")
        if isinstance(diagnostics, dict):
            indicators["diagnostics"] = diagnostics
        position = signals.get("position") or {"symbol": symbol, "size": self._broker.current_position(symbol)}
        price_source = signals.get("price_source") or "close"

        signal_entry = StrategySignal(
            strategy_id=self.strategy_id,
            session_id=self.session_id,
            symbol=symbol,
            interval=interval,
            side=side,
            price=price,
            confidence=confidence,
            target=target_value,
            status=SignalStatus.PENDING,
            reason=str(reason),
            params_snapshot=params_snapshot,
            indicators=indicators,
            position=position,
            price_source=price_source,
        )
        db.add(signal_entry)
        db.commit()
        self._broker.set_target_allocation(target_value, reason=reason or "generate_signals", symbol=symbol)
        self._last_target_by_stream[key] = target_value

    def _infer_target(self, signals: dict[str, Any]) -> Optional[float]:
        if "target" in signals:
            try:
                target = float(signals["target"])
                return max(-1.0, min(1.0, target))
            except Exception:
                return None
        if "target_weights" in signals:
            weights = signals["target_weights"]
            if hasattr(weights, "__getitem__"):
                try:
                    target = float(weights[-1])
                    return max(-1.0, min(1.0, target))
                except Exception:
                    return None
        return None

    def _build_bar(self, row: pd.Series, *, symbol: str, interval: str):
        from live_trading_sdk import Bar  # Safe import (raises if SDK missing)

        return Bar(
            timestamp=int(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=symbol,
            interval=interval,
        )
