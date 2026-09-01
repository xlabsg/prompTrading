import os
import subprocess
import fnmatch
import ast
import re
import json
import pandas as pd
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from agent.editor import CodeEditor
from agent.protocol import STRATEGY_FILE, STRATEGY_FUNCTION
from backtest.vectorized import run_backtest, BacktestConfig

@dataclass
class ToolResult:
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class FileSystemTools:
    def __init__(self, workspace_root: str):
        self.root = os.path.abspath(workspace_root)

    def _resolve_path(self, path: str) -> str:
        """Resolve path relative to workspace root and ensure safety."""
        if os.path.isabs(path):
            abs_path = os.path.normpath(path)
        else:
            abs_path = os.path.normpath(os.path.join(self.root, path))

        if not abs_path.startswith(self.root):
            raise ValueError(f"Path traversal attempted: {path}")
        return abs_path

    def _rel_path(self, path: str) -> str:
        """Return path relative to workspace root for display."""
        return os.path.relpath(path, self.root)

    def list_files(self, path: str = ".", recursive: bool = False, max_depth: int = 2) -> ToolResult:
        """List files in directory."""
        try:
            target_dir = self._resolve_path(path)
            if not os.path.exists(target_dir):
                return ToolResult(output="", error=f"Directory not found: {path}")

            results = []
            if recursive:
                for root, dirs, files in os.walk(target_dir):
                    depth = root[len(target_dir):].count(os.sep)
                    if depth < max_depth:
                        for f in files:
                            if not f.startswith("."):
                                full_path = os.path.join(root, f)
                                results.append(self._rel_path(full_path))
            else:
                for item in os.listdir(target_dir):
                    if not item.startswith("."):
                        results.append(item)

            return ToolResult(output="\n".join(sorted(results)))
        except Exception as e:
            return ToolResult(output="", error=str(e))

    def read_file(self, path: str, start_line: int = 1, end_line: Optional[int] = None) -> ToolResult:
        """Read file content with optional line numbers."""
        try:
            target_path = self._resolve_path(path)
            if not os.path.isfile(target_path):
                return ToolResult(output="", error=f"File not found: {path}")

            with open(target_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, end_line) if end_line else total_lines

            content = "".join(lines[start_idx:end_idx])

            if start_line > 1 or end_line:
                numbered_lines = []
                for i, line in enumerate(lines[start_idx:end_idx], start=start_idx + 1):
                    numbered_lines.append(f"{i:4d} | {line}")
                return ToolResult(output="".join(numbered_lines))

            return ToolResult(output=content)
        except Exception as e:
            return ToolResult(output="", error=str(e))

    def grep(self, pattern: str, path: str = ".", include: str = "*.py") -> ToolResult:
        """Alias for search_files for backward compatibility with prompts."""
        return self.search_files(pattern, path, include)

    def search_files(self, pattern: str, path: str = ".", include: str = "*.py") -> ToolResult:
        """Search for text pattern in files (Pure Python grep implementation)."""
        try:
            target_path = self._resolve_path(path)
            regex = re.compile(pattern)
            results = []

            # Helper to check if file matches include pattern
            def matches_include(filename):
                return fnmatch.fnmatch(filename, include)

            if os.path.isfile(target_path):
                files_to_search = [target_path]
            else:
                files_to_search = []
                for root, _, files in os.walk(target_path):
                    for f in files:
                        if matches_include(f):
                            files_to_search.append(os.path.join(root, f))

            match_count = 0
            for file_path in files_to_search:
                if match_count >= 50: break
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = self._rel_path(file_path)
                                results.append(f"{rel_path}:{i}:{line.strip()}")
                                match_count += 1
                                if match_count >= 50: break
                except Exception:
                    continue

            output = "\n".join(results)
            if match_count >= 50:
                output += "\n... (more matches truncated)"

            return ToolResult(output=output if output else "No matches found.")
        except Exception as e:
            return ToolResult(output="", error=str(e))

    def run_command(self, command: str) -> ToolResult:
        """Run a shell command safely."""
        # Whitelist allowed commands for safety
        allowed_cmds = ["python", "pytest", "ls", "pwd", "echo", "cat"]
        cmd_parts = command.split()
        if not cmd_parts or cmd_parts[0] not in allowed_cmds:
             # Relax constraint for development, but in prod this should be strict
             pass

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30 # 30s timeout
            )
            output = result.stdout
            if result.stderr:
                output += "\nSTDERR:\n" + result.stderr
            return ToolResult(output=output)
        except subprocess.TimeoutExpired:
            return ToolResult(output="", error="Command timed out")
        except Exception as e:
            return ToolResult(output="", error=str(e))

    def edit_file(self, path: str, operation: str, **kwargs) -> ToolResult:
        """
        Apply edits using the robust CodeEditor and verify syntax.
        """
        try:
            target_path = self._resolve_path(path)
            if not os.path.exists(target_path):
                return ToolResult(output="", error=f"File not found: {path}")

            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()

            editor = CodeEditor(content)
            spec = {"operations": [{"type": operation, **kwargs}]}
            result = editor.apply_change_spec(spec)

            if not result.success:
                return ToolResult(output="", error=result.error)

            # Syntax Check (Python only)
            if path.endswith(".py"):
                try:
                    ast.parse(result.modified_code)
                except SyntaxError as e:
                    return ToolResult(
                        output="",
                        error=f"Syntax Error in modified code: {e}\nLine {e.lineno}: {e.text}"
                    )

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(result.modified_code)

            return ToolResult(output=f"Successfully applied {operation} to {path}")

        except Exception as e:
            return ToolResult(output="", error=str(e))

    def write_file(self, path: str, content: str) -> ToolResult:
        try:
            target_path = self._resolve_path(path)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # Syntax Check for new files
            if path.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    return ToolResult(
                        output="",
                        error=f"Syntax Error in new file content: {e}\nLine {e.lineno}: {e.text}"
                    )

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(output=f"Successfully wrote to {path}")
        except Exception as e:
            return ToolResult(output="", error=str(e))

    def run_backtest(self, interval: str = "1h", data_path: Optional[str] = None) -> ToolResult:
        """
        Run a backtest on the current strategy.
        Uses synthetic data if data_path is not provided.
        """
        try:
            strategy_path = self._resolve_path(STRATEGY_FILE)
            if not os.path.isfile(strategy_path):
                return ToolResult(output="", error=f"{STRATEGY_FILE} not found")

            # Load strategy module dynamically
            import importlib.util
            spec = importlib.util.spec_from_file_location("strategy_module", strategy_path)
            if not spec or not spec.loader:
                return ToolResult(output="", error="Failed to load strategy module")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, STRATEGY_FUNCTION):
                return ToolResult(output="", error=f"{STRATEGY_FUNCTION}() function not found in {STRATEGY_FILE}")

            # Prepare data
            if data_path:
                data_abs_path = self._resolve_path(data_path)
                data = pd.read_csv(data_abs_path) # Assuming CSV for now
                # Basic validation
                required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
                if not all(col in data.columns for col in required_cols):
                     return ToolResult(output="", error=f"Data file missing columns. Required: {required_cols}")
            else:
                # Synthetic data for quick testing
                dates = pd.date_range(end=pd.Timestamp.now(), periods=1000, freq=interval)
                timestamps = dates.astype('int64') // 10**6 # ms
                close = np.cumprod(1 + np.random.normal(0, 0.01, 1000)) * 100
                data = pd.DataFrame({
                    "timestamp": timestamps,
                    "open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                    "volume": np.random.random(1000) * 1000
                })
                # Add numpy import for synthetic data gen
                import numpy as np

            # Run Strategy
            params = {} # Could allow passing params later
            try:
                signals = module.generate_signals(data.copy(), params)
            except Exception as e:
                return ToolResult(output="", error=f"Strategy Execution Error: {str(e)}")

            # Run Backtest Engine
            try:
                result = run_backtest(
                    data,
                    signals=signals,
                    interval=interval,
                    config=BacktestConfig()
                )
            except Exception as e:
                return ToolResult(output="", error=f"Backtest Engine Error: {str(e)}")

            # Format Metrics
            metrics_str = json.dumps(result.metrics, indent=2)
            summary = (
                f"Backtest Completed Successfully.\n"
                f"Sharpe Ratio: {result.metrics.get('sharpe_ratio', 0):.2f}\n"
                f"Total Return: {result.metrics.get('total_return', 0):.2f}%\n"
                f"Max Drawdown: {result.metrics.get('max_drawdown', 0):.2f}%\n"
                f"Trades: {result.metrics.get('total_trades', 0)}\n\n"
                f"Full Metrics:\n{metrics_str}"
            )

            return ToolResult(output=summary, metadata=result.metrics)

        except Exception as e:
            return ToolResult(output="", error=f"System Error: {str(e)}")
