"""Context management for agent conversation history.

Handles compression and summarization of conversation history to stay
within token limits while preserving important context.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from agent.config import ContextConfig, TokenEstimator

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    """Result of history compression."""
    compressed_history: list[dict[str, Any]]
    original_tokens: int
    compressed_tokens: int
    messages_removed: int


class ContextManager:
    """Manages conversation history and context compression."""

    def __init__(self, config: ContextConfig | None = None):
        self.config = config or ContextConfig()
        self.estimator = TokenEstimator(self.config.chars_per_token)

    def compress_if_needed(
        self,
        history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Compress history if it exceeds threshold.

        Compression strategy:
        1. Always keep system prompt (first message)
        2. Always keep recent messages (last N)
        3. Summarize middle portion into a condensed format
        """
        estimated_tokens = self.estimator.estimate_history_tokens(history)
        threshold = int(self.config.max_history_tokens * self.config.compression_threshold)

        if estimated_tokens < threshold:
            return history

        logger.info(
            "[context] compressing history: %d tokens > %d threshold",
            estimated_tokens,
            threshold
        )

        result = self._compress(history)

        logger.info(
            "[context] compressed: %d -> %d tokens, removed %d messages",
            result.original_tokens,
            result.compressed_tokens,
            result.messages_removed
        )

        return result.compressed_history

    def _compress(self, history: list[dict[str, Any]]) -> CompressionResult:
        """Perform history compression."""
        if len(history) <= self.config.keep_recent_messages + 2:
            # Not enough to compress
            return CompressionResult(
                compressed_history=history,
                original_tokens=self.estimator.estimate_history_tokens(history),
                compressed_tokens=self.estimator.estimate_history_tokens(history),
                messages_removed=0
            )

        original_tokens = self.estimator.estimate_history_tokens(history)

        # Split history
        system_msg = history[0] if history[0].get("role") == "system" else None
        user_task = history[1] if len(history) > 1 and history[1].get("role") == "user" else None

        # Determine split points
        start_idx = 2 if user_task else 1
        end_idx = len(history) - self.config.keep_recent_messages

        if end_idx <= start_idx:
            # Nothing to compress
            return CompressionResult(
                compressed_history=history,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                messages_removed=0
            )

        middle = history[start_idx:end_idx]
        recent = history[end_idx:]

        # Create summary of middle portion
        summary = self._summarize_messages(middle)

        # Build compressed history
        compressed: list[dict[str, Any]] = []

        if system_msg:
            compressed.append(system_msg)
        if user_task:
            compressed.append(user_task)

        # Add summary as system message
        compressed.append({
            "role": "system",
            "content": f"[Previous conversation summary - {len(middle)} messages compressed]\n\n{summary}"
        })

        # Add recent messages
        compressed.extend(recent)

        compressed_tokens = self.estimator.estimate_history_tokens(compressed)

        return CompressionResult(
            compressed_history=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            messages_removed=len(middle)
        )

    def _summarize_messages(self, messages: list[dict[str, Any]]) -> str:
        """Create a summary of messages.

        This is a simple rule-based summarization. For better results,
        this could use an LLM to generate summaries.
        """
        tool_calls: list[str] = []
        key_actions: list[str] = []
        files_read: set[str] = set()
        files_modified: set[str] = set()

        for msg in messages:
            role = msg.get("role", "")

            if role == "assistant":
                # Extract tool calls from assistant messages
                calls = msg.get("tool_calls", [])
                for call in calls:
                    func = call.get("function", {})
                    name = func.get("name", "unknown")
                    args_str = func.get("arguments", "{}")

                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}

                    # Track file operations
                    if name == "read_file":
                        files_read.add(args.get("path", "unknown"))
                    elif name in ("edit_file", "write_file"):
                        files_modified.add(args.get("path", "unknown"))
                    elif name == "run_backtest":
                        key_actions.append("Ran backtest")
                    elif name == "run_command":
                        cmd = args.get("command", "")[:50]
                        key_actions.append(f"Executed: {cmd}")

                    tool_calls.append(name)

            elif role == "tool":
                # Could extract key results here if needed
                pass

        # Build summary
        lines = []

        if files_read:
            lines.append(f"**Files Read:** {', '.join(sorted(files_read)[:10])}")

        if files_modified:
            lines.append(f"**Files Modified:** {', '.join(sorted(files_modified))}")

        if key_actions:
            lines.append("**Key Actions:**")
            for action in key_actions[:5]:
                lines.append(f"  - {action}")

        # Tool usage stats
        if tool_calls:
            from collections import Counter
            counts = Counter(tool_calls)
            stats = ", ".join(f"{name}({count})" for name, count in counts.most_common(5))
            lines.append(f"**Tool Usage:** {stats}")

        lines.append(f"**Total Operations:** {len(tool_calls)} tool calls")

        return "\n".join(lines) if lines else "No significant actions recorded."

    def estimate_tokens(self, history: list[dict[str, Any]]) -> int:
        """Estimate total tokens in history."""
        return self.estimator.estimate_history_tokens(history)

    def get_context_stats(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        """Get statistics about current context."""
        tokens = self.estimate_tokens(history)
        return {
            "message_count": len(history),
            "estimated_tokens": tokens,
            "max_tokens": self.config.max_history_tokens,
            "usage_percent": round(tokens / self.config.max_history_tokens * 100, 1),
            "compression_threshold_percent": round(self.config.compression_threshold * 100, 1),
        }
