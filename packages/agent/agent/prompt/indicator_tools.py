"""
Dynamic indicator discovery and query tool.

Design:
- Tool-based: LLM can call get_indicator_info() during generation
- Truly dynamic: Discovers ALL TA-Lib functions at runtime
- Queryable: Search by name, category, or pattern
- No hardcoded lists: Uses TA-Lib's own function inspection

Usage as a tool:
    get_indicator_info(indicators=["MACD", "RSI", "BBANDS"])
    list_all_indicators(category="momentum")
"""

from __future__ import annotations

import inspect
import re
from typing import Any

# Try to import TA-Lib for dynamic discovery
try:
    import talib
    _TALIB_AVAILABLE = True
except Exception:
    _TALIB_AVAILABLE = False

from backtest import indicators as builtin_indicators


def _get_builtin_indicators() -> dict[str, dict[str, Any]]:
    """Get built-in indicator docs by inspecting the module."""
    result = {}

    # Known built-in indicators (not everything in the module)
    BUILTIN_INDICATOR_NAMES = {
        "sma", "ema", "rsi", "zscore", "atr",
        "cross_over", "cross_under",
    }

    for name in BUILTIN_INDICATOR_NAMES:
        if not hasattr(builtin_indicators, name):
            continue
        obj = getattr(builtin_indicators, name)
        if not callable(obj):
            continue

        # Get signature
        try:
            sig = inspect.signature(obj)
            signature = f"{name}{sig}"
        except Exception:
            signature = f"{name}(...)"

        # Get docstring
        doc = inspect.getdoc(obj) or ""
        first_line = doc.split("\n")[0] if doc else ""

        # Determine category
        if name in ["sma", "ema"]:
            category = "trend"
        elif name == "rsi":
            category = "momentum"
        elif name in ["atr"]:
            category = "volatility"
        elif name in ["cross_over", "cross_under"]:
            category = "signal"
        else:
            category = "statistical"

        result[name] = {
            "signature": signature,
            "description": first_line,
            "category": category,
            "source": "builtin",
        }
    return result


def _get_talib_indicators() -> dict[str, dict[str, Any]]:
    """Get ALL TA-Lib indicators by dynamic inspection."""
    if not _TALIB_AVAILABLE:
        return {}

    result = {}

    # TA-Lib function patterns to identify different types
    # Pattern recognition functions start with "CDL"
    # Cycle functions start with "HT_"
    # Math functions like sin/cos/acos should be excluded

    EXCLUDED_PATTERNS = {
        # Math functions (not trading indicators)
        "acos", "asin", "atan", "atan2", "ceil", "cos", "cosh", "exp", "floor",
        "log", "log10", "max", "min", "pow", "round", "sin", "sinh", "sqrt",
        "tan", "tanh",
        # Statistical helper functions (not standalone indicators)
        "beta", "correl", "linearreg", "linearreg_angle", "linearreg_intercept",
        "linearreg_slope", "stddev", "tsf", "var",
        # Price transform (simple calculations)
        "avgprice", "medprice", "typprice", "wclprice",
        # Math operators
        "add", "div", "maxindex", "minindex", "minmax", "mult", "sub", "sum",
    }

    CATEGORY_PATTERNS = {
        # Overlap Studies (trend following)
        "sma": "trend", "ema": "trend", "wma": "trend", "dema": "trend",
        "tema": "trend", "trima": "trend", "kama": "trend", "mama": "trend",
        "t3": "trend", "bbands": "trend", "midpoint": "trend", "midprice": "trend",
        "sar": "trend", "arex": "trend",
        # Momentum Indicators
        "adx": "trend", "adxr": "trend", "apo": "momentum", "aroon": "momentum",
        "aroonosc": "momentum", "bop": "momentum", "cci": "momentum",
        "cmo": "momentum", "dx": "momentum", "macd": "momentum",
        "macdext": "momentum", "macdfix": "momentum", "mfi": "momentum",
        "minus_di": "trend", "minus_dm": "momentum", "mom": "momentum",
        "plus_di": "trend", "plus_dm": "momentum", "ppo": "momentum",
        "roc": "momentum", "rocp": "momentum", "rocr": "momentum",
        "rocr100": "momentum", "rsi": "momentum", "stoch": "momentum",
        "stochf": "momentum", "stochrsi": "momentum", "trix": "momentum",
        "ultosc": "momentum", "willr": "momentum",
        # Volume Indicators
        "ad": "volume", "adosc": "volume", "obv": "volume",
        # Volatility Indicators
        "atr": "volatility", "natr": "volatility", "trange": "volatility",
        # Cycle Indicators
        "ht_dcperiod": "cycle", "ht_dcphase": "cycle", "ht_phasor": "cycle",
        "ht_sine": "cycle", "ht_trendmode": "trend",
    }

    # Get ALL functions from TA-Lib
    for name in dir(talib):
        if name.startswith("_"):
            continue

        obj = getattr(talib, name, None)
        if not callable(obj):
            continue

        # Skip excluded math/stat functions
        name_lower = name.lower()
        if name_lower in EXCLUDED_PATTERNS:
            continue
        # Skip single-letter or very short names (usually math ops)
        if len(name) <= 3 and not name.startswith("CDL"):
            if name.isupper() and name not in ["ADX", "MFI", "WILLR", "ROC"]:
                continue

        # Get signature with proper defaults
        try:
            sig = inspect.signature(obj)
            # Build readable signature
            params = []
            param_defaults = {
                "timeperiod": "14",
                "fastperiod": "12", "slowperiod": "26", "signalperiod": "9",
                "nbdevup": "2", "nbdevdn": "2", "matype": "0",
                "fastk_period": "14", "slowk_period": "3", "slowd_period": "3",
            }

            for pname, param in sig.parameters.items():
                if pname == "real" or pname == "high" or pname == "low" or pname == "close" or pname == "open" or pname == "volume":
                    params.append(pname)  # Data parameters
                elif pname in param_defaults:
                    params.append(f"{pname}={param_defaults[pname]}")
                elif param.default == inspect.Parameter.empty:
                    params.append(pname)
                else:
                    params.append(f"{pname}={param.default}")

            signature = f"{name}({', '.join(params)})"
        except Exception:
            signature = f"{name}(...)"

        # Get docstring
        doc = inspect.getdoc(obj) or ""
        first_line = doc.split("\n")[0] if doc else ""

        # Determine category
        category = "other"
        name_lower = name.lower()

        # Check known patterns
        if name.startswith("CDL"):
            category = "pattern"
        elif name.startswith("HT_"):
            category = "cycle"
        else:
            # Check against known patterns
            for pattern, cat in CATEGORY_PATTERNS.items():
                if name_lower.startswith(pattern):
                    category = cat
                    break

        result[name.lower()] = {
            "signature": signature,
            "description": first_line,
            "category": category,
            "source": "talib",
        }

    return result


