"""Symbol and market detection utilities for TradingView strategies."""

import re
from typing import List

# Main crypto trading pairs (Binance USDT pairs)
CRYPTO_SYMBOLS = {
    # Top coins by market cap
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "UNIUSDT",
    # Additional popular pairs
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "ALGOUSDT", "VETUSDT",
    "FILUSDT", "ICPUSDT", "AAVEUSDT", "MKRUSDT", "COMPUSDT",
    # Binance USD pairs
    "BTCUSD", "ETHUSD",
}


def detect_symbols(text: str) -> List[str]:
    """
    Detect crypto trading symbols from text.

    Args:
        text: Input text to search for symbols

    Returns:
        List of detected symbols (e.g., ["BTCUSDT", "ETHUSDT"])
    """
    detected = []
    text_upper = text.upper()

    for symbol in CRYPTO_SYMBOLS:
        # Use word boundary to match whole symbols only
        # This prevents "BTCUSD" from matching within "BTCUSDT"
        pattern = r'\b' + re.escape(symbol) + r'\b'
        if re.search(pattern, text_upper):
            detected.append(symbol)

    # Remove duplicates while preserving order
    seen = set()
    unique_detected = []
    for symbol in detected:
        if symbol not in seen:
            seen.add(symbol)
            unique_detected.append(symbol)

    return unique_detected


def detect_markets(symbols: List[str]) -> List[str]:
    """
    Detect market types based on trading symbols.

    Args:
        symbols: List of trading symbols

    Returns:
        List of detected markets (e.g., ["crypto"])
    """
    markets = set()

    for symbol in symbols:
        if symbol.endswith("USDT") or symbol.endswith("USD"):
            markets.add("crypto")

    return list(markets)
