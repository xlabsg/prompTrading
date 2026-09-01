"""
Configuration helpers for the Flow Right strategy.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TradingCredentials:
    api_key: str = ""
    secret_key: str = ""
    passphrase: str = ""

    @classmethod
    def from_env(
        cls,
        api_key_env: str,
        secret_key_env: str,
        passphrase_env: str,
    ) -> TradingCredentials:
        return cls(
            api_key=os.getenv(api_key_env, ""),
            secret_key=os.getenv(secret_key_env, ""),
            passphrase=os.getenv(passphrase_env, ""),
        )

    @property
    def is_valid(self) -> bool:
        return bool(self.api_key and self.secret_key and self.passphrase)


@dataclass
class WindowConfig:
    name: str
    seconds: int
    weight: float


@dataclass
class OKXConfig:
    ws_base_url: str = "wss://ws.okx.com:8443/ws/v5/public"
    reconnect_delay: float = 2.0


@dataclass
class BinanceConfig:
    ws_base_url: str = "wss://stream.binance.com:9443/ws"
    reconnect_delay: float = 1.5
    ping_interval: float = 20.0
    ping_timeout: float = 10.0


@dataclass
class BybitConfig:
    ws_base_url: str = "wss://stream.bybit.com/v5/public/linear"
    reconnect_delay: float = 1.5
    ping_interval: float = 20.0
    ping_timeout: float = 10.0


@dataclass
class DataSourceConfig:
    provider: str = "okx"
    okx: OKXConfig = field(default_factory=OKXConfig)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    bybit: BybitConfig = field(default_factory=BybitConfig)


@dataclass
class RuntimeConfig:
    queue_size: int = 5000
    loop_interval_ms: int = 50
    batch_size: int = 200


@dataclass
class AnalyticsConfig:
    volatility_window_seconds: int = 30
    velocity_window_seconds: int = 3
    max_price_history_seconds: int = 60


@dataclass
class EntryConfig:
    impulse_window: str = "impulse"
    confirmation_window: str = "confirmation"
    context_window: str = "context"
    min_score: float = 0.55
    min_short_imbalance: float = 0.55
    min_mid_imbalance: float = 0.45
    min_long_imbalance: float = 0.35
    min_total_notional: float = 150_000.0
    min_trade_count: int = 10
    min_velocity_bps: float = 1.0
    max_volatility_bps: float = 35.0
    max_signal_latency_ms: int = 400


@dataclass
class RiskConfig:
    cooldown_ms: int = 1200
    max_position_seconds: int = 45
    flat_on_reverse_score: float = 0.2
    signal_expiry_seconds: int = 3
    quick_exit_seconds: int = 10
    exit_on_velocity_decay: bool = True
    velocity_decay_threshold: float = 0.5
    entry_grace_seconds: float = 2.0
    reverse_signal_exit: bool = True
    reverse_exit_min_score: float = 0.0


@dataclass
class PositionSizingConfig:
    enabled: bool = True
    base_usdt: float = 100.0
    confidence_multiplier: bool = True
    min_confidence: float = 0.60
    max_confidence: float = 0.85
    min_multiplier: float = 0.5
    max_multiplier: float = 2.0
    vol_adjust: bool = True
    low_vol_bps: float = 10.0
    high_vol_bps: float = 30.0
    vol_reduce_factor: float = 0.5
    time_decay: bool = True
    entry_time_limit_ms: int = 500
    late_entry_reduce_factor: float = 0.7


@dataclass
class DynamicExitConfig:
    enabled: bool = True
    use_atr_stop: bool = False
    use_flow_stop: bool = True
    stop_on_flow_reversal: bool = True
    reversal_threshold: float = 0.25
    use_trailing_stop: bool = True
    trailing_activation_bps: float = 4.0
    trailing_callback_bps: float = 2.0
    time_stop_enabled: bool = True
    time_stop_seconds: int = 30
    tp_enabled: bool = True
    tp_bps: float = 6.0
    partial_tp_enabled: bool = False
    partial_tp_ratio: float = 0.5
    partial_tp_bps: float = 3.5


@dataclass
class FlowRightTradingConfig:
    enabled: bool = False
    api_key_env: str = "OKX_FLOW_API_KEY"
    secret_key_env: str = "OKX_FLOW_SECRET"
    passphrase_env: str = "OKX_FLOW_PASSPHRASE"
    margin_mode: str = "cross"
    leverage: int = 5
    position_usdt: float = 150.0
    order_type: str = "market"
    reduce_only: bool = False
    pos_mode: str = "net"
    state_file: str = "state/flow_right_trade.json"

    def load_credentials(self) -> TradingCredentials:
        return TradingCredentials.from_env(
            api_key_env=self.api_key_env,
            secret_key_env=self.secret_key_env,
            passphrase_env=self.passphrase_env,
        )


@dataclass
class MarketConfig:
    name: str | None = None
    symbol: str | None = None
    instrument: str | None = None
    enabled: bool = True
    trading: FlowRightTradingConfig = field(default_factory=FlowRightTradingConfig)
    queue_size: int | None = None

    def with_defaults(
        self,
        *,
        default_name: str,
        fallback_symbol: str,
        fallback_instrument: str,
        default_trading: FlowRightTradingConfig,
        default_queue_size: int,
    ) -> MarketConfig:
        trading_cfg = self.trading or default_trading
        normalized_trading = (
            trading_cfg
            if trading_cfg is not default_trading
            else replace(default_trading)
        )

        return MarketConfig(
            name=self.name or default_name,
            symbol=(self.symbol or fallback_symbol).lower(),
            instrument=(self.instrument or fallback_instrument).upper(),
            enabled=self.enabled,
            trading=normalized_trading,
            queue_size=self.queue_size or default_queue_size,
        )


@dataclass
class TrendFilterConfig:
    enabled: bool = True
    timeframe_minutes: int = 5
    ema_period: int = 50
    slope_lookback: int = 10
    price_buffer_pct: float = 0.05
    neutral_policy: str = "skip"
    insufficient_data_policy: str = "skip"
    max_entry_distance_pct: float = 0.0


@dataclass
class SignalConfig:
    anomaly_enabled: bool = True
    anomaly_min_score: float = 0.3
    reentry_cooldown_minutes: int = 1
    ms_confirm_enabled: bool = True
    ms_confirm_5m_bars: int = 5
    ms_confirm_15m_bars: int = 15
    ms_confirm_5m_min_imbalance: float = 0.1
    ms_confirm_15m_min_imbalance: float = 0.1
    ms_confirm_5m_min_volume_zscore: float = 0.3
    ms_confirm_15m_min_volume_zscore: float = 0.3


@dataclass
class FlowRightConfig:
    name: str = "flow_right"
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    windows: list[WindowConfig] = field(
        default_factory=lambda: [
            WindowConfig(name="impulse", seconds=10, weight=1.0),
            WindowConfig(name="confirmation", seconds=30, weight=0.7),
            WindowConfig(name="context", seconds=60, weight=0.5),
        ]
    )
    entry: EntryConfig = field(default_factory=EntryConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    position_sizing: PositionSizingConfig = field(default_factory=PositionSizingConfig)
    dynamic_exit: DynamicExitConfig = field(default_factory=DynamicExitConfig)
    trend_filter: TrendFilterConfig = field(default_factory=TrendFilterConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)

    markets: list[MarketConfig] = field(default_factory=list)
    state_path: str = "state/flow_right_state.json"
    log_dir: str = "logs"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlowRightConfig:
        return cls(
            name=data.get("name", "flow_right"),
            data_source=DataSourceConfig(**data.get("data_source", {})),
            runtime=RuntimeConfig(**data.get("runtime", {})),
            analytics=AnalyticsConfig(**data.get("analytics", {})),
            windows=[WindowConfig(**w) for w in data.get("windows", [])],
            entry=EntryConfig(**data.get("entry", {})),
            risk=RiskConfig(**data.get("risk", {})),
            position_sizing=PositionSizingConfig(**data.get("position_sizing", {})),
            dynamic_exit=DynamicExitConfig(**data.get("dynamic_exit", {})),
            trend_filter=TrendFilterConfig(**data.get("trend_filter", {})),
            signal=SignalConfig(**data.get("signal", {})),
            markets=[MarketConfig(**m) for m in data.get("markets", [])],
            state_path=data.get("state_path", "state/flow_right_state.json"),
            log_dir=data.get("log_dir", "logs"),
        )

    def build_market_configs(self) -> list[MarketConfig]:
        if not self.markets:
            return [
                MarketConfig(
                    name="default",
                    symbol="btcusdt",
                    instrument="BTC-USDT-SWAP",
                    enabled=True,
                ).with_defaults(
                    default_name="default",
                    fallback_symbol="btcusdt",
                    fallback_instrument="BTC-USDT-SWAP",
                    default_trading=FlowRightTradingConfig(),
                    default_queue_size=self.runtime.queue_size,
                )
            ]

        configs: list[MarketConfig] = []
        for m in self.markets:
            configs.append(
                m.with_defaults(
                    default_name=m.name or "default",
                    fallback_symbol=m.symbol or "btcusdt",
                    fallback_instrument=m.instrument or "BTC-USDT-SWAP",
                    default_trading=FlowRightTradingConfig(),
                    default_queue_size=self.runtime.queue_size,
                )
            )
        return configs


def load_flow_right_config(path: str | Path) -> FlowRightConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return FlowRightConfig.from_dict(data)


def config_to_dict(config: FlowRightConfig) -> dict[str, Any]:
    return asdict(config)
