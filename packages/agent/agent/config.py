"""Agent configuration and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StopReason(Enum):
    """Reasons for agent loop termination."""
    TASK_DONE = "task_done"
    MAX_STEPS = "max_steps"
    TOKEN_BUDGET = "token_budget"
    IDLE = "idle"
    ERROR = "error"
    USER_INTERRUPT = "user_interrupt"


@dataclass
class RetryConfig:
    """Configuration for error recovery with retries."""
    max_retries: int = 3
    backoff_factor: float = 1.5
    base_delay: float = 1.0
    retryable_patterns: list[str] = field(default_factory=lambda: [
        "timeout",
        "rate_limit",
        "connection",
        "temporarily unavailable",
        "503",
        "502",
        "429",
    ])

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number (0-indexed)."""
        return self.base_delay * (self.backoff_factor ** attempt)

    def is_retryable(self, error_text: str) -> bool:
        """Check if error is retryable based on patterns."""
        error_lower = error_text.lower()
        return any(pattern in error_lower for pattern in self.retryable_patterns)


@dataclass
class ContextConfig:
    """Configuration for context management."""
    max_history_tokens: int = 80_000
    compression_threshold: float = 0.7  # Compress at 70% of max
    keep_recent_messages: int = 20      # Always keep last N messages
    chars_per_token: float = 4.0        # Rough estimate


@dataclass
class AgentConfig:
    """Configuration for AutonomousAgent behavior."""
    # Step limits
    max_steps: int = 50
    idle_threshold: int = 3  # Consecutive no-tool-call steps before stopping

    # Token budget (estimated)
    max_tokens: int = 100_000

    # Retry configuration
    retry: RetryConfig = field(default_factory=RetryConfig)

    # Context management
    context: ContextConfig = field(default_factory=ContextConfig)

    # Tool restrictions (None = all allowed)
    allowed_tools: list[str] | None = None


class TokenEstimator:
    """Estimates token usage for context management."""

    def __init__(self, chars_per_token: float = 4.0):
        self.chars_per_token = chars_per_token

    def estimate_message_tokens(self, message: dict[str, Any]) -> int:
        """Estimate tokens in a single message."""
        content = message.get("content", "")
        if isinstance(content, str):
            chars = len(content)
        else:
            chars = len(str(content))

        # Add overhead for role, structure
        overhead = 10
        return int(chars / self.chars_per_token) + overhead

    def estimate_history_tokens(self, history: list[dict[str, Any]]) -> int:
        """Estimate total tokens in message history."""
        total = 0
        for msg in history:
            total += self.estimate_message_tokens(msg)
        return total
