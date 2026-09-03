"""
Indicator documentation registry and smart retrieval.

Design:
- Scalable: Support 100+ indicators without bloating prompts
- Smart: Only include docs for indicators mentioned in user request
- Fallback: Always include core indicators for basic strategies

Usage:
    docs = get_relevant_indicator_docs("Use MACD and RSI for entry")
    # Returns docs for MACD and RSI only
"""

from __future__ import annotations

import re
from typing import Any


# Comprehensive indicator registry with signatures and documentation
# This can be extended to 100+ indicators without impacting prompt size
_INDICATOR_REGISTRY: dict[str, dict[str, str]] = {
    # === Core Built-in ===
    "sma": {
        "signature": "sma(x, window: int) -> pd.Series",
        "description": "Simple moving average over window periods",
        "category": "trend",
    },
    "ema": {
        "signature": "ema(x, window: int) -> pd.Series",
        "description": "Exponential moving average (weights recent prices more)",
        "category": "trend",
    },
    "rsi": {
        "signature": "rsi(close, window: int = 14) -> pd.Series",
        "description": "Relative Strength Index (0-100). >70 overbought, <30 oversold",
        "category": "momentum",
    },
    "zscore": {
        "signature": "zscore(x, window: int) -> pd.Series",
        "description": "Rolling z-score (std from mean). Use for mean reversion",
        "category": "statistical",
    },
    "atr": {
        "signature": "atr(high, low, close, window: int = 14) -> pd.Series",
        "description": "Average True Range. Measures volatility for dynamic stops",
        "category": "volatility",
    },
    "cross_over": {
        "signature": "cross_over(a, b) -> pd.Series[bool]",
        "description": "True when series a crosses ABOVE series b",
        "category": "signal",
    },
    "cross_under": {
        "signature": "cross_under(a, b) -> pd.Series[bool]",
        "description": "True when series a crosses BELOW series b",
        "category": "signal",
    },
    # === Alpha Library (Zero-Lookahead Building Blocks) ===
    "supertrend": {
        "signature": "calc_supertrend(df, period=10, multiplier=3.0) -> pd.DataFrame",
        "description": "SuperTrend indicator. Returns DataFrame with ['supertrend', 'trend_direction'] (1=bull, -1=bear)",
        "category": "trend",
    },
    "keltner": {
        "signature": "calc_keltner_channels(df, ema_period=20, atr_period=10, multiplier=2.0) -> pd.DataFrame",
        "description": "Keltner Channels with EMA centerline and ATR volatility bands. Returns ['middle', 'upper', 'lower']",
        "category": "volatility",
    },
    "donchian": {
        "signature": "calc_donchian_channels(df, period=20) -> pd.DataFrame",
        "description": "Donchian Channels breakout bands (lagged by 1 bar to prevent lookahead). Returns ['upper', 'middle', 'lower']",
        "category": "breakout",
    },
    "vwap_deviation": {
        "signature": "calc_vwap_deviation(df, rolling_bars=24) -> pd.Series",
        "description": "Rolling VWAP Z-score deviation for volume-weighted mean reversion",
        "category": "mean_reversion",
    },
    # === TA-Lib Momentum ===
    "macd": {
        "signature": "MACD(close, fastperiod=12, slowperiod=26, signalperiod=9) -> tuple[np.ndarray, np.ndarray, np.ndarray]",
        "description": "Returns (macd, signal, hist). Histogram >0 = bullish",
        "category": "momentum",
    },
    "stoch": {
        "signature": "STOCH(high, low, close, fastk_period=14, slowk_period=3) -> tuple[np.ndarray, np.ndarray]",
        "description": "Stochastic Oscillator. Returns (slowk, slowd). Values 0-100",
        "category": "momentum",
    },
    "cci": {
        "signature": "CCI(high, low, close, timeperiod=14) -> pd.Series",
        "description": "Commodity Channel Index. >100 overbought, <-100 oversold",
        "category": "momentum",
    },
    "mfi": {
        "signature": "MFI(high, low, close, volume, timeperiod=14) -> pd.Series",
        "description": "Money Flow Index (volume-weighted RSI). >80 overbought, <20 oversold",
        "category": "momentum",
    },
    "willr": {
        "signature": "WILLR(high, low, close, timeperiod=14) -> pd.Series",
        "description": "Williams %R. -20 to -80 range. >-20 overbought, <-80 oversold",
        "category": "momentum",
    },
    "roc": {
        "signature": "ROC(close, timeperiod=10) -> pd.Series",
        "description": "Rate of Change (% price change over n periods)",
        "category": "momentum",
    },
    # === TA-Lib Trend ===
    "bbands": {
        "signature": "BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2) -> tuple[np.ndarray, np.ndarray, np.ndarray]",
        "description": "Bollinger Bands. Returns (upper, middle, lower)",
        "category": "trend",
    },
    "sar": {
        "signature": "SAR(high, low, acceleration=0.02, maximum=0.2) -> pd.Series",
        "description": "Parabolic SAR. Use for trailing stops. Price below = short, above = long",
        "category": "trend",
    },
    "adx": {
        "signature": "ADX(high, low, close, timeperiod=14) -> pd.Series",
        "description": "Average Directional Index. >25 = trending, <20 = ranging",
        "category": "trend",
    },
    "minus_di": {
        "signature": "MINUS_DI(high, low, close, timeperiod=14) -> pd.Series",
        "description": "Negative Directional Indicator. Falling momentum",
        "category": "trend",
    },
    "plus_di": {
        "signature": "PLUS_DI(high, low, close, timeperiod=14) -> pd.Series",
        "description": "Positive Directional Indicator. Rising momentum",
        "category": "trend",
    },
    # === TA-Lib Volume ===
    "obv": {
        "signature": "OBV(close, volume) -> pd.Series",
        "description": "On-Balance Volume. Cumulative volume with +/- direction",
        "category": "volume",
    },
    "ad": {
        "signature": "AD(high, low, close, volume) -> pd.Series",
        "description": "Chaikin A/D Line. Accumulation/distribution with volume weighting",
        "category": "volume",
    },
    # === TA-Lib Volatility ===
    "natr": {
        "signature": "NATR(high, low, close, timeperiod=14) -> pd.Series",
        "description": "Normalized ATR (as percentage). Useful for position sizing",
        "category": "volatility",
    },
    # === TA-Lib Overlap Studies ===
    "wma": {
        "signature": "WMA(close, timeperiod=30) -> pd.Series",
        "description": "Weighted Moving Average (linear weighting)",
        "category": "trend",
    },
    "tema": {
        "signature": "TEMA(close, timeperiod=30) -> pd.Series",
        "description": "Triple Exponential Moving Average (faster response to price)",
        "category": "trend",
    },
    "kama": {
        "signature": "KAMA(close, timeperiod=30) -> pd.Series",
        "description": "Kaufman Adaptive Moving Average (adjusts to volatility)",
        "category": "trend",
    },
    "mama": {
        "signature": "MAMA(close, fastlimit=0.5, slowlimit=0.05) -> tuple[np.ndarray, np.ndarray]",
        "description": "MESA Adaptive Moving Average. Returns (mama, fama)",
        "category": "trend",
    },
    "t3": {
        "signature": "T3(close, timeperiod=5, vfactor=0.7) -> pd.Series",
        "description": "T3 Moving Average (smoothed, lag-reduced)",
        "category": "trend",
    },
    # === TA-Lib Cycle ===
    "ht_dcperiod": {
        "signature": "HT_DCPERIOD(close) -> pd.Series",
        "description": "Hilbert Transform - Dominant Cycle Period",
        "category": "cycle",
    },
    "ht_trendmode": {
        "signature": "HT_TRENDMODE(close) -> pd.Series",
        "description": "Hilbert Transform - Trend vs Cycle Mode (1=trend, 0=cycle)",
        "category": "cycle",
    },
    # === TA-Lib Pattern Recognition ===
    "cdl_doji": {
        "signature": "CDLDOJI(open, high, low, close) -> pd.Series[int]",
        "description": "Doji candle pattern (indecision). Returns +100, -100, or 0",
        "category": "pattern",
    },
    "cdl_engulfing": {
        "signature": "CDLENGULFING(open, high, low, close) -> pd.Series[int]",
        "description": "Engulfing pattern. +100 bullish, -100 bearish",
        "category": "pattern",
    },
    "cdl_hammer": {
        "signature": "CDLHAMMER(open, high, low, close) -> pd.Series[int]",
        "description": "Hammer candlestick (bullish reversal at bottom)",
        "category": "pattern",
    },
    "cdl_shooting_star": {
        "signature": "CDLSHOOTINGSTAR(open, high, low, close) -> pd.Series[int]",
        "description": "Shooting Star (bearish reversal at top)",
        "category": "pattern",
    },
    "cdl_morning_star": {
        "signature": "CDLMORNINGSTAR(open, high, low, close) -> pd.Series[int]",
        "description": "Morning Star (bullish reversal pattern)",
        "category": "pattern",
    },
    "cdl_evening_star": {
        "signature": "CDLEVENINGSTAR(open, high, low, close) -> pd.Series[int]",
        "description": "Evening Star (bearish reversal pattern)",
        "category": "pattern",
    },
}

