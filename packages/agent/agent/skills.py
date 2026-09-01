"""Skills system for reusable domain-specific workflows.

Skills are like Claude Code's slash commands - predefined workflows that
can be invoked by name (e.g., /backtest, /optimize, /analyze).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.tools import FileSystemTools

from agent.protocol import STRATEGY_FILE, STRATEGY_FUNCTION


@dataclass
class SkillResult:
    """Result from skill execution."""
    success: bool
    output: str
    metadata: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class SkillContext:
    """Context provided to skills during execution."""
    tools: "FileSystemTools"
    workspace_root: str
    history: list[dict[str, Any]] = field(default_factory=list)


class Skill(ABC):
    """Base class for all skills.

    Skills are reusable workflows that can be:
    1. Invoked via slash commands (e.g., /backtest)
    2. Auto-loaded as LLM tools based on their description

    Each skill defines:
    - name: Unique identifier
    - description: What the skill does (used by LLM for auto-selection)
    - usage: Human-readable usage pattern
    - parameters: JSON Schema for tool generation (optional)
    """

    name: str
    description: str
    usage: str = ""

    def get_tool_definition(self) -> dict[str, Any]:
        """Generate OpenAI-compatible tool definition for this skill.

        This allows LLM to see each skill as a separate tool and
        automatically choose based on the description.
        """
        return {
            "type": "function",
            "function": {
                "name": f"skill_{self.name}",
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            }
        }

    def get_parameters_schema(self) -> dict[str, Any]:
        """Return JSON Schema for skill parameters.

        Override in subclasses for typed parameters.
        Default: single 'args' string parameter.
        """
        return {
            "type": "object",
            "properties": {
                "args": {
                    "type": "string",
                    "description": f"Arguments for the skill. Usage: {self.usage}",
                }
            },
        }

    @abstractmethod
    def execute(self, args: str, context: SkillContext) -> SkillResult:
        """Execute the skill with given arguments."""
        pass

    def execute_from_tool_args(self, tool_args: dict[str, Any], context: SkillContext) -> SkillResult:
        """Execute skill from parsed tool arguments.

        Override for skills with typed parameters.
        Default: extract 'args' string and call execute().
        """
        args_str = tool_args.get("args", "")
        return self.execute(args_str, context)

    def parse_args(self, args: str) -> dict[str, str]:
        """Parse CLI-style arguments into a dictionary."""
        result: dict[str, str] = {}
        # Match --key=value or --key value patterns
        pattern = r'--(\w+)(?:=|\s+)([^\s-][^\s]*)?'
        matches = re.findall(pattern, args)
        for key, value in matches:
            result[key] = value if value else "true"

        # Also capture positional arguments (words not starting with --)
        positional = re.findall(r'(?:^|\s)([^-\s][^\s]*)', args)
        if positional:
            result["_positional"] = positional

        return result


class BacktestSkill(Skill):
    """Run backtest with specified parameters."""

    name = "backtest"
    description = "Run a backtest on the current trading strategy to evaluate performance metrics like Sharpe ratio, max drawdown, and total return"
    usage = "/backtest [--interval 1h] [--data path/to/data.csv]"

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "interval": {
                    "type": "string",
                    "description": "Bar interval for backtest (e.g., '1h', '4h', '1d')",
                    "default": "1h",
                },
                "data_path": {
                    "type": "string",
                    "description": "Optional path to custom CSV data file",
                },
            },
        }

    def execute_from_tool_args(self, tool_args: dict[str, Any], context: SkillContext) -> SkillResult:
        interval = tool_args.get("interval", "1h")
        data_path = tool_args.get("data_path")

        result = context.tools.run_backtest(interval=interval, data_path=data_path)

        if result.error:
            return SkillResult(success=False, output="", error=result.error)

        return SkillResult(success=True, output=result.output, metadata=result.metadata)

    def execute(self, args: str, context: SkillContext) -> SkillResult:
        params = self.parse_args(args)

        interval = params.get("interval", "1h")
        data_path = params.get("data")

        result = context.tools.run_backtest(
            interval=interval,
            data_path=data_path
        )

        if result.error:
            return SkillResult(
                success=False,
                output="",
                error=result.error
            )

        return SkillResult(
            success=True,
            output=result.output,
            metadata=result.metadata
        )


class AnalyzeSkill(Skill):
    """Analyze strategy code for potential issues."""

    name = "analyze"
    description = f"Analyze {STRATEGY_FILE} for common issues like missing imports, required functions, and suggest improvements for trading strategy code"
    usage = "/analyze [--verbose]"

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "verbose": {
                    "type": "boolean",
                    "description": "Show code preview in output",
                    "default": False,
                },
            },
        }

    def execute_from_tool_args(self, tool_args: dict[str, Any], context: SkillContext) -> SkillResult:
        verbose = tool_args.get("verbose", False)
        args_str = "--verbose" if verbose else ""
        return self.execute(args_str, context)

    def execute(self, args: str, context: SkillContext) -> SkillResult:
        params = self.parse_args(args)
        verbose = params.get("verbose", "false").lower() == "true"

        # Read strategy file using protocol constant
        result = context.tools.read_file(STRATEGY_FILE)
        if result.error:
            return SkillResult(
                success=False,
                output="",
                error=f"Cannot read {STRATEGY_FILE}: {result.error}"
            )

        code = result.output
        issues: list[str] = []
        suggestions: list[str] = []

        # Check for common issues
        if "import pandas" not in code and "pd." in code:
            issues.append("Missing 'import pandas as pd'")

        if "import numpy" not in code and "np." in code:
            issues.append("Missing 'import numpy as np'")

        if STRATEGY_FUNCTION not in code:
            issues.append(f"Missing required function '{STRATEGY_FUNCTION}'")

        if "target_weights" not in code:
            issues.append("Missing required output 'target_weights'")

        if "weight_reason" not in code:
            issues.append("Missing required output 'weight_reason'")

        # Check for risky patterns
        if ".iloc[-1]" in code:
            suggestions.append("Using .iloc[-1] may cause look-ahead bias in vectorized strategies")

        if "for " in code and "in range" in code:
            suggestions.append("Consider vectorizing loops for better performance")

        if "fillna(0)" in code:
            suggestions.append("fillna(0) may hide NaN issues - consider explicit handling")

        # Build output
        output_lines = ["## Strategy Analysis\n"]

        if issues:
            output_lines.append("### Issues Found:")
            for issue in issues:
                output_lines.append(f"  - ❌ {issue}")
            output_lines.append("")

        if suggestions:
            output_lines.append("### Suggestions:")
            for suggestion in suggestions:
                output_lines.append(f"  - 💡 {suggestion}")
            output_lines.append("")

        if not issues and not suggestions:
            output_lines.append("✅ No obvious issues found.")

        if verbose:
            output_lines.append("\n### Code Preview (first 50 lines):")
            lines = code.split("\n")[:50]
            for i, line in enumerate(lines, 1):
                output_lines.append(f"{i:3d} | {line}")

        return SkillResult(
            success=len(issues) == 0,
            output="\n".join(output_lines),
            metadata={"issues": len(issues), "suggestions": len(suggestions)}
        )




class SkillRegistry:
    """Registry for managing available skills.

    Skills are automatically exposed as LLM tools based on their descriptions,
    allowing the LLM to choose which skill to invoke based on context.
    """

    def __init__(self):
        self.skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill."""
        self.skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        # Handle /name, skill_name, or name
        clean_name = name.lstrip("/")
        if clean_name.startswith("skill_"):
            clean_name = clean_name[6:]  # Remove 'skill_' prefix
        return self.skills.get(clean_name)

    def list_skills(self) -> list[dict[str, str]]:
        """List all registered skills."""
        return [
            {"name": s.name, "description": s.description, "usage": s.usage}
            for s in self.skills.values()
        ]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Generate OpenAI-compatible tool definitions for all skills.

        Each skill becomes an independent tool that LLM can discover
        and invoke based on its description.
        """
        return [skill.get_tool_definition() for skill in self.skills.values()]

    def execute_skill_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        """Execute a skill from tool call.

        Args:
            tool_name: Tool name (e.g., 'skill_backtest')
            tool_args: Parsed tool arguments
            context: Skill execution context

        Returns:
            SkillResult from skill execution
        """
        skill = self.get(tool_name)
        if not skill:
            return SkillResult(
                success=False,
                output="",
                error=f"Unknown skill: {tool_name}"
            )
        return skill.execute_from_tool_args(tool_args, context)

    def parse_skill_invocation(self, text: str) -> tuple[str, str] | None:
        """Parse a skill invocation from text.

        Returns (skill_name, args) if found, None otherwise.
        """
        # Match /command at start of text or after newline
        match = re.match(r'^/(\w+)\s*(.*)?$', text.strip(), re.DOTALL)
        if match:
            return match.group(1), match.group(2) or ""
        return None


def create_default_registry() -> SkillRegistry:
    """Create a registry with default skills."""
    registry = SkillRegistry()

    # BacktestSkill disabled: causes edit→backtest loop.
    # Agent should read backtest results from workspace files instead.
    # registry.register(BacktestSkill())

    registry.register(AnalyzeSkill())

    return registry


# Default global registry
DEFAULT_SKILLS = create_default_registry()
