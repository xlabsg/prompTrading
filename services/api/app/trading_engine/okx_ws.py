"""Shared OKX WebSocket manager for candle subscriptions."""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

import websockets
from websockets.client import WebSocketClientProtocol

WS_PUBLIC_URL = "wss://ws.okx.com:8443/ws/v5/public"
WS_BUSINESS_URL = "wss://ws.okx.com:8443/ws/v5/business"

HEARTBEAT_INTERVAL = 20
RECONNECT_DELAY = 3

_callback_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="okx-ws-callback")


def _is_derivatives(inst_id: str) -> bool:
    upper_id = inst_id.upper()
    if upper_id.endswith("-SWAP"):
        return True
    if upper_id.endswith("-C") or upper_id.endswith("-P"):
        return True
    parts = upper_id.split("-")
    return len(parts) >= 3 and parts[-1].isdigit() and len(parts[-1]) == 6


def _normalize_interval(interval: str) -> str:
    tf = (interval or "").strip().lower()
    if tf.endswith("s"):
        return tf
    if tf.endswith("m"):
        return tf
    if tf.endswith("h"):
        return tf[:-1] + "H"
    if tf.endswith("d"):
        return tf[:-1] + "D"
    return tf


@dataclass(frozen=True)
class SubscriptionKey:
    channel: str
    inst_id: str

    def to_subscribe_arg(self) -> Dict[str, str]:
        return {"channel": self.channel, "instId": self.inst_id}


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    confirm: bool

    @classmethod
    def from_okx(cls, data: List[str]) -> "Candle":
        return cls(
            timestamp=int(data[0]),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]),
            confirm=(data[8] == "1") if len(data) > 8 else True,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class CandleBuffer:
    """Thread-safe candle buffer that only emits confirmed candles after init."""

    def __init__(
        self,
        *,
        inst_id: str,
        interval: str,
        max_candles: int = 2000,
    ) -> None:
        self.inst_id = inst_id
        self.interval = interval
        self.max_candles = max_candles
        self._candles: Dict[int, Candle] = {}
        self._last_confirmed_ts: int = 0
        self._initialized = False
        self._lock = threading.Lock()

    def load_history(self, candles: List[Dict[str, Any]]) -> None:
        with self._lock:
            for c in candles:
                ts_ms = int(c.get("timestamp", 0))
                if ts_ms <= 0:
                    continue
                candle = Candle(
                    timestamp=ts_ms,
                    open=float(c.get("open", 0)),
                    high=float(c.get("high", 0)),
                    low=float(c.get("low", 0)),
                    close=float(c.get("close", 0)),
                    volume=float(c.get("volume", 0)),
                    confirm=True,
                )
                self._candles[ts_ms] = candle
                if ts_ms > self._last_confirmed_ts:
                    self._last_confirmed_ts = ts_ms
            self._trim_old()

    def mark_initialized(self) -> None:
        with self._lock:
            self._initialized = True

    def on_ws_update(self, records: List[Any]) -> List[Candle]:
        new_confirmed: List[Candle] = []
        with self._lock:
            for record in records:
                try:
                    candle = Candle.from_okx(record)
                except (IndexError, ValueError):
                    continue
                self._candles[candle.timestamp] = candle
                if candle.confirm and candle.timestamp > self._last_confirmed_ts:
                    self._last_confirmed_ts = candle.timestamp
                    if self._initialized:
                        new_confirmed.append(candle)
            self._trim_old()
        return new_confirmed

    def get_candles(self, count: Optional[int] = None) -> List[Candle]:
        with self._lock:
            confirmed = [c for c in self._candles.values() if c.confirm]
            confirmed.sort(key=lambda c: c.timestamp)
            if count:
                return confirmed[-count:]
            return confirmed

    def _trim_old(self) -> None:
        if len(self._candles) <= self.max_candles:
            return
        to_remove = len(self._candles) - self.max_candles
        for ts in sorted(self._candles.keys())[:to_remove]:
            del self._candles[ts]