# Aliases for common alternate names
_INDICATOR_ALIASES: dict[str, str] = {
    "moving average": "sma",
    "moving avg": "sma",
    "ma": "sma",
    "bollinger": "bbands",
    "bollinger bands": "bbands",
    "stochastic": "stoch",
    "williams": "willr",
    "williams %r": "willr",
    "rate of change": "roc",
    "money flow": "mfi",
    "on balance volume": "obv",
    "parabolic": "sar",
    "parabolic sar": "sar",
    "triple ema": "tema",
    "weighted ma": "wma",
    "kaufman": "kama",
}

# Core indicators always included (fallback)
_CORE_INDICATORS = ["sma", "ema", "rsi", "cross_over", "cross_under"]


def _extract_indicator_names(text: str) -> set[str]:
    """Extract indicator names mentioned in user request.

    Looks for:
    1. Direct names: "rsi", "macd", "bollinger"
    2. Aliases: "moving average" -> sma
    3. Category keywords: "momentum", "trend", "volume"

    Args:
        text: User's request text.

    Returns:
        Set of indicator keys found.
    """
    text_lower = text.lower()
    found = set()

    # Direct name matching
    for name in _INDICATOR_REGISTRY:
        if name.lower() in text_lower:
            found.add(name)

    # Alias matching
    for alias, canonical in _INDICATOR_ALIASES.items():
        if alias.lower() in text_lower:
            found.add(canonical)

    # Category hints (add related indicators)
    category_keywords = {
        "momentum": ["rsi", "stoch", "macd", "cci", "mfi", "willr", "roc"],
        "trend": ["sma", "ema", "adx", "sar", "bbands"],
        "volatility": ["atr", "natr"],
        "volume": ["obv", "ad", "mfi"],
        "overbought": ["rsi", "stoch", "cci"],
        "oversold": ["rsi", "stoch", "cci"],
        "breakout": ["bbands", "adx"],
        "reversal": ["rsi", "stoch", "sar"],
    }

    for keyword, related in category_keywords.items():
        if keyword in text_lower:
            # Add one or two from the category to avoid bloating
            found.update(related[:2])

    return found


