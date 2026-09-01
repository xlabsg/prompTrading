from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stable5Preset:
    exchange: str = "okx"
    symbols: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
    intervals: tuple[str, ...] = ("1h", "4h")
    min_days: int = 365

    # OKX maker fee default for retail (2 bps).
    fee_rate: float = 0.0002

    # Fixed slippage assumption in bps, applied on rebalances.
    slippage_bps: float = 2.0

