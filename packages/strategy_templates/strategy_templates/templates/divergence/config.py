from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StochasticZoneFilterSettings:
    enabled: bool = False
    overbought: float = 70.0
    oversold: float = 30.0


@dataclass
class IndicatorSettings:
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    stochastic_k: int = 14
    stochastic_d: int = 3
    stochastic_smooth: int = 3
    vw_macd_fast: int = 12
    vw_macd_slow: int = 26
    vw_macd_signal: int = 9
    vw_macd_enabled: bool = True
    obv_enabled: bool = True
    stochastic_zone_filter: StochasticZoneFilterSettings = field(
        default_factory=StochasticZoneFilterSettings
    )
    rsi_period: int = 14
    rsi_enabled: bool = False
    mfi_period: int = 14
    mfi_enabled: bool = False
    cci_period: int = 20
    cci_enabled: bool = False


@dataclass
class StrategyParams:
    pivot_period: int = 10
    pivot_confirm_bars: int = 1
    min_confirmations: int = 3
    min_risk_reward: float = 1.0
    use_dynamic_tpsl: bool = True
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.02
    cooldown_bars: int = 0
    position_size_pct: float = 1.0
    max_hold_bars: int = 0
    min_rsi_delta: float = 0.0
    indicators: IndicatorSettings = field(default_factory=IndicatorSettings)


def params_from_dict(values: dict[str, Any]) -> StrategyParams:
    indicators_raw = values.get("indicators") or {}
    stoch_zone_raw = indicators_raw.get("stochastic_zone_filter") or {}
    stoch_zone = StochasticZoneFilterSettings(
        enabled=bool(stoch_zone_raw.get("enabled", False)),
        overbought=float(stoch_zone_raw.get("overbought", 70.0) or 70.0),
        oversold=float(stoch_zone_raw.get("oversold", 30.0) or 30.0),
    )
    indicators = IndicatorSettings(
        macd_fast=int(indicators_raw.get("macd_fast", 12)),
        macd_slow=int(indicators_raw.get("macd_slow", 26)),
        macd_signal=int(indicators_raw.get("macd_signal", 9)),
        stochastic_k=int(indicators_raw.get("stochastic_k", 14)),
        stochastic_d=int(indicators_raw.get("stochastic_d", 3)),
        stochastic_smooth=int(indicators_raw.get("stochastic_smooth", 3)),
        vw_macd_fast=int(indicators_raw.get("vw_macd_fast", 12)),
        vw_macd_slow=int(indicators_raw.get("vw_macd_slow", 26)),
        vw_macd_signal=int(indicators_raw.get("vw_macd_signal", 9)),
        vw_macd_enabled=bool(indicators_raw.get("vw_macd_enabled", True)),
        obv_enabled=bool(indicators_raw.get("obv_enabled", True)),
        stochastic_zone_filter=stoch_zone,
        rsi_period=int(indicators_raw.get("rsi_period", 14)),
        rsi_enabled=bool(indicators_raw.get("rsi_enabled", False)),
        mfi_period=int(indicators_raw.get("mfi_period", 14)),
        mfi_enabled=bool(indicators_raw.get("mfi_enabled", False)),
        cci_period=int(indicators_raw.get("cci_period", 20)),
        cci_enabled=bool(indicators_raw.get("cci_enabled", False)),
    )

    return StrategyParams(
        pivot_period=int(values.get("pivot_period", 10)),
        pivot_confirm_bars=max(0, int(values.get("pivot_confirm_bars", 1))),
        min_confirmations=max(1, int(values.get("min_confirmations", 3))),
        min_risk_reward=float(values.get("min_risk_reward", 1.0)),
        use_dynamic_tpsl=bool(values.get("use_dynamic_tpsl", True)),
        stop_loss_pct=float(values.get("stop_loss_pct", 0.01)),
        take_profit_pct=float(values.get("take_profit_pct", 0.02)),
        cooldown_bars=max(0, int(values.get("cooldown_bars", 0))),
        position_size_pct=float(values.get("position_size_pct", 1.0)),
        max_hold_bars=max(0, int(values.get("max_hold_bars", 0))),
        min_rsi_delta=float(values.get("min_rsi_delta", 0.0)),
        indicators=indicators,
    )
