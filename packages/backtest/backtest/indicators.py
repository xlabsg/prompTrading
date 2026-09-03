from __future__ import annotations

import functools
from typing import Any, Callable, NamedTuple, Union

import numpy as np
import pandas as pd

SeriesLike = Union[pd.Series, np.ndarray, list[float], float, int]

try:
    import talib as _talib  # type: ignore
except Exception:  # noqa: BLE001
    _talib = None


def _resolve_window(window: int, timeperiod: int | None = None, length: int | None = None) -> int:
    if timeperiod is not None:
        return int(timeperiod)
    if length is not None:
        return int(length)
    return int(window)


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


# =====================================================================
# Core Platform Technical Indicators
# =====================================================================

def sma(x: SeriesLike, window: int = 10, timeperiod: int | None = None, length: int | None = None) -> pd.Series:
    """Simple moving average."""
    s = _to_series(x)
    w = max(1, _resolve_window(window, timeperiod, length))
    return s.rolling(w).mean()


def ema(x: SeriesLike, window: int = 10, timeperiod: int | None = None, length: int | None = None) -> pd.Series:
    """Exponential moving average (EMA)."""
    s = _to_series(x)
    w = max(1, _resolve_window(window, timeperiod, length))
    return s.ewm(span=w, adjust=False, min_periods=w).mean()


def rsi(close: SeriesLike, window: int = 14, timeperiod: int | None = None, length: int | None = None) -> pd.Series:
    """Relative Strength Index (RSI), Wilder-style smoothing."""
    c = _to_series(close)
    w = max(1, _resolve_window(window, timeperiod, length))
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / w, adjust=False, min_periods=w).mean()
    avg_loss = loss.ewm(alpha=1.0 / w, adjust=False, min_periods=w).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out


def zscore(x: SeriesLike, window: int = 20) -> pd.Series:
    """Rolling z-score."""
    s = _to_series(x)
    w = max(1, int(window))
    mu = s.rolling(w).mean()
    sig = s.rolling(w).std(ddof=0)
    return (s - mu) / sig.replace(0.0, np.nan)


# Quantitative convention alias
ts_zscore = zscore


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


# =====================================================================
# Layer 1: Atomic Time-Series Operators (Alpha 101/Qlib Mathematical Primitives)
# =====================================================================

def ts_rank(x: SeriesLike, window: int = 14) -> pd.Series:
    """Rolling percentile rank in range [0.0, 1.0]."""
    s = _to_series(x)
    w = max(2, int(window))

    def _rank_last(arr: np.ndarray) -> float:
        val = arr[-1]
        if np.isnan(val):
            return np.nan
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return np.nan
        return float(np.sum(valid <= val) / len(valid))

    return s.rolling(w).apply(_rank_last, raw=True)


def ts_corr(x: SeriesLike, y: SeriesLike, window: int = 20) -> pd.Series:
    """Rolling Pearson correlation between x and y."""
    x_s = _to_series(x)
    y_s = _to_series(y, like=x_s)
    w = max(2, int(window))
    return x_s.rolling(w).corr(y_s)


def ts_cov(x: SeriesLike, y: SeriesLike, window: int = 20) -> pd.Series:
    """Rolling covariance between x and y."""
    x_s = _to_series(x)
    y_s = _to_series(y, like=x_s)
    w = max(2, int(window))
    return x_s.rolling(w).cov(y_s)


def ts_decay_linear(x: SeriesLike, window: int = 10) -> pd.Series:
    """Linearly weighted moving average (weights 1, 2, ..., w normalized to sum to 1)."""
    s = _to_series(x)
    w = max(1, int(window))
    weights = np.arange(1, w + 1, dtype=float)
    weights /= weights.sum()

    def _wma(arr: np.ndarray) -> float:
        if np.isnan(arr[-1]):
            return np.nan
        return float(np.dot(arr, weights))

    return s.rolling(w).apply(_wma, raw=True)


def ts_max(x: SeriesLike, window: int = 10) -> pd.Series:
    """Rolling maximum over window."""
    s = _to_series(x)
    return s.rolling(max(1, int(window))).max()


def ts_min(x: SeriesLike, window: int = 10) -> pd.Series:
    """Rolling minimum over window."""
    s = _to_series(x)
    return s.rolling(max(1, int(window))).min()


def ts_diff(x: SeriesLike, periods: int = 1) -> pd.Series:
    """Difference between current value and value k periods ago."""
    s = _to_series(x)
    return s.diff(int(periods))


def ts_returns(x: SeriesLike, periods: int = 1) -> pd.Series:
    """Percentage return relative to k periods ago."""
    s = _to_series(x)
    return s.pct_change(int(periods))


