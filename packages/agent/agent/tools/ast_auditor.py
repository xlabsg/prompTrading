from __future__ import annotations

import ast
import logging
from typing import Any
from agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

DISALLOWED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "socket", "urllib", "requests", "httpx", "aiohttp",
    "shutil", "builtins", "importlib", "pty", "posix",
})


class LookaheadVisitor(ast.NodeVisitor):
    def __init__(self):
        self.issues: list[str] = []

    def visit_Call(self, node: ast.Call):
        # Detect df.shift(-1) or series.shift(-k)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "shift":
            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.UnaryOp) and isinstance(arg0.op, ast.USub):
                    self.issues.append(
                        f"Line {node.lineno}: Potential lookahead bias detected: negative shift() call."
                    )
                elif isinstance(arg0, ast.Constant) and isinstance(arg0.value, (int, float)) and arg0.value < 0:
                    self.issues.append(
                        f"Line {node.lineno}: Potential lookahead bias detected: shift({arg0.value}) looks into the future."
                    )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in DISALLOWED_IMPORTS:
                self.issues.append(f"Line {node.lineno}: Prohibited import '{alias.name}'.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in DISALLOWED_IMPORTS:
                self.issues.append(f"Line {node.lineno}: Prohibited from-import '{node.module}'.")
        self.generic_visit(node)


class ASTAuditorTool(BaseTool):
    """Audits generated strategy Python code for lookahead bias, syntax errors, and security issues."""

    name = "ast_auditor"
    description = (
        "Static code audit tool that checks strategy code for syntax correctness, "
        "lookahead data leaks (future bias), and unsafe system calls."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python strategy source code"},
        },
        "required": ["code"],
    }

    async def run(self, code: str, **kwargs: Any) -> ToolResult:
        if not code or not code.strip():
            return ToolResult(success=False, data={"passed": False, "issues": ["Code is empty"]})

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ToolResult(
                success=True,
                data={
                    "passed": False,
                    "syntax_valid": False,
                    "issues": [f"SyntaxError on line {e.lineno}: {e.msg}"],
                    "quality_score": 0.0,
                },
            )

        visitor = LookaheadVisitor()
        visitor.visit(tree)

        passed = len(visitor.issues) == 0
        score = 100.0 if passed else max(0.0, 100.0 - (len(visitor.issues) * 25.0))

        return ToolResult(
            success=True,
            data={
                "passed": passed,
                "syntax_valid": True,
                "issues": visitor.issues,
                "quality_score": score,
            },
        )
