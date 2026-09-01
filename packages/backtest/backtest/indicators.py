from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

SeriesLike = Union[pd.Series, np.ndarray, list[float], float, int]

try:
    import talib as _talib  # type: ignore
except Exception:  # noqa: BLE001
    _talib = None


def sma(x: SeriesLike, window: int) -> pd.Series:
    """Simple moving average."""
    s = pd.Series(x, copy=False).astype(float)
    w = max(1, int(window))
    return s.rolling(w).mean()


def ema(x: SeriesLike, window: int) -> pd.Series:
    """Exponential moving average (EMA)."""
    s = pd.Series(x, copy=False).astype(float)
    w = max(1, int(window))
    return s.ewm(span=w, adjust=False, min_periods=w).mean()


def rsi(close: SeriesLike, window: int = 14) -> pd.Series:
    """Relative Strength Index (RSI), Wilder-style smoothing."""
    c = pd.Series(close, copy=False).astype(float)
    w = max(1, int(window))
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / w, adjust=False, min_periods=w).mean()
    avg_loss = loss.ewm(alpha=1.0 / w, adjust=False, min_periods=w).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out


def zscore(x: SeriesLike, window: int) -> pd.Series:
    """Rolling z-score."""
    s = pd.Series(x, copy=False).astype(float)
    w = max(1, int(window))
    mu = s.rolling(w).mean()
    sig = s.rolling(w).std(ddof=0)
    return (s - mu) / sig.replace(0.0, np.nan)


def _to_series(x: SeriesLike, *, like: pd.Series | None = None) -> pd.Series:
    if isinstance(x, pd.Series):
        s = x.astype(float)
    elif np.isscalar(x):
        if like is None:
            s = pd.Series([float(x)])
        else:
            s = pd.Series(float(x), index=like.index)
    else:
        s = pd.Series(x, copy=False).astype(float)
        if like is not None and len(s) != len(like):
            if len(s) == 1:
                s = pd.Series(float(s.iloc[0]), index=like.index)
            else:
                raise ValueError("indicator_input_length_mismatch")
    return s


def atr(
    high: SeriesLike,
    low: SeriesLike,
    close: SeriesLike,
    window: int = 14,
) -> pd.Series:
    """Average True Range (ATR), Wilder-style smoothing."""
    h = _to_series(high)
    l = _to_series(low, like=h)
    c = _to_series(close, like=h)
    w = max(1, int(window))
    prev_close = c.shift(1)
    tr = pd.concat(
        [
            (h - l).abs(),
            (h - prev_close).abs(),
            (l - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / w, adjust=False, min_periods=w).mean()


def cross_over(a: SeriesLike, b: SeriesLike) -> pd.Series:
    """True where a crosses above b."""
    a_s = _to_series(a)
    b_s = _to_series(b, like=a_s)
    return (a_s > b_s) & (a_s.shift(1) <= b_s.shift(1))


def cross_under(a: SeriesLike, b: SeriesLike) -> pd.Series:
    """True where a crosses below b."""
    a_s = _to_series(a)
    b_s = _to_series(b, like=a_s)
    return (a_s < b_s) & (a_s.shift(1) >= b_s.shift(1))


def _resolve_talib_function(name: str):
    if _talib is None:
        return None
    candidates = [name, name.upper()]
    if "_" in name:
        candidates.append(name.replace("_", "").upper())
    for candidate in candidates:
        if hasattr(_talib, candidate):
            fn = getattr(_talib, candidate)
            if callable(fn):
                return fn
    return None


def __getattr__(name: str):
    fn = _resolve_talib_function(name)
    if fn is not None:
        return fn
    raise AttributeError(f"module 'backtest.indicators' has no attribute {name!r}")


def __dir__() -> list[str]:
    base = set(globals().keys())
    if _talib is not None:
        for name in dir(_talib):
            if name.startswith("_"):
                continue
            fn = getattr(_talib, name, None)
            if callable(fn):
                base.add(name.lower())
    return sorted(base)
