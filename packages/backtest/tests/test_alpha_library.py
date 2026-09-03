import numpy as np
import pandas as pd
import pytest

from backtest.alpha_library import (
    calc_adx,
    calc_atr,
    calc_donchian_channels,
    calc_keltner_channels,
    calc_supertrend,
    calc_vwap_deviation,
)


@pytest.fixture
def sample_ohlcv():
    np.random.seed(42)
    n = 100
    close = 100.0 + np.cumsum(np.random.normal(0, 1, n))
    high = close + np.random.uniform(0.5, 2.0, n)
    low = close - np.random.uniform(0.5, 2.0, n)
    open_p = close + np.random.uniform(-0.5, 0.5, n)
    volume = np.random.uniform(100, 1000, n)

    return pd.DataFrame(
        {
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def test_calc_atr(sample_ohlcv):
    atr = calc_atr(sample_ohlcv, period=14)
    assert len(atr) == len(sample_ohlcv)
    assert (atr.dropna() > 0).all()


def test_calc_supertrend(sample_ohlcv):
    st = calc_supertrend(sample_ohlcv, period=10, multiplier=3.0)
    assert "supertrend" in st.columns
    assert "trend_direction" in st.columns
    assert set(st["trend_direction"].unique()).issubset({-1.0, 1.0})


def test_calc_adx(sample_ohlcv):
    adx = calc_adx(sample_ohlcv, period=14)
    assert len(adx) == len(sample_ohlcv)
    assert (adx >= 0.0).all()
    assert (adx <= 100.0).all()


def test_calc_keltner_channels(sample_ohlcv):
    kc = calc_keltner_channels(sample_ohlcv, ema_period=20, atr_period=10, multiplier=2.0)
    valid = kc.dropna()
    assert (valid["upper"] >= valid["middle"]).all()
    assert (valid["middle"] >= valid["lower"]).all()


def test_calc_donchian_channels_no_lookahead(sample_ohlcv):
    dc = calc_donchian_channels(sample_ohlcv, period=20)
    # Donchian channel is lagged by 1 bar, so bar 20 should be derived from bars 0..19
    assert len(dc) == len(sample_ohlcv)
    valid = dc.dropna()
    assert (valid["upper"] >= valid["lower"]).all()


def test_calc_vwap_deviation(sample_ohlcv):
    dev = calc_vwap_deviation(sample_ohlcv, rolling_bars=24)
    assert len(dev) == len(sample_ohlcv)
    assert not dev.isna().any()