class BaseSharedConnection:
    def __init__(self, *, conn_id: str, url: str) -> None:
        self._conn_id = conn_id
        self._url = url
        self._subscriptions: Dict[str, Dict[str, List[Callable]]] = {}
        self._sub_lock = threading.RLock()
        self._active_keys: Set[SubscriptionKey] = set()
        self._ws: Optional[WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"okx-ws-{self._conn_id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
                future.result(timeout=10)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        self._connected.clear()

    def subscribe(self, channel: str, inst_id: str, callback: Callable[[List[Any]], None]) -> SubscriptionKey:
        key = SubscriptionKey(channel, inst_id)
        with self._sub_lock:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = {}
            is_new_inst = inst_id not in self._subscriptions[channel]
            if inst_id not in self._subscriptions[channel]:
                self._subscriptions[channel][inst_id] = []
            if callback not in self._subscriptions[channel][inst_id]:
                self._subscriptions[channel][inst_id].append(callback)
            self._active_keys.add(key)
            should_subscribe = is_new_inst and self._is_ws_ready()
        if should_subscribe:
            self._send_subscribe([key])
        return key

    def unsubscribe(self, key: SubscriptionKey, callback: Callable) -> None:
        should_unsubscribe = False
        with self._sub_lock:
            channel = key.channel
            inst_id = key.inst_id
            if channel not in self._subscriptions or inst_id not in self._subscriptions[channel]:
                return
            callbacks = self._subscriptions[channel][inst_id]
            while callback in callbacks:
                callbacks.remove(callback)
            if not callbacks:
                del self._subscriptions[channel][inst_id]
                self._active_keys.discard(key)
                should_unsubscribe = True
        if should_unsubscribe and self._is_ws_ready():
            self._send_unsubscribe([key])

    def has_subscriptions(self) -> bool:
        with self._sub_lock:
            return bool(self._active_keys)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connection_loop())
        finally:
            self._loop.close()
            self._connected.clear()

    async def _connection_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._run_connection()
            except websockets.ConnectionClosed:
                pass
            except Exception:
                pass
            self._connected.clear()
            if not self._stop_event.is_set():
                await asyncio.sleep(RECONNECT_DELAY)

    async def _run_connection(self) -> None:
        async with websockets.connect(self._url, ping_interval=None) as ws:
            self._ws = ws
            await self._recover_subscriptions()
            self._connected.set()
            await self._message_loop()

    async def _recover_subscriptions(self) -> None:
        with self._sub_lock:
            keys = list(self._active_keys)
        if keys and self._ws:
            args = [key.to_subscribe_arg() for key in keys]
            await self._ws.send(json.dumps({"op": "subscribe", "args": args}))

    async def _message_loop(self) -> None:
        heartbeat_task = asyncio.create_task(self._heartbeat())
        try:
            async for message in self._ws:
                if self._stop_event.is_set():
                    break
                self._handle_message(message)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self) -> None:
        first_ping = True
        while not self._stop_event.is_set():
            wait_time = 5 if first_ping else HEARTBEAT_INTERVAL
            first_ping = False
            await asyncio.sleep(wait_time)
            if self._ws:
                try:
                    await self._ws.send("ping")
                except Exception:
                    break

    async def _shutdown(self) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    def _handle_message(self, message: str) -> None:
        if message == "pong":
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if data.get("event") in ("subscribe", "unsubscribe", "error"):
            return
        arg = data.get("arg", {})
        channel = arg.get("channel")
        inst_id = arg.get("instId")
        records = data.get("data") or []
        if channel and inst_id and records:
            self._route_to_callbacks(channel, inst_id, records)

    def _route_to_callbacks(self, channel: str, inst_id: str, records: List[Any]) -> None:
        callbacks_to_call: List[Callable] = []
        with self._sub_lock:
            if channel in self._subscriptions and inst_id in self._subscriptions[channel]:
                callbacks_to_call = list(self._subscriptions[channel][inst_id])
        for callback in callbacks_to_call:
            _callback_executor.submit(callback, records)

    def _is_ws_ready(self) -> bool:
        return self._ws is not None and self._connected.is_set() and self._loop is not None

    def _send_subscribe(self, keys: List[SubscriptionKey]) -> None:
        if not self._is_ws_ready():
            return
        args = [key.to_subscribe_arg() for key in keys]
        msg = {"op": "subscribe", "args": args}
        try:
            asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(msg)), self._loop)
        except Exception:
            pass

    def _send_unsubscribe(self, keys: List[SubscriptionKey]) -> None:
        if not self._is_ws_ready():
            return
        args = [key.to_subscribe_arg() for key in keys]
        msg = {"op": "unsubscribe", "args": args}
        try:
            asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(msg)), self._loop)
        except Exception:
            pass


class SharedPublicConnection(BaseSharedConnection):
    def __init__(self) -> None:
        super().__init__(conn_id="public", url=WS_PUBLIC_URL)


class SharedBusinessConnection(BaseSharedConnection):
    def __init__(self) -> None:
        super().__init__(conn_id="business", url=WS_BUSINESS_URL)


class OKXWSManager:
    """Singleton manager for OKX public/business connections."""

    _instance: Optional["OKXWSManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "OKXWSManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._public_conn: Optional[SharedPublicConnection] = None
        self._business_conn: Optional[SharedBusinessConnection] = None
        self._conn_lock = threading.Lock()
        self._initialized = True

    @classmethod
    def instance(cls) -> "OKXWSManager":
        return cls()

    def get_connection(self, inst_id: str) -> BaseSharedConnection:
        with self._conn_lock:
            if _is_derivatives(inst_id):
                if self._business_conn is None:
                    self._business_conn = SharedBusinessConnection()
                    self._business_conn.start()
                return self._business_conn
            if self._public_conn is None:
                self._public_conn = SharedPublicConnection()
                self._public_conn.start()
            return self._public_conn

    def release_if_idle(self) -> None:
        with self._conn_lock:
            if self._public_conn and not self._public_conn.has_subscriptions():
                self._public_conn.stop()
                self._public_conn = None
            if self._business_conn and not self._business_conn.has_subscriptions():
                self._business_conn.stop()
                self._business_conn = None

    def build_candle_channel(self, interval: str) -> str:
        return f"candle{_normalize_interval(interval)}"
