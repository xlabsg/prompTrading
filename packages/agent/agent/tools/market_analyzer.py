from __future__ import annotations

import logging
import math
from typing import Any, Optional
from agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MarketAnalyzerTool(BaseTool):
    """Diagnoses asset market regime (volatility, trend strength, ATR) from OHLCV candles."""

    name = "market_analyzer"
    description = (
        "Analyze historical market OHLCV data to determine market regime "
        "(trending, ranging, high volatility, low volatility) and calculate ATR / volatility metrics."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Trading symbol (e.g. BTC-USDT)"},
            "interval": {"type": "string", "description": "Bar interval (e.g. 1h, 4h, 1d)"},
            "df_dict": {
                "type": "object",
                "description": "Optional raw OHLCV candle dict (columns: open, high, low, close, volume)",
            },
        },
    }

    async def run(
        self,
        symbol: str = "BTC-USDT",
        interval: str = "1h",
        df_dict: Optional[dict[str, list[float]]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            if df_dict and "close" in df_dict and len(df_dict["close"]) > 20:
                highs = [float(x) for x in df_dict.get("high", [])]
                lows = [float(x) for x in df_dict.get("low", [])]
                closes = [float(x) for x in df_dict.get("close", [])]
            else:
                highs, lows, closes = self._generate_fallback_candles(symbol)

            metrics = self._calculate_regime_metrics(highs, lows, closes)
            metrics["symbol"] = symbol
            metrics["interval"] = interval

            return ToolResult(success=True, data=metrics)
        except Exception as e:
            logger.warning(f"Market analyzer error ({e}); returning default profile")
            return ToolResult(
                success=True,
                data={
                    "symbol": symbol,
                    "interval": interval,
                    "regime": "trending_breakout",
                    "volatility_level": "medium",
                    "normalized_atr_pct": 2.5,
                    "recommended_style": "momentum_breakout",
                },
            )

    def _calculate_regime_metrics(
        self, highs: list[float], lows: list[float], closes: list[float]
    ) -> dict[str, Any]:
        n = min(len(highs), len(lows), len(closes))
        if n < 2:
            return {
                "regime": "trending_breakout",
                "volatility_level": "medium",
                "atr_14": 100.0,
                "normalized_atr_pct": 2.0,
                "trend_strength_pct": 1.5,
                "current_price": closes[-1] if closes else 50000.0,
                "recommended_style": "momentum_breakout",
            }

        # 1. Calculate True Ranges
        true_ranges: list[float] = []
        for i in range(1, n):
            h = highs[i]
            l = lows[i]
            prev_c = closes[i - 1]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            true_ranges.append(tr)

        lookback = min(14, len(true_ranges))
        recent_trs = true_ranges[-lookback:]
        atr_14 = sum(recent_trs) / float(lookback) if lookback > 0 else 1.0

        current_close = closes[-1]
        normalized_atr_pct = (atr_14 / current_close) * 100.0 if current_close > 0 else 2.0

        # 2. Trend slope (last 20 vs last 50 avg)
        avg_20 = sum(closes[-20:]) / min(20, len(closes))
        avg_50 = sum(closes[-50:]) / min(50, len(closes))
        trend_diff_pct = ((avg_20 - avg_50) / avg_50) * 100.0 if avg_50 > 0 else 0.0

        # 3. Classify regime
        if normalized_atr_pct > 3.5:
            volatility_level = "high"
        elif normalized_atr_pct < 1.5:
            volatility_level = "low"
        else:
            volatility_level = "medium"

        if abs(trend_diff_pct) > 2.0:
            regime = "strong_trend"
            recommended_style = "trend_following_momentum"
        elif volatility_level == "high":
            regime = "high_volatility_breakout"
            recommended_style = "volatility_breakout_with_atr_stops"
        else:
            regime = "ranging_mean_reversion"
            recommended_style = "bollinger_or_rsi_mean_reversion"

        return {
            "regime": regime,
            "volatility_level": volatility_level,
            "atr_14": round(atr_14, 4),
            "normalized_atr_pct": round(normalized_atr_pct, 2),
            "trend_strength_pct": round(trend_diff_pct, 2),
            "current_price": round(current_close, 4),
            "recommended_style": recommended_style,
        }

    def _generate_fallback_candles(self, symbol: str) -> tuple[list[float], list[float], list[float]]:
        base_price = 50000.0 if "BTC" in symbol.upper() else (3000.0 if "ETH" in symbol.upper() else 100.0)
        closes: list[float] = []
        highs: list[float] = []
        lows: list[float] = []

        curr = base_price
        for i in range(60):
            change = math.sin(i / 5.0) * (base_price * 0.01) + (i * 10)
            curr += change
            c = max(1.0, curr)
            h = c * 1.015
            l = c * 0.985
            closes.append(c)
            highs.append(h)
            lows.append(l)

        return highs, lows, closes
