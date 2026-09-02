"""Tests for enhanced AutonomousAgent capabilities."""

from unittest.mock import MagicMock

from agent.config import (
    AgentConfig,
    RetryConfig,
    ContextConfig,
    TokenEstimator,
)
from agent.context_manager import ContextManager
from agent.skills import (
    SkillRegistry,
    SkillContext,
    BacktestSkill,
    AnalyzeSkill,
    create_default_registry,
)


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_get_delay_exponential_backoff(self):
        config = RetryConfig(base_delay=1.0, backoff_factor=2.0)
        assert config.get_delay(0) == 1.0
        assert config.get_delay(1) == 2.0
        assert config.get_delay(2) == 4.0

    def test_is_retryable_matches_patterns(self):
        config = RetryConfig()
        assert config.is_retryable("Connection timeout occurred")
        assert config.is_retryable("Rate limit exceeded (429)")
        assert config.is_retryable("503 Service Unavailable")
        assert not config.is_retryable("File not found")
        assert not config.is_retryable("Syntax error in code")


class TestTokenEstimator:
    """Tests for TokenEstimator."""

    def test_estimate_message_tokens(self):
        estimator = TokenEstimator(chars_per_token=4.0)
        msg = {"role": "user", "content": "Hello world"}  # 11 chars
        tokens = estimator.estimate_message_tokens(msg)
        # 11 / 4 + 10 overhead = ~13
        assert 10 <= tokens <= 20

    def test_estimate_history_tokens(self):
        estimator = TokenEstimator(chars_per_token=4.0)
        history = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = estimator.estimate_history_tokens(history)
        assert tokens > 30  # Should have reasonable token count


class TestContextManager:
    """Tests for ContextManager."""

    def test_no_compression_under_threshold(self):
        config = ContextConfig(max_history_tokens=10000, compression_threshold=0.7)
        manager = ContextManager(config)

        history = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Task: do something"},
            {"role": "assistant", "content": "OK"},
        ]

        result = manager.compress_if_needed(history)
        assert result == history

    def test_compression_when_over_threshold(self):
        config = ContextConfig(
            max_history_tokens=100,  # Very low to trigger compression
            compression_threshold=0.5,
            keep_recent_messages=2,
        )
        manager = ContextManager(config)

        # Create a long history
        history = [{"role": "system", "content": "System prompt"}]
        history.append({"role": "user", "content": "Task"})
        for i in range(20):
            history.append({"role": "assistant", "content": f"Response {i}" * 50})
            history.append({"role": "user", "content": f"Follow up {i}"})

        result = manager.compress_if_needed(history)

        # Should be compressed
        assert len(result) < len(history)
        # Should keep system prompt
        assert result[0]["role"] == "system"
        # Should have summary message
        assert any("summary" in msg.get("content", "").lower() for msg in result)

    def test_get_context_stats(self):
        manager = ContextManager()
        history = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
        ]
        stats = manager.get_context_stats(history)

        assert "message_count" in stats
        assert stats["message_count"] == 2
        assert "estimated_tokens" in stats
        assert "usage_percent" in stats


class TestSkillRegistry:
    """Tests for SkillRegistry."""

    def test_register_and_get_skill(self):
        registry = SkillRegistry()
        skill = BacktestSkill()
        registry.register(skill)

        assert registry.get("backtest") is skill
        assert registry.get("/backtest") is skill  # With leading slash
        assert registry.get("unknown") is None

    def test_list_skills(self):
        registry = create_default_registry()
        skills = registry.list_skills()

        assert len(skills) == 2  # backtest, analyze
        names = [s["name"] for s in skills]
        assert "backtest" in names
        assert "analyze" in names

    def test_parse_skill_invocation(self):
        registry = SkillRegistry()

        result = registry.parse_skill_invocation("/backtest --interval 1h")
        assert result == ("backtest", "--interval 1h")

        result = registry.parse_skill_invocation("/search pattern")
        assert result == ("search", "pattern")

        result = registry.parse_skill_invocation("not a skill")
        assert result is None


class TestSkills:
    """Tests for individual skills."""

    def test_backtest_skill_parse_args(self):
        skill = BacktestSkill()
        args = skill.parse_args("--interval 4h --data path/to/data.csv")

        assert args["interval"] == "4h"
        assert args["data"] == "path/to/data.csv"

    def test_analyze_skill_detects_missing_imports(self):
        skill = AnalyzeSkill()

        # Create mock tools
        mock_tools = MagicMock()
        mock_tools.read_file.return_value = MagicMock(
            output="def generate_signals(data, params):\n    return pd.DataFrame()",
            error=None
        )

        context = SkillContext(
            tools=mock_tools,
            workspace_root="/tmp",
        )

        result = skill.execute("", context)
        assert "import pandas" in result.output.lower() or "pd" in result.output

class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_default_config(self):
        config = AgentConfig()
        assert config.max_steps == 50
        assert config.max_tokens == 100_000
        assert config.idle_threshold == 3

    def test_custom_config(self):
        config = AgentConfig(
            max_steps=100,
            max_tokens=50_000,
            allowed_tools=["read_file", "ls"],
        )
        assert config.max_steps == 100
        assert config.max_tokens == 50_000
        assert config.allowed_tools == ["read_file", "ls"]


