"""Build strategy extraction prompt from transcribed text."""

import logging

logger = logging.getLogger(__name__)


def build_strategy_prompt(
    transcript: str,
    video_title: str = "",
    video_description: str = "",
    uploader: str = "",
) -> str:
    """Build a detailed prompt for LLM to extract trading strategy from transcript.

    Args:
        transcript: Transcribed text from YouTube video
        video_title: Video title (optional)
        video_description: Video description (optional)
        uploader: Channel name (optional)

    Returns:
        Detailed prompt for strategy extraction and conversion to Python
    """
    # Truncate transcript if too long (keep first 8000 chars to fit in context)
    max_transcript_length = 8000
    if len(transcript) > max_transcript_length:
        transcript = transcript[:max_transcript_length] + "\n\n[Transcript truncated for length...]"
        logger.warning(f"Transcript truncated from {len(transcript)} to {max_transcript_length} characters")

    prompt = f"""Extract and convert a trading strategy from the following YouTube video transcript to Python code for backtesting.

**Video Information:**
- Title: {video_title or "Unknown"}
- Channel: {uploader or "Unknown"}
- Description: {video_description[:200] if video_description else "N/A"}

**Video Transcript:**
```
{transcript}
```

**Your Task:**

1. **Analyze the Transcript:**
   - Identify the core trading strategy being explained
   - Extract entry and exit rules
   - Note any indicators mentioned (MA, EMA, RSI, MACD, Bollinger Bands, etc.)
   - Identify timeframes and symbols discussed
   - Extract risk management rules (stop loss, take profit, position sizing)

2. **Strategy Extraction Guidelines:**
   - If multiple strategies are mentioned, focus on the PRIMARY strategy
   - Ignore promotional content, channel subscriptions, disclaimers
   - Extract concrete, actionable trading rules
   - Note any specific parameter values mentioned (e.g., "20-day moving average")

3. **Convert to Python:**
   - Implement as vectorized pandas/numpy operations
   - Use available indicators from backtest.indicators module:
     - sma(x, window), ema(x, window), rsi(close, window=14)
     - cross_over(a, b), cross_under(a, b), zscore(x, window)
   - Define generate_signals(data: pd.DataFrame, params: dict) -> dict
   - Return {{entries: bool_array, exits: bool_array}}

4. **Best Practices:**
   - Use params.get(key, default) for all parameters
   - Handle edge cases (NaN values, insufficient data)
   - Add clear comments explaining the strategy logic
   - Map video concepts to code accurately
   - Ensure deterministic and reproducible results

5. **Handle Ambiguity:**
   - If strategy details are unclear, make REASONABLE assumptions
   - Document assumptions in code comments
   - Prefer simpler implementations when multiple interpretations exist
   - If no clear strategy is found, implement a basic trend-following strategy and note this in comments

**Output Format:**
Generate a complete Python strategy file with:
- Necessary imports
- generate_signals() function with vectorized logic
- Optional: LiveStrategy class for live trading hooks
- Clear comments mapping video concepts to code

**Important Notes:**
- Focus on the TRADING STRATEGY, not the presenter's opinions or market analysis
- If the video discusses general market conditions without a specific strategy, extract the IMPLIED trading approach
- Preserve the spirit of the strategy even if exact parameters aren't mentioned

Begin your analysis and code generation:
"""

    return prompt.strip()


def extract_strategy_summary(transcript: str, max_length: int = 500) -> str:
    """Extract a brief summary of the strategy from transcript.

    Args:
        transcript: Full transcript text
        max_length: Maximum summary length in characters

    Returns:
        Brief summary of the strategy (for display purposes)
    """
    # Simple heuristic: take first few sentences that mention trading-related keywords
    trading_keywords = [
        'strategy', 'trade', 'indicator', 'signal', 'buy', 'sell',
        'entry', 'exit', 'stop loss', 'take profit', 'moving average',
        'rsi', 'macd', 'bollinger', 'trend', 'breakout', 'support', 'resistance'
    ]

    lines = transcript.split('.')
    summary_lines = []
    current_length = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if line contains trading keywords
        if any(keyword in line.lower() for keyword in trading_keywords):
            if current_length + len(line) <= max_length:
                summary_lines.append(line)
                current_length += len(line)
            else:
                break

        # Stop if we have enough content
        if len(summary_lines) >= 3 and current_length >= max_length // 2:
            break

    summary = '. '.join(summary_lines)
    if summary:
        summary += '.'

    return summary if summary else transcript[:max_length]