# Cache the discovery results
_INDICATOR_CACHE: dict[str, dict[str, Any]] | None = None


def _discover_all_indicators() -> dict[str, dict[str, Any]]:
    """Discover ALL available indicators (built-in + TA-Lib)."""
    global _INDICATOR_CACHE
    if _INDICATOR_CACHE is not None:
        return _INDICATOR_CACHE

    result = {}
    result.update(_get_builtin_indicators())
    result.update(_get_talib_indicators())

    _INDICATOR_CACHE = result
    return result


def _resolve_indicator_name(name: str) -> str | None:
    """Resolve an indicator name or alias to its canonical key."""
    all_indicators = _discover_all_indicators()

    # Direct match (case-insensitive)
    name_lower = name.lower()
    if name_lower in all_indicators:
        return name_lower

    # Check if any key starts with this name
    for key in all_indicators:
        if key.startswith(name_lower):
            return key

    # Check if any key contains this name
    for key in all_indicators:
        if name_lower in key:
            return key

    return None


def get_indicator_info(
    indicators: list[str] | str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
) -> str:
    """
    Tool: Get indicator documentation.

    Query the dynamic indicator registry for detailed documentation.

    Args:
        indicators: Specific indicator names (e.g., ["MACD", "RSI"])
        category: Filter by category (trend, momentum, volatility, volume, pattern, cycle)
        search: Search term in description/name
        limit: Max results to return

    Returns:
        Formatted documentation string.

    Examples:
        # Get specific indicators
        get_indicator_info(indicators=["MACD", "RSI"])

        # Get all momentum indicators
        get_indicator_info(category="momentum")

        # Search for pattern
        get_indicator_info(search="bollinger")

        # Discovery mode - get sample indicators
        get_indicator_info(limit=10)
    """
    all_indicators = _discover_all_indicators()

    # Filter results
    if indicators:
        if isinstance(indicators, str):
            indicators = [indicators]
        results = {}
        for name in indicators:
            resolved = _resolve_indicator_name(name)
            if resolved and resolved in all_indicators:
                results[resolved] = all_indicators[resolved]
    elif category:
        category_lower = category.lower()
        results = {
            k: v for k, v in all_indicators.items()
            if v.get("category", "").lower() == category_lower
        }
    elif search:
        search_lower = search.lower()
        results = {}
        for k, v in all_indicators.items():
            if search_lower in k or search_lower in v.get("description", "").lower():
                results[k] = v
    else:
        results = all_indicators

    # Limit results
    if limit and len(results) > limit:
        results = dict(sorted(results.items())[:limit])

    # Format output
    if not results:
        cats = set(v.get("category", "") for v in all_indicators.values())
        return f"No indicators found. Available categories: {', '.join(sorted(cats))}"

    # Group by category
    by_category: dict[str, list[str]] = {}
    for name, info in results.items():
        cat = info.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(name)

    # Build output
    lines = [f"Found {len(results)} indicator(s):\n"]

    category_order = ["trend", "momentum", "volatility", "volume", "signal", "pattern", "cycle", "statistical", "other"]
    for cat in category_order:
        if cat not in by_category:
            continue
        lines.append(f"\n## {cat.title()}")
        for name in sorted(by_category[cat]):
            info = results[name]
            sig = info.get("signature", f"{name}(...)")
            desc = info.get("description", "")
            source = info.get("source", "")
            lines.append(f"  {sig}")
            if desc:
                lines.append(f"    {desc}")

    return "\n".join(lines)


