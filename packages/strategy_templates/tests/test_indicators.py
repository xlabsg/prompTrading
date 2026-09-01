"""Unit tests for strategy template indicators."""

import pandas as pd
import numpy as np
import pytest

from strategy_templates.shared.indicators import (
    sma,
    ema,
    rsi,
    macd,
    stochastic,
    bollinger_bands,
    atr,
    detect_pivots,
)


@pytest.fixture
def sample_ohlcv():
    """Create sample OHLCV data for testing."""
    np.random.seed(42)
    n = 100

    # Generate realistic price data
    close = np.cumsum(np.random.randn(n) * 10) + 1000
    high = close + np.abs(np.random.randn(n) * 5)
    low = close - np.abs(np.random.randn(n) * 5)
    open_ = close + np.random.randn(n) * 2
    volume = np.random.randint(1000, 10000, n)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestSMA:
    """Tests for Simple Moving Average."""

    def test_sma_basic(self, sample_ohlcv):
        result = sma(sample_ohlcv["close"], 10)
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlcv)
        assert result.isna().sum() == 0

    def test_sma_window_size(self, sample_ohlcv):
        result = sma(sample_ohlcv["close"], 20)
        # SMA should smooth the data
        assert result.std() < sample_ohlcv["close"].std()


class TestEMA:
    """Tests for Exponential Moving Average."""

    def test_ema_basic(self, sample_ohlcv):
        result = ema(sample_ohlcv["close"], 10)
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlcv)

    def test_ema_vs_sma(self, sample_ohlcv):
        ema_result = ema(sample_ohlcv["close"], 10)
        sma_result = sma(sample_ohlcv["close"], 10)
        # EMA should react faster to price changes
        assert ema_result.iloc[-1] != sma_result.iloc[-1]


class TestRSI:
    """Tests for Relative Strength Index."""

    def test_rsi_basic(self, sample_ohlcv):
        result = rsi(sample_ohlcv["close"], 14)
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlcv)

    def test_rsi_range(self, sample_ohlcv):
        result = rsi(sample_ohlcv["close"], 14)
        # RSI should be between 0 and 100
        assert result.min() >= 0
        assert result.max() <= 100


class TestMACD:
    """Tests for MACD indicator."""

    def test_macd_basic(self, sample_ohlcv):
        macd_line, signal_line, histogram = macd(sample_ohlcv["close"])
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)
        assert len(macd_line) == len(sample_ohlcv)

    def test_macd_relationship(self, sample_ohlcv):
        macd_line, signal_line, histogram = macd(sample_ohlcv["close"])
        # Histogram should be MACD - Signal
        calculated_hist = macd_line - signal_line
        assert np.allclose(histogram, calculated_hist, equal_nan=True)


class TestStochastic:
    """Tests for Stochastic Oscillator."""

    def test_stochastic_basic(self, sample_ohlcv):
        k_percent, d_percent = stochastic(
            sample_ohlcv["high"],
            sample_ohlcv["low"],
            sample_ohlcv["close"],
        )
        assert isinstance(k_percent, pd.Series)
        assert isinstance(d_percent, pd.Series)

    def test_stochastic_range(self, sample_ohlcv):
        k_percent, d_percent = stochastic(
            sample_ohlcv["high"],
            sample_ohlcv["low"],
            sample_ohlcv["close"],
        )
        # %K and %D should be between 0 and 100
        assert k_percent.max() <= 100
        assert d_percent.max() <= 100


class TestBollingerBands:
    """Tests for Bollinger Bands."""

    def test_bollinger_bands_basic(self, sample_ohlcv):
        upper, middle, lower = bollinger_bands(sample_ohlcv["close"])
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)

    def test_bollinger_bands_relationship(self, sample_ohlcv):
        upper, middle, lower = bollinger_bands(sample_ohlcv["close"])
        # Upper band should be >= middle >= lower band
        assert (upper >= middle).all()
        assert (middle >= lower).all()


class TestATR:
    """Tests for Average True Range."""

    def test_atr_basic(self, sample_ohlcv):
        result = atr(
            sample_ohlcv["high"],
            sample_ohlcv["low"],
            sample_ohlcv["close"],
        )
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlcv)

    def test_atr_positive(self, sample_ohlcv):
        result = atr(
            sample_ohlcv["high"],
            sample_ohlcv["low"],
            sample_ohlcv["close"],
        )
        # ATR should always be positive
        assert (result >= 0).all()


class TestDetectPivots:
    """Tests for pivot detection."""

    def test_detect_pivots_basic(self, sample_ohlcv):
        pivot_highs, pivot_lows = detect_pivots(
            sample_ohlcv["high"],
            sample_ohlcv["low"],
            window=3,
        )
        assert isinstance(pivot_highs, pd.Series)
        assert isinstance(pivot_lows, pd.Series)

    def test_detect_pivots_count(self, sample_ohlcv):
        pivot_highs, pivot_lows = detect_pivots(
            sample_ohlcv["high"],
            sample_ohlcv["low"],
            window=3,
        )
        # Should have some pivots
        assert pivot_highs.sum() > 0 or pivot_lows.sum() > 0