def safe_div(num: SeriesLike, denom: SeriesLike, fill: float = 0.0) -> pd.Series:
    """Element-wise safe division avoiding div-by-zero, inf, and NaN."""
    n = _to_series(num)
    d = _to_series(denom, like=n)
    out = n / d
    return out.replace([np.inf, -np.inf, np.nan], fill)


# =====================================================================
# Layer 2: Modern Crypto & Quant Technical Indicators
# =====================================================================

class SupertrendResult(NamedTuple):
    supertrend: pd.Series
    direction: pd.Series


def supertrend(
    high: SeriesLike,
    low: SeriesLike,
    close: SeriesLike,
    period: int = 10,
    multiplier: float = 3.0,
) -> SupertrendResult:
    """Lookahead-safe SuperTrend indicator.

    Returns:
        SupertrendResult(supertrend=Series, direction=Series),
        where direction is +1.0 (bullish uptrend) or -1.0 (bearish downtrend).
    """
    h = _to_series(high)
    l = _to_series(low, like=h)
    c = _to_series(close, like=h)
    n = len(c)
    p = max(1, int(period))
    m = float(multiplier)

    vol_atr = atr(h, l, c, window=p).to_numpy()
    hl2 = ((h + l) / 2.0).to_numpy()
    close_np = c.to_numpy()

    basic_upper = hl2 + m * vol_atr
    basic_lower = hl2 - m * vol_atr

    final_upper = np.copy(basic_upper)
    final_lower = np.copy(basic_lower)
    super_trend = np.zeros(n, dtype=float)
    direction = np.ones(n, dtype=float)

    for i in range(1, n):
        if np.isnan(vol_atr[i]):
            super_trend[i] = np.nan
            direction[i] = 1.0
            continue

        # Final Upper Band
        if basic_upper[i] < final_upper[i - 1] or close_np[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Final Lower Band
        if basic_lower[i] > final_lower[i - 1] or close_np[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Trend Direction & SuperTrend Line
        prev_dir = direction[i - 1]
        if prev_dir == 1.0:
            if close_np[i] < final_lower[i]:
                direction[i] = -1.0
                super_trend[i] = final_upper[i]
            else:
                direction[i] = 1.0
                super_trend[i] = final_lower[i]
        else:
            if close_np[i] > final_upper[i]:
                direction[i] = 1.0
                super_trend[i] = final_lower[i]
            else:
                direction[i] = -1.0
                super_trend[i] = final_upper[i]

    st_series = pd.Series(super_trend, index=c.index)
    dir_series = pd.Series(direction, index=c.index)
    return SupertrendResult(supertrend=st_series, direction=dir_series)


def vwap(
    high: SeriesLike,
    low: SeriesLike,
    close: SeriesLike,
    volume: SeriesLike,
    window: int | None = None,
) -> pd.Series:
    """Volume-Weighted Average Price (cumulative or rolling window if provided)."""
    h = _to_series(high)
    l = _to_series(low, like=h)
    c = _to_series(close, like=h)
    v = _to_series(volume, like=h)
    tp = (h + l + c) / 3.0
    pv = tp * v
    if window is not None and int(window) > 0:
        w = int(window)
        roll_pv = pv.rolling(w).sum()
        roll_v = v.rolling(w).sum()
        return roll_pv / roll_v.replace(0.0, np.nan)
    cum_pv = pv.cumsum()
    cum_v = v.cumsum()
    return cum_pv / cum_v.replace(0.0, np.nan)


class KeltnerChannelResult(NamedTuple):
    upper: pd.Series
    middle: pd.Series
    lower: pd.Series


def keltner_channel(
    high: SeriesLike,
    low: SeriesLike,
    close: SeriesLike,
    ema_window: int = 20,
    atr_window: int = 10,
    multiplier: float = 2.0,
) -> KeltnerChannelResult:
    """Keltner Channel based on EMA center line and ATR volatility bands."""
    h = _to_series(high)
    l = _to_series(low, like=h)
    c = _to_series(close, like=h)
    mid = ema(c, window=ema_window)
    vol_atr = atr(h, l, c, window=atr_window)
    mult = float(multiplier)
    upper = mid + mult * vol_atr
    lower = mid - mult * vol_atr
    return KeltnerChannelResult(upper=upper, middle=mid, lower=lower)


class DonchianChannelResult(NamedTuple):
    upper: pd.Series
    middle: pd.Series
    lower: pd.Series


def donchian_channel(
    high: SeriesLike,
    low: SeriesLike,
    window: int = 20,
    shift: bool = True,
) -> DonchianChannelResult:
    """Donchian Breakout Channel.

    If shift=True (default), channels are shifted by 1 bar to guarantee zero lookahead bias.
    """
    h = _to_series(high)
    l = _to_series(low, like=h)
    w = max(1, int(window))
    upper = h.rolling(w).max()
    lower = l.rolling(w).min()
    if shift:
        upper = upper.shift(1)
        lower = lower.shift(1)
    mid = (upper + lower) / 2.0
    return DonchianChannelResult(upper=upper, middle=mid, lower=lower)


class StochRsiResult(NamedTuple):
    k: pd.Series
    d: pd.Series


def stoch_rsi(
    close: SeriesLike,
    rsi_window: int = 14,
    stoch_window: int = 14,
    k_window: int = 3,
    d_window: int = 3,
) -> StochRsiResult:
    """Stochastic RSI."""
    c = _to_series(close)
    rsi_val = rsi(c, window=rsi_window)
    sw = max(1, int(stoch_window))
    min_rsi = rsi_val.rolling(sw).min()
    max_rsi = rsi_val.rolling(sw).max()
    stoch = (rsi_val - min_rsi) / (max_rsi - min_rsi).replace(0.0, np.nan)
    k = stoch.rolling(max(1, int(k_window))).mean() * 100.0
    d = k.rolling(max(1, int(d_window))).mean()
    return StochRsiResult(k=k, d=d)


def cmf(
    high: SeriesLike,
    low: SeriesLike,
    close: SeriesLike,
    volume: SeriesLike,
    window: int = 20,
) -> pd.Series:
    """Chaikin Money Flow (CMF)."""
    h = _to_series(high)
    l = _to_series(low, like=h)
    c = _to_series(close, like=h)
    v = _to_series(volume, like=h)
    w = max(1, int(window))
    hl_range = (h - l).replace(0.0, np.nan)
    mfm = ((c - l) - (h - c)) / hl_range
    mfv = mfm.fillna(0.0) * v
    vol_sum = v.rolling(w).sum().replace(0.0, np.nan)
    return mfv.rolling(w).sum() / vol_sum


class BollingerBandsResult(NamedTuple):
    upper: pd.Series
    middle: pd.Series
    lower: pd.Series
    bandwidth: pd.Series
    percent_b: pd.Series


def bollinger_bands(
    close: SeriesLike,
    window: int = 20,
    num_std: float = 2.0,
) -> BollingerBandsResult:
    """Bollinger Bands returning upper, middle, lower, bandwidth, and %B."""
    c = _to_series(close)
    w = max(1, int(window))
    std_mult = float(num_std)
    mid = c.rolling(w).mean()
    std = c.rolling(w).std(ddof=0)
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    bandwidth = (upper - lower) / mid.replace(0.0, np.nan)
    percent_b = (c - lower) / (upper - lower).replace(0.0, np.nan)
    return BollingerBandsResult(
        upper=upper,
        middle=mid,
        lower=lower,
        bandwidth=bandwidth,
        percent_b=percent_b,
    )


# =====================================================================
# Crypto-Native Derivative & Microstructure Factor Helpers
# =====================================================================

def funding_rate_zscore(funding_rate: SeriesLike, window: int = 72) -> pd.Series:
    """Standardized z-score of perpetual funding rate to detect squeeze regime."""
    return zscore(funding_rate, window=window)


def oi_momentum(open_interest: SeriesLike, window: int = 24) -> pd.Series:
    """Rate of change (ROC) of open interest over window bars."""
    s = _to_series(open_interest)
    return s.pct_change(max(1, int(window)))


# =====================================================================
# Layer 3: Universal Series-Friendly TA-Lib Facade
# =====================================================================

def _wrap_talib_func(fn: Callable) -> Callable:
    """Wrap a TA-Lib C-function to automatically convert Series, alias params, and restore index."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        idx = None
        converted_args = []
        for arg in args:
            if isinstance(arg, (pd.Series, pd.DataFrame)):
                if idx is None and hasattr(arg, "index"):
                    idx = arg.index
                converted_args.append(np.asarray(arg, dtype=np.float64))
            else:
                converted_args.append(arg)

        # Handle parameter aliasing: window/length -> timeperiod
        if "window" in kwargs and "timeperiod" not in kwargs:
            kwargs["timeperiod"] = int(kwargs.pop("window"))
        if "length" in kwargs and "timeperiod" not in kwargs:
            kwargs["timeperiod"] = int(kwargs.pop("length"))

        res = fn(*converted_args, **kwargs)

        if isinstance(res, np.ndarray):
            return pd.Series(res, index=idx)
        if isinstance(res, tuple):
            return tuple(pd.Series(r, index=idx) if isinstance(r, np.ndarray) else r for r in res)
        return res

    return wrapper


def _resolve_talib_function(name: str) -> Callable | None:
    if _talib is None:
        return None
    candidates = [name, name.upper()]
    if "_" in name:
        candidates.append(name.replace("_", "").upper())
    for candidate in candidates:
        if hasattr(_talib, candidate):
            fn = getattr(_talib, candidate)
            if callable(fn):
                return _wrap_talib_func(fn)
    return None


def __getattr__(name: str) -> Any:
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

