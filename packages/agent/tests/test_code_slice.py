"""Unit tests for code_slice module."""

import pytest

from agent.prompt.code_slice import (
    estimate_tokens,
    extract_function_signatures,
    extract_function_body,
    find_anchor_position,
    should_slice_function,
    extract_logic_blocks,
    find_block_with_anchor,
    prepare_code_summary,
    extract_relevant_context,
)


# Sample code for testing
SAMPLE_CODE = '''"""
Strategy module for backtesting.
"""

import pandas as pd
import numpy as np
from backtest.indicators import sma, ema, rsi


def calculate_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Calculate RSI indicator.

    Args:
        close: Close price series.
        window: RSI period.

    Returns:
        RSI values.
    """
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Generate trading signals.

    Args:
        data: OHLCV data.
        params: Strategy parameters.

    Returns:
        Dict with entries, exits, and reasons.
    """
    # Extract parameters
    fast = params.get("fast", 10)
    slow = params.get("slow", 20)

    # Calculate indicators
    fast_ma = sma(data["close"], window=fast)
    slow_ma = sma(data["close"], window=slow)
    rsi_val = rsi(data["close"], window=14)

    # Initialize signals
    entries = pd.Series(False, index=data.index)
    exits = pd.Series(False, index=data.index)
    entry_reason = [""] * len(data)
    exit_reason = [""] * len(data)

    # Entry logic: MA crossover
    cross_over = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    entries[cross_over] = True
    for i in data.index[cross_over]:
        entry_reason[i] = f"MA crossover at {data.loc[i, 'close']}"

    # Exit logic
    cross_under = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
    exits[cross_under] = True
    for i in data.index[cross_under]:
        exit_reason[i] = f"MA crossunder at {data.loc[i, 'close']}"

    return {
        "entries": entries,
        "exits": exits,
        "entry_reason": entry_reason,
        "exit_reason": exit_reason,
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
        "rsi": rsi_val,
    }
'''

LONG_FUNCTION_CODE = '''
def process_data(data: pd.DataFrame, params: dict) -> dict:
    """A very long function that should be split."""
    # Step 1: Data cleaning
    cleaned = data.dropna()
    cleaned = cleaned[cleaned["volume"] > 0]

    # Step 2: Calculate indicators
    sma_20 = cleaned["close"].rolling(20).mean()
    sma_50 = cleaned["close"].rolling(50).mean()
    rsi_14 = rsi(cleaned["close"], 14)

    # Step 3: Generate signals
    signals = pd.DataFrame(index=cleaned.index)
    signals["trend"] = "neutral"

    # Uptrend
    signals.loc[sma_20 > sma_50, "trend"] = "up"

    # Downtrend
    signals.loc[sma_20 < sma_50, "trend"] = "down"

    # Step 4: Filter entries
    entries = (signals["trend"] == "up") & (rsi_14 < 70)

    # Step 5: Calculate exits
    exits = (signals["trend"] == "down") | (rsi_14 > 70)

    # Step 6: Build result
    return {
        "entries": entries,
        "exits": exits,
        "signals": signals,
        "indicators": {
            "sma_20": sma_20,
            "sma_50": sma_50,
            "rsi_14": rsi_14,
        }
    }
'''


class TestEstimateTokens:
    """Tests for estimate_tokens function."""

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_string(self):
        # ~30 chars ≈ 8-10 tokens
        tokens = estimate_tokens("def foo(): return 42")
        assert 5 <= tokens <= 15

    def test_longer_string(self):
        # ~300 chars ≈ 75-100 tokens
        text = "def foo() -> int:\n    return 42\n" * 10
        tokens = estimate_tokens(text)
        assert tokens > 50


class TestExtractFunctionSignatures:
    """Tests for extract_function_signatures function."""

    def test_extract_from_sample_code(self):
        sigs = extract_function_signatures(SAMPLE_CODE)
        assert len(sigs) >= 2

        names = {s["name"] for s in sigs}
        assert "calculate_rsi" in names
        assert "generate_signals" in names

    def test_signature_includes_line_numbers(self):
        sigs = extract_function_signatures(SAMPLE_CODE)
        generate_sig = next(s for s in sigs if s["name"] == "generate_signals")

        assert "line_start" in generate_sig
        assert "line_end" in generate_sig
        assert "length_lines" in generate_sig
        assert generate_sig["length_lines"] > 0

    def test_signature_includes_token_estimate(self):
        sigs = extract_function_signatures(SAMPLE_CODE)
        generate_sig = next(s for s in sigs if s["name"] == "generate_signals")

        assert "estimated_tokens" in generate_sig
        assert generate_sig["estimated_tokens"] > 0

    def test_empty_code(self):
        assert extract_function_signatures("") == []

    def test_invalid_code(self):
        sigs = extract_function_signatures("this is not valid python")
        # Should not crash, return empty
        assert sigs == []