def _format_indicator_doc(key: str, info: dict[str, str]) -> str:
    """Format a single indicator's documentation.

    Args:
        key: Indicator name.
        info: Indicator info dict.

    Returns:
        Formatted documentation string.
    """
    signature = info["signature"]
    description = info["description"]
    return f"  {signature}\n    {description}"


def build_indicator_docs(
    user_prompt: str = "",
    *,
    max_indicators: int = 8,
    always_include_core: bool = True,
) -> str:
    """Build indicator documentation based on user request.

    Smart retrieval:
    1. Parse user prompt for mentioned indicators
    2. Include docs for those indicators
    3. Fall back to core indicators if none found
    4. Limit to max_indicators to control prompt size

    Args:
        user_prompt: The user's strategy request text.
        max_indicators: Maximum number of indicators to document.
        always_include_core: Always include core indicators.

    Returns:
        Formatted indicator documentation string.
    """
    mentioned = _extract_indicator_names(user_prompt)

    # Determine which indicators to document
    if mentioned and not always_include_core:
        selected = list(mentioned)[:max_indicators]
    elif mentioned:
        # Prioritize mentioned, then fill with core
        selected = list(mentioned) + [c for c in _CORE_INDICATORS if c not in mentioned]
        selected = selected[:max_indicators]
    else:
        # No indicators mentioned, use core
        selected = _CORE_INDICATORS[:max_indicators]

    # Build output by category
    by_category: dict[str, list[str]] = {}
    for key in selected:
        if key not in _INDICATOR_REGISTRY:
            continue
        info = _INDICATOR_REGISTRY[key]
        cat = info.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(key)

    # Format output
    lines = ["Available Indicators (from backtest.indicators):"]

    category_order = ["trend", "momentum", "volatility", "volume", "signal", "pattern", "statistical", "cycle", "other"]
    for cat in category_order:
        if cat not in by_category:
            continue
        lines.append(f"\n# {cat.title()}")
        for key in by_category[cat]:
            lines.append(_format_indicator_doc(key, _INDICATOR_REGISTRY[key]))

    # Add usage examples
    lines.append("\n# Usage Examples")
    if "sma" in selected or "ema" in selected:
        lines.extend([
            "  fast_ma = sma(close, 10)",
            "  slow_ma = sma(close, 30)",
            "  entries = cross_over(fast_ma, slow_ma)",
        ])
    if "rsi" in selected:
        lines.extend([
            "  rsi_val = rsi(close, 14)",
            "  exits = (rsi_val > 70)  # Overbought exit",
        ])
    if "bbands" in selected:
        lines.extend([
            "  bb_upper, bb_mid, bb_lower = BBANDS(close, 20, nbdevup=2, nbdevdn=2)",
            "  bb_mid = pd.Series(bb_mid, index=data.index)",
            "  entries = close < bb_mid  # Example usage",
        ])
    if "macd" in selected:
        lines.extend([
            "  macd_line, macd_signal, macd_hist = MACD(close)",
            "  macd_line = pd.Series(macd_line, index=data.index)",
            "  macd_signal = pd.Series(macd_signal, index=data.index)",
            "  entries = macd_line > macd_signal",
        ])

    # Note about TA-Lib
    if any(k in selected for k in ["macd", "bbands", "stoch", "mama"]):
        lines.append(
            "\nNote: Multi-output TA-Lib functions return tuples, not dicts. "
            "Unpack first, then wrap arrays with pd.Series(..., index=data.index) when needed."
        )

    return "\n".join(lines)


def get_all_indicator_names() -> list[str]:
    """Get all available indicator names.

    Useful for:
    - Validation
    - UI autocomplete
    - Testing

    Returns:
        List of all indicator keys.
    """
    return list(_INDICATOR_REGISTRY.keys())


def get_indicator_info(name: str) -> dict[str, str] | None:
    """Get info for a specific indicator.

    Args:
        name: Indicator name or alias.

    Returns:
        Indicator info dict or None if not found.
    """
    # Check direct name
    if name in _INDICATOR_REGISTRY:
        return _INDICATOR_REGISTRY[name]

    # Check alias
    if name in _INDICATOR_ALIASES:
        return _INDICATOR_REGISTRY[_INDICATOR_ALIASES[name]]

    # Check case-insensitive
    lower_name = name.lower()
    for key, value in _INDICATOR_REGISTRY.items():
        if key.lower() == lower_name:
            return value

    return None


__all__ = [
    "build_indicator_docs",
    "get_all_indicator_names",
    "get_indicator_info",
]
