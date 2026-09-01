"""Agent package - Enhanced Autonomous Coding Agent.

This package provides an autonomous coding agent with:
- Skills (slash commands) for reusable workflows
- Context management with automatic compression
- Error recovery with retries
- Dynamic step limits
"""

from agent.autonomous import AutonomousAgent, AgentResult
from agent.config import (
    AgentConfig,
    RetryConfig,
    ContextConfig,
    StopReason,
)
from agent.skills import (
    Skill,
    SkillResult,
    SkillContext,
    SkillRegistry,
    DEFAULT_SKILLS,
    create_default_registry,
)
from agent.context_manager import ContextManager
from agent.protocol import (
    StrategyProtocol,
    PROTOCOL,
    STRATEGY_FILE,
    STRATEGY_FUNCTION,
    OVERVIEW_FILE,
    SPEC_FILE,
)

__all__ = [
    # Core
    "AutonomousAgent",
    "AgentResult",
    # Config
    "AgentConfig",
    "RetryConfig",
    "ContextConfig",
    "StopReason",
    # Skills
    "Skill",
    "SkillResult",
    "SkillContext",
    "SkillRegistry",
    "DEFAULT_SKILLS",
    "create_default_registry",
    # Context
    "ContextManager",
    # Protocol
    "StrategyProtocol",
    "PROTOCOL",
    "STRATEGY_FILE",
    "STRATEGY_FUNCTION",
    "OVERVIEW_FILE",
    "SPEC_FILE",
]
