"""Change-spec adapter over the shared `code_editor` fuzzy matcher.

Text matching lives in `code_editor.core.editor.replace`, which carries the
progressive fallback strategies (line-trimmed, block-anchor, whitespace- and
indentation-flexible, ...). This module only maps change-spec operations onto it.
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict, Any

from code_editor.core.editor import EditError, replace as fuzzy_replace

@dataclass
class EditResult:
    success: bool
    modified_code: str
    error: Optional[str] = None
    details: Optional[str] = None

class CodeEditor:
    """
    A robust code editor that handles fuzzy matching and structured code modifications.
    Mimics the capabilities of advanced coding agents.
    """

    def __init__(self, content: str):
        self.original_content = content
        self.lines = content.splitlines(keepends=True)

    def apply_change_spec(self, change_spec: Dict[str, Any]) -> EditResult:
        """
        Apply a full ChangeSpec (list of operations).
        """
        current_content = self.original_content
        operations = change_spec.get("operations", [])

        for i, op in enumerate(operations):
            op_type = op.get("type")
            try:
                if op_type == "exact_replace":
                    current_content = self._apply_replace(current_content, op["old_text"], op["new_text"])
                elif op_type == "insert_after":
                    current_content = self._apply_insert(current_content, op["anchor"], op["insert_text"], position="after")
                elif op_type == "insert_before":
                    current_content = self._apply_insert(current_content, op["anchor"], op["insert_text"], position="before")
                elif op_type == "range_replace":
                    # Range replace is fragile, fallback to simple line replacement if possible
                    current_content = self._apply_range_replace(current_content, op["start_line"], op["end_line"], op["replacement"])
                elif op_type == "unified_diff":
                    # Not implemented in this strict version, handled by fallback usually
                    pass
                else:
                    raise ValueError(f"Unknown operation type: {op_type}")
            except Exception as e:
                return EditResult(
                    success=False,
                    modified_code=self.original_content,
                    error=f"Operation {i} ({op_type}) failed: {str(e)}",
                    details=f"Failed op: {op}"
                )

        return EditResult(success=True, modified_code=current_content)

    def _normalize(self, text: str) -> str:
        """Normalize whitespace for fuzzy comparison."""
        return re.sub(r'\s+', ' ', text).strip()

    def _apply_replace(self, content: str, old_text: str, new_text: str) -> str:
        """Replace `old_text` using the shared fuzzy matcher."""
        if not old_text:
            raise ValueError("old_text is empty")
        if old_text == new_text:
            return content
        try:
            return fuzzy_replace(content, old_text, new_text)
        except EditError as e:
            snippet = old_text[:200] + "..." if len(old_text) > 200 else old_text
            raise ValueError(f"{e} Preview: {snippet!r}") from e

    def _apply_insert(self, content: str, anchor: str, insert_text: str, position: str = "after") -> str:
        if anchor in content:
            if position == "after":
                return content.replace(anchor, anchor + "\n" + insert_text, 1)
            else:
                return content.replace(anchor, insert_text + "\n" + anchor, 1)

        # Fuzzy insert
        content_lines = content.splitlines()
        anchor_lines = anchor.splitlines()

        # Normalize
        norm_anchor = [self._normalize(l) for l in anchor_lines if l.strip()]
        if not norm_anchor:
             raise ValueError("Empty anchor provided")

        # Search
        for i in range(len(content_lines)):
            if self._normalize(content_lines[i]) == norm_anchor[0]:
                # Potential match start
                match = True
                for j in range(1, len(norm_anchor)):
                    if i + j >= len(content_lines) or self._normalize(content_lines[i+j]) != norm_anchor[j]:
                        match = False
                        break

                if match:
                    # Found it at line i (end at i + len - 1)
                    insertion_idx = i + len(norm_anchor) if position == "after" else i

                    pre = content_lines[:insertion_idx]
                    post = content_lines[insertion_idx:]

                    # Convert list back to string
                    new_block = insert_text.splitlines()

                    final_lines = pre + new_block + post
                    return "\n".join(final_lines)

        raise ValueError(f"Anchor not found: {anchor[:100]}...")

    def _apply_range_replace(self, content: str, start: int, end: int, replacement: str) -> str:
        lines = content.splitlines()
        # Convert 1-based to 0-based
        idx_start = start - 1
        idx_end = end # slice is exclusive at end, so line 50 included means up to index 50 (start of line 51)

        if idx_start < 0 or idx_end > len(lines):
            raise ValueError(f"Line range {start}-{end} out of bounds (file has {len(lines)} lines)")

        pre = lines[:idx_start]
        post = lines[idx_end:]

        return "\n".join(pre + replacement.splitlines() + post)
