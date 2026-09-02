"""Divergence Strategy - multi-indicator regular divergence template."""

from __future__ import annotations

from typing import Any

import pandas as pd
from live_trading_sdk import Bar, Broker, StrategyContext

from strategy_templates.base import BaseTemplateStrategy, TemplateMetadata
from strategy_templates.shared import indicators
from strategy_templates.shared.pivots import detect_pivots_confirmed

from .config import params_from_dict, StrategyParams
from .risk import SupportResistanceCalculator
from .signals import (
    aggregate_signals,
    detect_regular_divergence,
    filter_signals_by_zone,
)


class DivergenceStrategy(BaseTemplateStrategy):
    """Regular divergence strategy with multi-indicator confirmation."""

    metadata = TemplateMetadata(
        name="divergence",
        description="Regular divergence with multi-indicator confirmation and optional S/R risk filter.",
        version="1.0.0",
        author="PromptTrading",
        tags=["divergence", "rsi", "macd", "mean_reversion"],
        risk_level="medium",
        trading_frequency="intraday",
        complexity_score=4,
        min_capital_usdt=100.0,
        supported_exchanges=["okx"],
        supported_symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )

    def initialize(self, context: StrategyContext) -> None:
        super().initialize(context)
        self._config: StrategyParams = params_from_dict(self._params)
        self._sr = SupportResistanceCalculator(
            lookback_bars=50,
            pivot_period=max(2, int(self._config.pivot_period / 2)),
            buffer_pct=0.003,
            min_risk_reward=self._config.min_risk_reward,
            fallback_sl_pct=self._config.stop_loss_pct,
            fallback_tp_pct=self._config.take_profit_pct,
            min_sl_pct=0.005,
        )
        self._last_signal_bar: int | None = None
        self._position_dir = 0
        self._entry_price: float | None = None
        self._entry_bar: int | None = None

    def on_bar(self, bar: Bar, history: pd.DataFrame, broker: Broker) -> None:
        if history is None or len(history) < 10:
            return

        frame = self._prepare_history(history)
        if frame is None or len(frame) < 10:
            return

        cfg = self._config
        pivots = detect_pivots_confirmed(
            close=frame["close"],
            timestamps=frame["datetime"],
            left=max(1, cfg.pivot_period),
            right=max(0, cfg.pivot_confirm_bars),
        )
        if not pivots:
            return

        signals = self._build_signals(frame, pivots, cfg)
        if not signals:
            return

        aggregated = aggregate_signals(
            divergence_signals=signals,
            min_confirmations=cfg.min_confirmations,
            bar_duration=self._infer_bar_duration(frame),
        )
        if not aggregated:
            return

        current_index = len(frame) - 1
        candidate = aggregated[-1]
        if candidate.bar_index != current_index:
            return

        if self._last_signal_bar is not None:
            if current_index - self._last_signal_bar <= cfg.cooldown_bars:
                return

        if cfg.min_risk_reward > 0:
            tpsl = self._sr.calculate_tpsl(
                data=frame,
                entry_index=candidate.bar_index,
                direction=candidate.direction,
                entry_price=candidate.price,
            )
            if not tpsl.is_valid:
                return

        signal_dir = 1 if candidate.direction == "long" else -1
        if signal_dir == self._position_dir:
            return

        target = max(0.0, min(1.0, float(cfg.position_size_pct))) * float(signal_dir)
        broker.set_target_allocation(target, reason=f"divergence_{candidate.direction}")
        self._position_dir = signal_dir
        self._entry_price = float(bar.close)
        self._entry_bar = current_index
        self._last_signal_bar = current_index

    def _prepare_history(self, history: pd.DataFrame) -> pd.DataFrame | None:
        required_cols = {"open", "high", "low", "close", "volume"}
        if not required_cols.issubset(set(history.columns)):
            return None

        frame = history.copy()
        if "datetime" not in frame.columns:
            if "timestamp" in frame.columns:
                frame["datetime"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
            else:
                frame["datetime"] = pd.to_datetime(frame.index, utc=True)
        frame = frame.dropna(subset=["close", "datetime"])

        lookback = max(200, self._config.pivot_period * 4 + 100)
        if len(frame) > lookback:
            frame = frame.iloc[-lookback:].reset_index(drop=True)
        else:
            frame = frame.reset_index(drop=True)
        return frame

    def _build_signals(
        self,
        frame: pd.DataFrame,
        pivots: list[Any],
        cfg: StrategyParams,
    ) -> list[Any]:
        ind_cfg = cfg.indicators
        signals: list[Any] = []

        macd_line, _, hist = indicators.macd(
            frame["close"], ind_cfg.macd_fast, ind_cfg.macd_slow, ind_cfg.macd_signal
        )
        signals.extend(detect_regular_divergence(pivots, macd_line, "MACD"))
        signals.extend(detect_regular_divergence(pivots, hist, "MACD_Hist"))

        stoch_df = indicators.stochastic_oscillator(
            frame["high"],
            frame["low"],
            frame["close"],
            k_period=ind_cfg.stochastic_k,
            d_period=ind_cfg.stochastic_d,
            smooth_k=ind_cfg.stochastic_smooth,
        )
        stoch_signals = detect_regular_divergence(pivots, stoch_df["stoch_k"], "Stochastic")
        zf = ind_cfg.stochastic_zone_filter
        if zf and zf.enabled:
            stoch_signals = filter_signals_by_zone(
                stoch_signals, short_min=zf.overbought, long_max=zf.oversold
            )
        signals.extend(stoch_signals)

        if ind_cfg.vw_macd_enabled:
            vw_macd, _, _ = indicators.volume_weighted_macd(
                frame["close"],
                frame["volume"],
                ind_cfg.vw_macd_fast,
                ind_cfg.vw_macd_slow,
                ind_cfg.vw_macd_signal,
            )
            signals.extend(detect_regular_divergence(pivots, vw_macd, "VW_MACD"))

        if ind_cfg.obv_enabled:
            obv_series = indicators.obv(frame["close"], frame["volume"])
            signals.extend(detect_regular_divergence(pivots, obv_series, "OBV"))

        if ind_cfg.rsi_enabled:
            rsi_series = indicators.rsi(frame["close"], ind_cfg.rsi_period)
            signals.extend(detect_regular_divergence(pivots, rsi_series, "RSI"))

        if ind_cfg.mfi_enabled:
            mfi_series = indicators.mfi(
                frame["high"], frame["low"], frame["close"], frame["volume"], ind_cfg.mfi_period
            )
            signals.extend(detect_regular_divergence(pivots, mfi_series, "MFI"))

        if ind_cfg.cci_enabled:
            cci_series = indicators.cci(
                frame["high"], frame["low"], frame["close"], ind_cfg.cci_period
            )
            signals.extend(detect_regular_divergence(pivots, cci_series, "CCI"))

        return signals

    def _infer_bar_duration(self, frame: pd.DataFrame) -> str:
        if len(frame) < 2:
            return "15m"
        delta = frame["datetime"].iloc[-1] - frame["datetime"].iloc[-2]
        minutes = int(max(1, round(delta.total_seconds() / 60)))
        if minutes >= 60 and minutes % 60 == 0:
            hours = minutes // 60
            return f"{hours}h"
        return f"{minutes}m"


def create_live_strategy() -> DivergenceStrategy:
    return DivergenceStrategy()