class TestExtractFunctionBody:
    """Tests for extract_function_body function."""

    def test_extract_existing_function(self):
        body = extract_function_body(SAMPLE_CODE, "calculate_rsi")
        assert body is not None
        assert "def calculate_rsi" in body
        assert "return 100 - (100 / (1 + rs))" in body

    def test_extract_nonexistent_function(self):
        body = extract_function_body(SAMPLE_CODE, "nonexistent")
        assert body is None

    def test_extract_generate_signals(self):
        body = extract_function_body(SAMPLE_CODE, "generate_signals")
        assert body is not None
        assert "fast_ma = sma" in body
        assert "return {" in body


class TestFindAnchorPosition:
    """Tests for find_anchor_position function."""

    def test_find_exact_match(self):
        result = find_anchor_position(
            SAMPLE_CODE,
            "fast_ma = sma(data['close'], window=fast)"
        )
        assert result is not None
        assert result["found"] is True
        assert "line_number" in result

    def test_find_partial_match(self):
        result = find_anchor_position(
            SAMPLE_CODE,
            "fast_ma = sma"
        )
        assert result is not None
        assert result["found"] is True

    def test_anchor_not_found(self):
        result = find_anchor_position(
            SAMPLE_CODE,
            "nonexistent_line"
        )
        assert result is None

    def test_includes_context(self):
        result = find_anchor_position(
            SAMPLE_CODE,
            "fast_ma = sma(data['close'], window=fast)"
        )
        if result:
            assert "context" in result
            # Context should have more lines than just the anchor
            context_lines = result["context"].strip().split("\n")
            assert len(context_lines) > 1


class TestShouldSliceFunction:
    """Tests for should_slice_function function."""

    def test_short_function_no_slice(self):
        assert should_slice_function("def foo(): return 42", max_tokens=8000) is False

    def test_long_function_should_slice(self):
        # Create a very long function
        long_code = "def f():\n" + "    x = 1\n" * 3000  # ~12000 lines
        assert should_slice_function(long_code, max_tokens=8000) is True


class TestExtractLogicBlocks:
    """Tests for extract_logic_blocks function."""

    def test_extract_blocks_from_long_function(self):
        blocks = extract_logic_blocks(LONG_FUNCTION_CODE)
        assert len(blocks) > 0

    def test_block_types(self):
        blocks = extract_logic_blocks(LONG_FUNCTION_CODE)
        block_types = {b["type"] for b in blocks}
        # Should have various block types
        assert any(bt in block_types for bt in ["assignment", "if_block", "return"])

    def test_blocks_have_line_numbers(self):
        blocks = extract_logic_blocks(LONG_FUNCTION_CODE)
        for block in blocks:
            assert "line_start" in block
            assert "content" in block


class TestFindBlockWithAnchor:
    """Tests for find_block_with_anchor function."""

    def test_find_block_with_anchor(self):
        blocks = extract_logic_blocks(SAMPLE_CODE)
        result = find_block_with_anchor(blocks, "fast_ma = sma")
        # Should find a block containing this line
        assert result is not None

    def test_find_nonexistent_anchor(self):
        blocks = extract_logic_blocks(SAMPLE_CODE)
        result = find_block_with_anchor(blocks, "nonexistent_xyz")
        assert result is None


class TestPrepareCodeSummary:
    """Tests for prepare_code_summary function."""

    def test_summary_includes_imports(self):
        summary = prepare_code_summary(SAMPLE_CODE)
        assert "import" in summary
        assert "pandas" in summary

    def test_summary_includes_functions(self):
        summary = prepare_code_summary(SAMPLE_CODE)
        assert "Functions:" in summary or "functions:" in summary.lower()
        assert "calculate_rsi" in summary
        assert "generate_signals" in summary

    def test_summary_empty_code(self):
        summary = prepare_code_summary("")
        assert "Empty" in summary

    def test_summary_respects_token_limit(self):
        # Generate a large summary and check it's truncated
        large_code = SAMPLE_CODE * 10
        summary = prepare_code_summary(large_code, max_tokens=500)
        tokens = estimate_tokens(summary)
        # Should be under limit (roughly)
        assert tokens < 1000  # Allow some margin


class TestExtractRelevantContext:
    """Tests for extract_relevant_context main entry point."""

    def test_extract_by_function_name(self):
        result = extract_relevant_context(
            SAMPLE_CODE,
            target_name="calculate_rsi"
        )
        assert result["type"] == "function"
        assert result["name"] == "calculate_rsi"
        assert "def calculate_rsi" in result["code"]

    def test_extract_by_anchor(self):
        result = extract_relevant_context(
            SAMPLE_CODE,
            anchor="fast_ma = sma"
        )
        assert result["type"] == "context"
        assert "fast_ma" in result["code"]

    def test_extract_summary_fallback(self):
        result = extract_relevant_context(
            SAMPLE_CODE
        )
        assert result["type"] in ["summary", "full"]
        assert result["code"]

    def test_empty_code(self):
        result = extract_relevant_context("")
        assert result["type"] == "empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
