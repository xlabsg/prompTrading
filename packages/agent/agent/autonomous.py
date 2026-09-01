"""Enhanced Autonomous Agent with Sub-Agent, Skills, Context Management, and Error Recovery.

This module implements a ReAct (Reasoning + Acting) agent loop with:
- Dynamic step limits and token budgets
- Error recovery with retries
- Context compression for long conversations
- Sub-agent delegation for specialized tasks
- Skills (slash commands) for reusable workflows
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from agent.config import (
    AgentConfig,
    StopReason,
)
from agent.context_manager import ContextManager
from agent.llm_openai_compat import ChatCompletionRequest, chat_completion
from agent.protocol import STRATEGY_FILE, OVERVIEW_FILE, PROTOCOL
from agent.skills import SkillContext, SkillRegistry, DEFAULT_SKILLS
from agent.tools import FileSystemTools

logger = logging.getLogger(__name__)

# System Prompt with Sub-Agent and Skills awareness
SYSTEM_PROMPT = """You are an elite Autonomous Coding Agent, designed to modify and improve codebases with precision.
Your goal is to complete the user's request by navigating the file system, understanding the code, and applying robust edits.

**Core Tools:**
1. **Explore**: Use `ls` and `read_file` to understand the codebase structure and content.
2. **Search**: Use `search_files` to find specific code patterns.
3. **Edit**: Use `edit_file` to modify code. The editor is "fuzzy" - it can match code even with slight whitespace differences.
4. **Create**: Use `write_file` to create new files.

