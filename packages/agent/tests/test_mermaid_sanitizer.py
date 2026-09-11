"""Unit tests for mermaid_sanitizer."""

import pytest
from agent.mermaid_sanitizer import (
    sanitize_mermaid,
    sanitize_mermaid_line,
    sanitize_overview_markdown,
)


def test_colleague_parse_error_reproduced_and_fixed():
    raw_chart = (
        "flowchart TD\n"
        "  A[Market Data / Bar] --> B[Compute SMA(20) & SMA(100)]\n"
        "  B --> C{Cross(fast, slow)}\n"
        "  C -->|entry (long)| D([Open Long (1.0)])\n"
        "  C -->|entry (short)| E([Open Short (-1.0)])\n"
        "  D --> F[Trailing Stop (2%)]\n"
        "  E --> F\n"
        "  F -->|exit| G[Close Position]\n"
    )
    sanitized = sanitize_mermaid(raw_chart)

    # Verify node B has double quotes wrapping the label with parentheses
    assert 'B["Compute SMA(20) & SMA(100)"]' in sanitized
    # Verify decision node C has double quotes
    assert 'C{"Cross(fast, slow)"}' in sanitized
    # Verify edge labels have double quotes
    assert '|"entry (long)"|' in sanitized
    assert '|"entry (short)"|' in sanitized
    # Verify stadium node D has double quotes
    assert 'D(["Open Long (1.0)"])' in sanitized
    # Verify trailing stop node F has double quotes
    assert 'F["Trailing Stop (2%)"]' in sanitized


def test_already_quoted_labels_are_preserved():
    chart = (
        "flowchart TD\n"
        '  A["Pre-quoted (20)"] --> B["Another (100)"]\n'
        "  B -->|'single quoted'| C\n"
    )
    sanitized = sanitize_mermaid(chart)
    assert 'A["Pre-quoted (20)"]' in sanitized
    assert 'B["Another (100)"]' in sanitized
    assert "|'single quoted'|" in sanitized


def test_subgraph_with_parentheses():
    line = "  subgraph Sub1 [Indicators (SMA & EMA)]"
    sanitized = sanitize_mermaid_line(line)
    assert 'subgraph Sub1 ["Indicators (SMA & EMA)"]' in sanitized


def test_directives_and_comments_untouched():
    chart = (
        "%% This is a comment (with parens)\n"
        "flowchart LR\n"
        "  classDef default fill:#f9f,stroke:#333\n"
        "  style A fill:#bbf,stroke:#f66\n"
        "  A[Simple] --> B[Basic]\n"
    )
    sanitized = sanitize_mermaid(chart)
    assert "%% This is a comment (with parens)" in sanitized
    assert "classDef default fill:#f9f,stroke:#333" in sanitized
    assert "style A fill:#bbf,stroke:#f66" in sanitized
    assert 'A["Simple"]' in sanitized
    assert 'B["Basic"]' in sanitized


def test_sanitize_overview_markdown():
    markdown = (
        "# Summary\n\n"
        "A dual moving average strategy.\n\n"
        "# Flow Animation\n\n"
        "```mermaid\n"
        "flowchart TD\n"
        "  A[Tick] --> B[SMA(20)]\n"
        "  B --> C[SMA(100)]\n"
        "```\n\n"
        "# Trading Board\n\n"
        "- Monitor equity and drawdowns.\n"
    )
    sanitized_md = sanitize_overview_markdown(markdown)
    assert 'B["SMA(20)"]' in sanitized_md
    assert 'C["SMA(100)"]' in sanitized_md
    assert "# Summary\n\nA dual moving average strategy." in sanitized_md
    assert "# Trading Board" in sanitized_md


def test_internal_quotes_escaped():
    line = '  A[Price "Close" > 100]'
    sanitized = sanitize_mermaid_line(line)
    assert 'A["Price #quot;Close#quot; > 100"]' in sanitized
