"""
AST-based code slicing for intelligent code context extraction.

Instead of naive character truncation, this module:
1. Extracts function signatures for LLM selection
2. Extracts complete function bodies
3. Decomposes long functions into logical blocks
4. Estimates token counts for context management
"""

from __future__ import annotations

import ast
import re
from typing import Any


# Token estimation: 1 token ≈ 4 characters (rough estimate for English)
# For Python code, it's closer to 1 token ≈ 3-4 characters
TOKEN_CHAR_RATIO = 3.5


def estimate_tokens(text: str) -> int:
    """Estimate token count for a string.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return int(len(text) / TOKEN_CHAR_RATIO)


def extract_function_signatures(code: str) -> list[dict[str, Any]]:
    """Extract all function signatures from code.

    Args:
        code: Python source code.

    Returns:
        List of function info dicts with keys:
        - name: Function name
        - signature: Full signature string
        - line_start: Start line number (1-indexed)
        - line_end: End line number (1-indexed)
        - length_lines: Length in lines
        - estimated_tokens: Estimated token count
    """
    if not code or not code.strip():
        return []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    signatures = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            source = ast.get_source_segment(code, node)
            if source:
                # Extract signature line
                sig_line = source.split("\n")[0]
                # Add return type hint if present
                if node.returns:
                    sig_line += f" -> {ast.unparse(node.returns)}"

                signatures.append({
                    "name": node.name,
                    "signature": sig_line,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "length_lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                    "estimated_tokens": estimate_tokens(source),
                })

    return signatures


def extract_class_signatures(code: str) -> list[dict[str, Any]]:
    """Extract all class signatures and their methods.

    Args:
        code: Python source code.

    Returns:
        List of class info dicts with keys:
        - name: Class name
        - line_start: Start line number
        - line_end: End line number
        - methods: List of method signatures
    """
    if not code or not code.strip():
        return []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    classes = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append({
                        "name": item.name,
                        "signature": f"{item.name}({ast.unparse(item.args)})",
                        "line_start": item.lineno,
                        "line_end": item.end_lineno or item.lineno,
                    })

            classes.append({
                "name": node.name,
                "line_start": node.lineno,
                "line_end": node.end_lineno or node.lineno,
                "methods": methods,
            })

    return classes


def extract_function_body(code: str, function_name: str) -> str | None:
    """Extract the complete function body from code.

    Args:
        code: Python source code.
        function_name: Name of the function to extract.

    Returns:
        The complete function source code, or None if not found.
    """
    if not code or not function_name:
        return None

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            source = ast.get_source_segment(code, node)
            return source

    return None


def extract_class_method_body(
    code: str,
    class_name: str,
    method_name: str
) -> str | None:
    """Extract a method body from a class.

    Args:
        code: Python source code.
        class_name: Name of the class.
        method_name: Name of the method.

    Returns:
        The complete method source code, or None if not found.
    """
    if not code or not class_name or not method_name:
        return None

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(code, item)

    return None


def find_anchor_position(
    code: str,
    anchor: str,
    context_lines: int = 5
) -> dict[str, Any] | None:
    """Find the position of an anchor line in code.

    Args:
        code: Python source code.
        anchor: The anchor line to search for (can be partial).
        context_lines: Number of lines to include before/after.

    Returns:
        Dict with keys:
        - found: True if anchor was found
        - line_number: Line number (1-indexed)
        - context: Code snippet with context
        - or None if not found
    """
    if not code or not anchor:
        return None

    lines = code.split("\n")
    anchor_stripped = anchor.strip()

    # Try exact match first
    for i, line in enumerate(lines):
        line_s = line.strip()
        if line_s == anchor_stripped or line_s.replace('"', "'") == anchor_stripped.replace('"', "'"):
            return {
                "found": True,
                "line_number": i + 1,
                "context": _extract_context(lines, i, context_lines),
            }

    # Try partial match (fuzzy)
    for i, line in enumerate(lines):
        line_s = line.strip()
        if anchor_stripped in line_s or anchor_stripped.replace('"', "'") in line_s.replace('"', "'"):
            return {
                "found": True,
                "line_number": i + 1,
                "context": _extract_context(lines, i, context_lines),
                "partial_match": True,
            }

    return None


def _extract_context(
    lines: list[str],
    anchor_index: int,
    context_lines: int
) -> str:
    """Extract context around an anchor line."""
    start = max(0, anchor_index - context_lines)
    end = min(len(lines), anchor_index + context_lines + 1)

    context_lines_list = []
    for i in range(start, end):
        prefix = ">>> " if i == anchor_index else "    "
        context_lines_list.append(f"{prefix}{lines[i]}")

    return "\n".join(context_lines_list)


def should_slice_function(
    function_code: str,
    max_tokens: int = 8000
) -> bool:
    """Determine if a function needs to be split into blocks.

    Args:
        function_code: The function source code.
        max_tokens: Maximum tokens to process at once.

    Returns:
        True if the function should be split.
    """
    return estimate_tokens(function_code) > max_tokens


def extract_logic_blocks(function_code: str) -> list[dict[str, Any]]:
    """Decompose a long function into logical blocks.

    This identifies:
    - Top-level if/elif/else blocks
    - Top-level for/while loops
    - Top-level try/except blocks
    - Assignment sequences
    - Return statements

    Args:
        function_code: The function source code.

    Returns:
        List of block dicts with keys:
        - type: Block type (if_block, for_loop, assignment, return, etc.)
        - content: Block source code
        - line_start: Start line number
        - line_end: End line number
        - indent: Indentation level
    """
    if not function_code:
        return []

    try:
        tree = ast.parse(function_code)
    except SyntaxError:
        # Fallback: split by lines with similar indentation
        return _fallback_block_split(function_code)

    blocks = []
    lines = function_code.split("\n")

    body_nodes = []
    has_functions = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)
    if has_functions:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body_nodes.extend(node.body)
            else:
                body_nodes.append(node)
    else:
        body_nodes = tree.body

    for node in body_nodes:
        if isinstance(node, ast.If):
            source = ast.get_source_segment(function_code, node)
            if source:
                blocks.append({
                    "type": "if_block",
                    "content": source,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                })
        elif isinstance(node, ast.For):
            source = ast.get_source_segment(function_code, node)
            if source:
                blocks.append({
                    "type": "for_loop",
                    "content": source,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                })
        elif isinstance(node, ast.While):
            source = ast.get_source_segment(function_code, node)
            if source:
                blocks.append({
                    "type": "while_loop",
                    "content": source,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                })
        elif isinstance(node, ast.Try):
            source = ast.get_source_segment(function_code, node)
            if source:
                blocks.append({
                    "type": "try_block",
                    "content": source,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                })
        elif isinstance(node, ast.Assign):
            # Group consecutive assignments
            source = ast.get_source_segment(function_code, node)
            if source:
                blocks.append({
                    "type": "assignment",
                    "content": source,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                })
        elif isinstance(node, ast.Return):
            source = ast.get_source_segment(function_code, node)
            if source:
                blocks.append({
                    "type": "return",
                    "content": source,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                })
        elif isinstance(node, ast.Expr):
            # Expression statements (function calls, etc.)
            source = ast.get_source_segment(function_code, node)
            if source:
                blocks.append({
                    "type": "expr",
                    "content": source,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                })

    # If no blocks found, return the whole function as one block
    if not blocks:
        return [{
            "type": "whole_function",
            "content": function_code,
            "line_start": 1,
            "line_end": len(lines),
        }]

    return blocks


def _fallback_block_split(function_code: str) -> list[dict[str, Any]]:
    """Fallback block splitting when AST parsing fails.

    Splits by blank lines and indentation changes.
    """
    lines = function_code.split("\n")
    blocks = []
    current_block = []
    current_indent = None

    for line in lines:
        stripped = line.lstrip()
        if not stripped:  # Blank line
            if current_block:
                blocks.append("\n".join(current_block))
                current_block = []
            continue

        indent = len(line) - len(stripped)
        if current_indent is None:
            current_indent = indent

        # If indentation decreases significantly, start new block
        if current_block and indent < current_indent - 4:
            blocks.append("\n".join(current_block))
            current_block = [line]
            current_indent = indent
        else:
            current_block.append(line)

    if current_block:
        blocks.append("\n".join(current_block))

    return [
        {
            "type": "code_block",
            "content": block,
            "line_start": i + 1,
        }
        for i, block in enumerate(blocks)
        if block.strip()
    ]


def find_block_with_anchor(
    blocks: list[dict[str, Any]],
    anchor: str
) -> dict[str, Any] | None:
    """Find the block containing an anchor line.

    Args:
        blocks: List of block dicts from extract_logic_blocks.
        anchor: The anchor line to search for.

    Returns:
        The block containing the anchor, or None.
    """
    if not anchor:
        return None

    anchor_stripped = anchor.strip()

    for block in blocks:
        content = block.get("content", "")
        if anchor_stripped in content:
            return block

    return None


def prepare_code_summary(code: str, max_tokens: int = 2000) -> str:
    """Prepare a code summary for LLM consumption.

    This provides:
    1. Function signatures list
    2. Class signatures with methods
    3. Import statements
    4. Token-efficient representation

    Args:
        code: Python source code.
        max_tokens: Maximum tokens for the summary.

    Returns:
        A string summary of the code structure.
    """
    if not code:
        return "# Empty code"

    lines = code.split("\n")

    # Extract imports
    imports = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(line)

    # Extract function signatures
    functions = extract_function_signatures(code)

    # Extract class signatures
    classes = extract_class_signatures(code)

    # Build summary
    parts = []

    if imports:
        parts.append("# Imports:")
        parts.extend(imports)
        parts.append("")

    if functions:
        parts.append("# Functions:")
        for f in functions:
            parts.append(f"  # Line {f['line_start']}: {f['signature']} ({f['length_lines']} lines)")
        parts.append("")

    if classes:
        parts.append("# Classes:")
        for c in classes:
            parts.append(f"  # Line {c['line_start']}: class {c['name']}")
            for m in c.get("methods", []):
                parts.append(f"    # Line {m['line_start']}: {m['signature']}")
        parts.append("")

    summary = "\n".join(parts)

    # If still too long, truncate
    if estimate_tokens(summary) > max_tokens:
        # Keep imports, truncate functions/classes list
        result = []
        if imports:
            result.extend(imports)
            result.append("")

        result.append("# Functions:")
        for f in functions[:10]:  # Limit to 10 functions
            result.append(f"  {f['signature']}")

        result.append("\n... (truncated)")
        summary = "\n".join(result)

    return summary


def extract_relevant_context(
    code: str,
    target_name: str | None = None,
    anchor: str | None = None,
    max_tokens: int = 8000
) -> dict[str, Any]:
    """Extract relevant code context for an LLM operation.

    This is the main entry point for context extraction. It:
    1. If target_name is given, extracts that function/class
    2. If anchor is given, extracts context around the anchor
    3. Ensures the result fits within max_tokens

    Args:
        code: Full source code.
        target_name: Optional function/class name to extract.
        anchor: Optional anchor line for precise positioning.
        max_tokens: Maximum tokens to return.

    Returns:
        Dict with keys:
        - code: Extracted code
        - type: "function" | "class" | "context" | "full"
        - name: Name of extracted entity
        - line_start: Start line in original code
        - line_end: End line in original code
        - tokens: Estimated token count
    """
    if not code:
        return {
            "code": "# Empty",
            "type": "empty",
            "tokens": 0,
        }

    # Case 1: Extract specific function
    if target_name:
        func_code = extract_function_body(code, target_name)
        if func_code:
            tokens = estimate_tokens(func_code)
            if tokens <= max_tokens:
                return {
                    "code": func_code,
                    "type": "function",
                    "name": target_name,
                    "tokens": tokens,
                }
            else:
                # Function too long, use blocks
                blocks = extract_logic_blocks(func_code)
                return {
                    "code": func_code,
                    "type": "function_long",
                    "name": target_name,
                    "tokens": tokens,
                    "blocks": blocks,
                    "needs_splitting": True,
                }

    # Case 2: Extract context around anchor
    if anchor:
        anchor_pos = find_anchor_position(code, anchor, context_lines=20)
        if anchor_pos:
            return {
                "code": anchor_pos["context"],
                "type": "context",
                "anchor": anchor,
                "line_number": anchor_pos["line_number"],
                "tokens": estimate_tokens(anchor_pos["context"]),
            }

    # Case 3: Return summary (not full code)
    summary = prepare_code_summary(code, max_tokens)
    return {
        "code": summary,
        "type": "summary",
        "tokens": estimate_tokens(summary),
    }


__all__ = [
    "estimate_tokens",
    "extract_function_signatures",
    "extract_class_signatures",
    "extract_function_body",
    "extract_class_method_body",
    "find_anchor_position",
    "should_slice_function",
    "extract_logic_blocks",
    "find_block_with_anchor",
    "prepare_code_summary",
    "extract_relevant_context",
]
