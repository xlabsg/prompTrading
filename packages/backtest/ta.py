"""Compatibility shim for strategies that use `import ta`.

Supports:
- ta.rsi(close, timeperiod=14)
- ta.adx(high, low, close, timeperiod=14) (returns series indexable with ['ADX'])
- ta.bbands(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0) -> (upper, middle, lower)
- all other indicators forwarded to backtest.indicators and talib.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import indicators as _ind

try:
    import talib as _talib
except Exception:
    _talib = None


class _AdxResult(pd.Series):
    """Series that can also be accessed via item ['ADX'] or attribute .ADX."""
    @property
    def _constructor(self):
        return _AdxResult

    def __getitem__(self, key):
        if key in ("ADX", "adx"):
            return self
        return super().__getitem__(key)

    def __getattr__(self, name):
        if name in ("ADX", "adx"):
            return self
        return super().__getattr__(name)


def rsi(close, timeperiod: int = 14, **kwargs) -> pd.Series:
    period = kwargs.get("window") or kwargs.get("length") or timeperiod
    return _ind.rsi(close, window=int(period))


def adx(high, low, close, timeperiod: int = 14, **kwargs):
    period = kwargs.get("window") or kwargs.get("length") or timeperiod
    if _talib is not None:
        arr = _talib.ADX(
            np.asarray(high, dtype=float),
            np.asarray(low, dtype=float),
            np.asarray(close, dtype=float),
            timeperiod=int(period),
        )
        idx = getattr(close, "index", None)
        return _AdxResult(arr, index=idx)
    return _AdxResult(np.zeros(len(close)), index=getattr(close, "index", None))


class _BBandsResult(tuple):
    """Result tuple (upper, middle, lower) supporting both tuple unpacking and dict access."""

    def __new__(cls, upper, middle, lower):
        return super().__new__(cls, (upper, middle, lower))

    @property
    def upper(self):
        return self[0]

    @property
    def middle(self):
        return self[1]

    @property
    def lower(self):
        return self[2]

    def __getitem__(self, item):
        if isinstance(item, str):
            key = item.lower().replace("_", "")
            if "mid" in key or key == "bbm":
                return self[1]
            if "up" in key or key == "bbu":
                return self[0]
            if "low" in key or key == "bbl":
                return self[2]
            raise KeyError(f"Unknown BBands key: {item!r}. Expected 'middleband', 'upperband', or 'lowerband'")
        return super().__getitem__(item)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def bbands(close, timeperiod: int = 20, nbdevup: float = 2.0, nbdevdn: float = 2.0, matype: int = 0, **kwargs):
    period = kwargs.get("window") or kwargs.get("length") or timeperiod
    idx = getattr(close, "index", None)
    if _talib is not None:
        up, mid, low = _talib.BBANDS(
            np.asarray(close, dtype=float),
            timeperiod=int(period),
            nbdevup=float(nbdevup),
            nbdevdn=float(nbdevdn),
            matype=int(matype),
        )
        return _BBandsResult(pd.Series(up, index=idx), pd.Series(mid, index=idx), pd.Series(low, index=idx))
    c_s = pd.Series(close, copy=False).astype(float)
    mid = c_s.rolling(int(period)).mean()
    std = c_s.rolling(int(period)).std(ddof=0)
    up = mid + float(nbdevup) * std
    low = mid - float(nbdevdn) * std
    return _BBandsResult(pd.Series(up, index=idx), pd.Series(mid, index=idx), pd.Series(low, index=idx))


def __getattr__(name: str):
    return getattr(_ind, name)


def __dir__() -> list[str]:
    base = set(globals().keys())
    base.update(dir(_ind))
    return sorted(base)
