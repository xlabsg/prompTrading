"""The change-spec editor must keep working after delegating to `code_editor`."""

from __future__ import annotations

import textwrap

from agent.editor import CodeEditor

SOURCE = textwrap.dedent(
    """\
    import numpy as np


    def generate_signals(data, params):
        close = data["close"].to_numpy()
        fast = 10
        slow = 30
        return {"target_weights": close}
    """
)


def apply(source, ops):
    return CodeEditor(source).apply_change_spec({"operations": ops})


def test_exact_replace():
    res = apply(SOURCE, [{"type": "exact_replace", "old_text": "fast = 10", "new_text": "fast = 5"}])
    assert res.success, res.error
    assert "fast = 5" in res.modified_code
    assert "slow = 30" in res.modified_code


def test_replace_tolerates_whitespace_drift():
    """The shared matcher should still find text whose indentation differs."""
    res = apply(
        SOURCE,
        [{"type": "exact_replace", "old_text": "fast   =   10", "new_text": "fast = 7"}],
    )
    assert res.success, res.error
    assert "fast = 7" in res.modified_code


def test_replace_reports_missing_text():
    res = apply(SOURCE, [{"type": "exact_replace", "old_text": "nonexistent_token", "new_text": "x"}])
    assert not res.success
    assert "nonexistent_token" in (res.error or "")


def test_replace_with_identical_text_is_noop():
    res = apply(SOURCE, [{"type": "exact_replace", "old_text": "fast = 10", "new_text": "fast = 10"}])
    assert res.success, res.error
    assert res.modified_code == SOURCE


def test_insert_after_preserves_surrounding_lines():
    res = apply(
        SOURCE,
        [{"type": "insert_after", "anchor": "    slow = 30", "insert_text": "    extra = 1"}],
    )
    assert res.success, res.error
    lines = res.modified_code.splitlines()
    idx = lines.index("    slow = 30")
    assert lines[idx + 1] == "    extra = 1"
    assert "    fast = 10" in lines, "existing indentation must be preserved"


def test_insert_before():
    res = apply(
        SOURCE,
        [{"type": "insert_before", "anchor": "    slow = 30", "insert_text": "    extra = 2"}],
    )
    assert res.success, res.error
    lines = res.modified_code.splitlines()
    assert lines[lines.index("    slow = 30") - 1] == "    extra = 2"


def test_range_replace():
    res = apply(SOURCE, [{"type": "range_replace", "start_line": 6, "end_line": 6, "replacement": "    fast = 99"}])
    assert res.success, res.error
    assert "fast = 99" in res.modified_code
    assert "fast = 10" not in res.modified_code


def test_range_replace_out_of_bounds_reports_error():
    res = apply(SOURCE, [{"type": "range_replace", "start_line": 1, "end_line": 999, "replacement": "x"}])
    assert not res.success
    assert "out of bounds" in (res.error or "")


def test_multiple_operations_applied_in_order():
    res = apply(
        SOURCE,
        [
            {"type": "exact_replace", "old_text": "fast = 10", "new_text": "fast = 11"},
            {"type": "exact_replace", "old_text": "slow = 30", "new_text": "slow = 31"},
        ],
    )
    assert res.success, res.error
    assert "fast = 11" in res.modified_code and "slow = 31" in res.modified_code


def test_failed_operation_leaves_original_untouched():
    res = apply(
        SOURCE,
        [
            {"type": "exact_replace", "old_text": "fast = 10", "new_text": "fast = 11"},
            {"type": "exact_replace", "old_text": "missing", "new_text": "x"},
        ],
    )
    assert not res.success
    assert res.modified_code == SOURCE, "a failed spec must not partially apply"


def test_unknown_operation_rejected():
    res = apply(SOURCE, [{"type": "teleport", "old_text": "a", "new_text": "b"}])
    assert not res.success
    assert "Unknown operation" in (res.error or "")