**Guidelines:**
- **Read before Edit**: Always read the file content before attempting an edit.
- **Unique Context**: Provide enough surrounding lines in `old_text` or `anchor` to ensure unique matches.
- **Incremental Steps**: Break complex tasks down. Read -> Plan -> Edit one file -> Verify.
- **Task Done**: When you have completed the task, use the `task_done` tool to submit your work.
"""


@dataclass
class AgentResult:
    """Result from agent execution."""
    success: bool
    summary: str
    history: list[Any]
    stop_reason: StopReason = StopReason.TASK_DONE
    steps_taken: int = 0
    metadata: dict[str, Any] | None = None


class AutonomousAgent:
    """Enhanced autonomous coding agent with advanced capabilities."""

    def __init__(
        self,
        workspace_root: str,
        llm_config: Any,
        config: AgentConfig | None = None,
        skill_registry: SkillRegistry | None = None,
        system_prompt: str | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.workspace_root = workspace_root
        self.tools = FileSystemTools(workspace_root)
        self.llm_config = llm_config
        self.config = config or AgentConfig()
        self.skills = skill_registry or DEFAULT_SKILLS
        self.progress_callback = progress_callback

        # Initialize history with system prompt
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.history: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]

        # Components
        self.context_manager = ContextManager(self.config.context)

        # State
        self.step = 0
        self.idle_count = 0
        self.tool_definitions = self._get_tool_definitions()

    def run(self, task: str) -> AgentResult:
        """Run the autonomous agent loop."""
        self.history.append({"role": "user", "content": f"Task: {task}"})
        self.step = 0
        self.idle_count = 0

        while True:
            self.step += 1
            logger.info("[agent] step %d starting", self.step)

            # Check stop conditions
            should_stop, reason = self._should_stop()
            if should_stop:
                return AgentResult(
                    success=False,
                    summary=f"Agent stopped: {reason.value}",
                    history=self.history,
                    stop_reason=reason,
                    steps_taken=self.step,
                )

            # Compress context if needed
            self.history = self.context_manager.compress_if_needed(self.history)

            # Call LLM
            try:
                message = self._call_llm_with_retry()
            except Exception as e:
                logger.error("[agent] LLM error: %s", e)
                return AgentResult(
                    success=False,
                    summary=f"LLM Error: {str(e)}",
                    history=self.history,
                    stop_reason=StopReason.ERROR,
                    steps_taken=self.step,
                )

            # Append assistant message
            self.history.append(message)

            content = message.get("content")
            tool_calls = message.get("tool_calls")

            if content:
                logger.debug("[agent] assistant: %s", content[:200])

            if not tool_calls:
                self.idle_count += 1
                logger.debug("[agent] no tool calls, idle_count=%d", self.idle_count)
                continue

            # Reset idle count on tool usage
            self.idle_count = 0

            # Execute tools
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                arguments_str = tool_call["function"]["arguments"]
                call_id = tool_call["id"]

                logger.info("[agent] tool_call: %s", function_name)

                try:
                    args = json.loads(arguments_str)
                    self._emit_progress({
                        "phase": "start",
                        "tool": function_name,
                        "path": args.get("path"),
                        "step": self.step,
                    })

                    # Handle task_done specially
                    if function_name == "task_done":
                        result = self._handle_task_done(args, call_id)
                        if isinstance(result, AgentResult):
                            return result
                        # If not done, result is error message
                        self.history.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": function_name,
                            "content": result,
                        })
                        continue

                    # Execute tool with retry
                    result_text = self._execute_tool_with_retry(function_name, args)
                    self._emit_progress({
                        "phase": "end",
                        "tool": function_name,
                        "path": args.get("path"),
                        "step": self.step,
                        "ok": not result_text.startswith("Error:"),
                    })

                except json.JSONDecodeError as e:
                    result_text = f"Error: Invalid JSON arguments - {e}"
                except Exception as e:
                    logger.error("[agent] tool error: %s", traceback.format_exc())
                    result_text = f"Error executing tool '{function_name}': {str(e)}"
                    self._emit_progress({
                        "phase": "error",
                        "tool": function_name,
                        "path": None,
                        "step": self.step,
                        "ok": False,
                        "error": str(e),
                    })

                # Add tool result
                self.history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": function_name,
                    "content": result_text,
                })

        # Should not reach here
        return AgentResult(
            success=False,
            summary="Unexpected loop exit",
            history=self.history,
            stop_reason=StopReason.ERROR,
            steps_taken=self.step,
        )

    def _emit_progress(self, payload: dict[str, Any]) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(payload)
        except Exception:
            logger.debug("[agent] progress callback failed", exc_info=True)

    def _should_stop(self) -> tuple[bool, StopReason]:
        """Check if the agent should stop."""
        # Max steps
        if self.step > self.config.max_steps:
            return True, StopReason.MAX_STEPS

        # Token budget
        estimated_tokens = self.context_manager.estimate_tokens(self.history)
        if estimated_tokens > self.config.max_tokens:
            logger.warning(
                "[agent] token budget exceeded: %d > %d",
                estimated_tokens,
                self.config.max_tokens
            )
            return True, StopReason.TOKEN_BUDGET

        # Idle detection
        if self.idle_count >= self.config.idle_threshold:
            return True, StopReason.IDLE

        return False, StopReason.TASK_DONE

    def _call_llm_with_retry(self) -> dict[str, Any]:
        """Call LLM with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self.config.retry.max_retries):
            try:
                req = ChatCompletionRequest(
                    api_key=self.llm_config.api_key,
                    base_url=self.llm_config.base_url,
                    model=self.llm_config.model,
                    messages=self.history,
                    temperature=0.0,
                    tools=self.tool_definitions,
                )
                return chat_completion(req)

            except Exception as e:
                last_error = e
                error_str = str(e)

                if not self.config.retry.is_retryable(error_str):
                    raise

                if attempt < self.config.retry.max_retries - 1:
                    delay = self.config.retry.get_delay(attempt)
                    logger.warning(
                        "[agent] LLM call failed (attempt %d), retrying in %.1fs: %s",
                        attempt + 1,
                        delay,
                        error_str[:100]
                    )
                    time.sleep(delay)

        raise last_error or Exception("LLM call failed after retries")

    def _execute_tool_with_retry(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool with retry logic for transient errors."""
        last_result = ""

        for attempt in range(self.config.retry.max_retries):
            result = self._execute_tool(name, args)

            # Check if result indicates a retryable error
            if result.startswith("Error:"):
                if self.config.retry.is_retryable(result):
                    if attempt < self.config.retry.max_retries - 1:
                        delay = self.config.retry.get_delay(attempt)
                        logger.warning(
                            "[agent] tool '%s' failed (attempt %d), retrying: %s",
                            name,
                            attempt + 1,
                            result[:100]
                        )
                        time.sleep(delay)
                        last_result = result
                        continue

                # Non-retryable error or max retries reached
                return self._enhance_error_message(result, name, args)

            return result

        return last_result

    def _enhance_error_message(
        self,
        error: str,
        tool_name: str,
        args: dict[str, Any]
    ) -> str:
        """Add helpful suggestions to error messages."""
        suggestions = []

        if "not found" in error.lower():
            if tool_name in ("read_file", "edit_file"):
                suggestions.append("Use `ls` to check available files first.")
            elif tool_name == "search_files":
                suggestions.append("Try a different search path or pattern.")

        if "syntax error" in error.lower():
            suggestions.append("Check the code syntax and try again.")

        if "permission" in error.lower():
            suggestions.append("The file may be read-only or protected.")

        if "timeout" in error.lower():
            suggestions.append("The operation timed out. Try a simpler command.")

        if suggestions:
            return f"{error}\n\n💡 Suggestions:\n" + "\n".join(f"- {s}" for s in suggestions)

        return error

    def _handle_task_done(
        self,
        args: dict[str, Any],
        call_id: str
    ) -> AgentResult | str:
        """Handle task_done tool call with deliverable verification."""
        summary = args.get("summary", "Done")

        # Verify deliverables using protocol constants
        has_strategy = False
        has_overview = False
        has_overview_diagram = False

        try:
            res_files = self.tools.list_files(".", recursive=False)
            if STRATEGY_FILE in res_files.output:
                has_strategy = True
            if OVERVIEW_FILE in res_files.output:
                has_overview = True
                overview_res = self.tools.read_file(OVERVIEW_FILE)
                if PROTOCOL.overview_required_marker in overview_res.output:
                    has_overview_diagram = True
        except Exception:
            pass

        if not has_strategy:
            return f"Task cannot be completed: `{STRATEGY_FILE}` is missing. Please create the strategy code."

        if not (has_overview and has_overview_diagram):
            return f"Task cannot be completed: `{OVERVIEW_FILE}` with a mermaid diagram is required."

        return AgentResult(
            success=True,
            summary=summary,
            history=self.history,
            stop_reason=StopReason.TASK_DONE,
            steps_taken=self.step,
        )

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Execute a single tool."""
        # Check if tool is allowed
        if self.config.allowed_tools and name not in self.config.allowed_tools:
            return f"Error: Tool '{name}' is not allowed in this context."

        try:
            if name == "ls":
                return self.tools.list_files(
                    path=args.get("path", "."),
                    recursive=args.get("recursive", False)
                ).output or "Empty directory"

            elif name == "read_file":
                res = self.tools.read_file(
                    path=args["path"],
                    start_line=args.get("start_line", 1),
                    end_line=args.get("end_line")
                )
                return res.error if res.error else res.output

            elif name == "search_files":
                res = self.tools.search_files(
                    pattern=args["pattern"],
                    path=args.get("path", ".")
                )
                return res.error if res.error else res.output

            elif name == "edit_file":
                res = self.tools.edit_file(
                    path=args["path"],
                    operation=args["operation"],
                    old_text=args.get("old_text"),
                    new_text=args.get("new_text"),
                    anchor=args.get("anchor"),
                    insert_text=args.get("insert_text"),
                    start_line=args.get("start_line"),
                    end_line=args.get("end_line"),
                    replacement=args.get("replacement")
                )
                return res.error if res.error else res.output

            elif name == "write_file":
                res = self.tools.write_file(path=args["path"], content=args["content"])
                return res.error if res.error else res.output

            # Skills
            elif name.startswith("skill_"):
                return self._run_skill_tool(name, args)

            else:
                return f"Error: Unknown tool '{name}'"

        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"

    def _run_skill_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Run a skill from tool call (e.g., skill_backtest)."""
        context = SkillContext(
            tools=self.tools,
            workspace_root=self.workspace_root,
            history=self.history,
        )

        result = self.skills.execute_skill_tool(tool_name, tool_args, context)

        if result.error:
            return f"Skill Error: {result.error}"

        return result.output

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions for LLM."""
        base_tools = [
            {
                "type": "function",
                "function": {
                    "name": "ls",
                    "description": "List files in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Directory path", "default": "."},
                            "recursive": {"type": "boolean", "description": "List recursively", "default": False}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read content of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                            "start_line": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
                            "end_line": {"type": "integer", "description": "End line (optional)"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Search for text pattern in files (regex supported)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "Regex pattern to search"},
                            "path": {"type": "string", "description": "Directory or file to search", "default": "."},
                            "include": {"type": "string", "description": "File pattern to include (e.g. *.py)", "default": "*.py"}
                        },
                        "required": ["pattern"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "description": "Modify a file using robust fuzzy matching operations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                            "operation": {
                                "type": "string",
                                "enum": ["exact_replace", "insert_after", "insert_before", "range_replace"],
                                "description": "Type of edit operation"
                            },
                            "old_text": {"type": "string", "description": "Text to replace (for exact_replace). Must include unique context."},
                            "new_text": {"type": "string", "description": "Replacement text (for exact_replace)."},
                            "anchor": {"type": "string", "description": "Text to anchor insertion (for insert_*). Must be unique."},
                            "insert_text": {"type": "string", "description": "Text to insert (for insert_*)."},
                            "start_line": {"type": "integer", "description": "Start line (for range_replace)."},
                            "end_line": {"type": "integer", "description": "End line (for range_replace)."},
                            "replacement": {"type": "string", "description": "Replacement text (for range_replace)."}
                        },
                        "required": ["path", "operation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Overwrite or create a file with full content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                            "content": {"type": "string", "description": "Full file content"}
                        },
                        "required": ["path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "task_done",
                    "description": "Mark the task as completed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string", "description": "Summary of work done"}
                        },
                        "required": ["summary"]
                    }
                }
            },
        ]

        # Dynamically add skill tools from registry
        # Each skill becomes an independent tool with its own description
        # so LLM can auto-select based on task requirements
        skill_tools = self.skills.get_tool_definitions()
        base_tools.extend(skill_tools)

        # Filter tools if restrictions are set
        if self.config.allowed_tools:
            allowed = set(self.config.allowed_tools)
            base_tools = [t for t in base_tools if t["function"]["name"] in allowed]

        return base_tools
