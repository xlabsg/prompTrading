from __future__ import annotations

from dataclasses import dataclass

from .aggregator import MinuteBar
from .config import SignalConfig
from .types import Direction


@dataclass
class MultiScaleResult:
    ok: bool
    reason: str
    score_5m: float = 0.0
    score_15m: float = 0.0
    vol_z_5m: float = 0.0
    vol_z_15m: float = 0.0


def _window_stats(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, var ** 0.5


def confirm_multiscale(
    direction: Direction,
    bars: list[MinuteBar],
    signal_cfg: SignalConfig,
) -> MultiScaleResult:
    enabled = bool(getattr(signal_cfg, "ms_confirm_enabled", False))
    if not enabled:
        return MultiScaleResult(ok=True, reason="ms_confirm_disabled")

    if not bars:
        return MultiScaleResult(ok=False, reason="ms_confirm_no_bars")

    win_5m = max(int(getattr(signal_cfg, "ms_confirm_5m_bars", 5) or 5), 1)
    win_15m = max(int(getattr(signal_cfg, "ms_confirm_15m_bars", 15) or 15), 1)
    min_imb_5m = abs(float(getattr(signal_cfg, "ms_confirm_5m_min_imbalance", 0.0) or 0.0))
    min_imb_15m = abs(float(getattr(signal_cfg, "ms_confirm_15m_min_imbalance", 0.0) or 0.0))
    min_z_5m = float(getattr(signal_cfg, "ms_confirm_5m_min_volume_zscore", 0.0) or 0.0)
    min_z_15m = float(getattr(signal_cfg, "ms_confirm_15m_min_volume_zscore", 0.0) or 0.0)

    bars_5m = bars[-win_5m:]
    bars_15m = bars[-win_15m:]

    def _imbalance(b: list[MinuteBar]) -> float:
        buy = sum(x.buy_volume for x in b)
        sell = sum(x.sell_volume for x in b)
        total = buy + sell
        return (buy - sell) / total if total > 0 else 0.0

    def _vol_z(b: list[MinuteBar]) -> float:
        vols = [x.volume for x in b]
        mean, std = _window_stats(vols)
        if std <= 0:
            return 0.0
        return (vols[-1] - mean) / std

    imb_5m = _imbalance(bars_5m)
    imb_15m = _imbalance(bars_15m)
    z_5m = _vol_z(bars_5m)
    z_15m = _vol_z(bars_15m)

    dir_sign = 1.0 if direction == Direction.LONG else -1.0
    score_5m = imb_5m * dir_sign
    score_15m = imb_15m * dir_sign

    if score_5m < min_imb_5m or score_15m < min_imb_15m:
        return MultiScaleResult(
            ok=False,
            reason="ms_confirm_imbalance_insufficient",
            score_5m=score_5m,
            score_15m=score_15m,
            vol_z_5m=z_5m,
            vol_z_15m=z_15m,
        )

    if z_5m < min_z_5m or z_15m < min_z_15m:
        return MultiScaleResult(
            ok=False,
            reason="ms_confirm_volume_insufficient",
            score_5m=score_5m,
            score_15m=score_15m,
            vol_z_5m=z_5m,
            vol_z_15m=z_15m,
        )

    return MultiScaleResult(
        ok=True,
        reason="ms_confirm_passed",
        score_5m=score_5m,
        score_15m=score_15m,
        vol_z_5m=z_5m,
        vol_z_15m=z_15m,
    )


__all__ = ["MultiScaleResult", "confirm_multiscale"]