def list_all_indicators(
    category: str | None = None,
    format: str = "names",
) -> list[str] | dict:
    """
    Tool: List ALL available indicators.

    Complete discovery of all built-in and TA-Lib indicators.

    Args:
        category: Filter by category (optional)
        format: "names" for list, "json" for full dict

    Returns:
        List of indicator names or full info dict.

    Examples:
        # List all indicator names
        list_all_indicators()

        # List momentum indicators only
        list_all_indicators(category="momentum")

        # Get full info
        list_all_indicators(format="json")
    """
    all_indicators = _discover_all_indicators()

    if category:
        category_lower = category.lower()
        all_indicators = {
            k: v for k, v in all_indicators.items()
            if v.get("category", "").lower() == category_lower
        }

    if format == "names":
        return sorted(all_indicators.keys())
    else:  # json
        return dict(sorted(all_indicators.items()))


def get_signature(name: str) -> str | None:
    """
    Tool: Get function signature for a specific indicator.

    Args:
        name: Indicator name (case-insensitive)

    Returns:
        Function signature string or None if not found.

    Examples:
        get_signature("MACD")
        # Returns: "MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)"
    """
    all_indicators = _discover_all_indicators()
    key = name.lower()

    if key in all_indicators:
        return all_indicators[key].get("signature")

    # Try case-insensitive search
    for k, v in all_indicators.items():
        if k.lower() == key:
            return v.get("signature")

    return None


def get_categories() -> list[str]:
    """Get all available indicator categories."""
    all_indicators = _discover_all_indicators()
    return sorted(set(v.get("category", "other") for v in all_indicators.values()))


# Summary for LLM prompt
_TOOL_SUMMARY = """
## Available Indicator Tools

You have access to dynamic indicator discovery tools:

1. get_indicator_info(indicators=["MACD", "RSI"], category="momentum", search="pattern", limit=20)
   - Get detailed docs for specific indicators
   - Filter by category or search term
   - Use limit to control results

2. list_all_indicators(category="momentum", format="names")
   - List all available indicator names
   - Discovery mode for exploring

3. get_signature("MACD")
   - Get function signature for a single indicator

4. get_categories()
   - Get all available categories

These tools dynamically discover ALL TA-Lib and built-in indicators.
"""


def build_discovery_prompt(max_examples: int = 10) -> str:
    """Build the discovery-enabled prompt for LLM."""
    all_indicators = _discover_all_indicators()
    categories = get_categories()

    # Get a sample of indicators for each category
    samples_by_cat: dict[str, list[str]] = {}
    for name, info in all_indicators.items():
        cat = info.get("category", "other")
        if cat not in samples_by_cat:
            samples_by_cat[cat] = []
        if len(samples_by_cat[cat]) < max_examples:
            samples_by_cat[cat].append(name)

    lines = [_TOOL_SUMMARY]
    lines.append(f"\nDiscovered {len(all_indicators)} total indicators across {len(categories)} categories.")
    lines.append(f"\nCategories: {', '.join(categories)}")

    lines.append("\n## Sample Indicators by Category")
    for cat in sorted(samples_by_cat.keys()):
        samples = sorted(samples_by_cat[cat])[:max_examples]
        lines.append(f"\n### {cat.title()}")
        for name in samples:
            info = all_indicators[name]
            sig = info.get("signature", f"{name}(...)")
            lines.append(f"  {sig}")

    lines.append("\n## Core Built-in Indicators (Always Available)")
    lines.append("  sma(x, window: int) -> pd.Series")
    lines.append("  ema(x, window: int) -> pd.Series")
    lines.append("  rsi(close, window: int = 14) -> pd.Series")
    lines.append("  cross_over(a, b) -> pd.Series[bool]")
    lines.append("  cross_under(a, b) -> pd.Series[bool]")
    lines.append("  atr(high, low, close, window: int = 14) -> pd.Series")
    lines.append("  zscore(x, window: int) -> pd.Series")

    return "\n".join(lines)


__all__ = [
    "get_indicator_info",
    "list_all_indicators",
    "get_signature",
    "get_categories",
    "build_discovery_prompt",
    "_discover_all_indicators",
]
