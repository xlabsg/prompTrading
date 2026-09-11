"""Mermaid diagram and markdown sanitizer.

Sanitizes Mermaid flowcharts so that node labels and edge labels containing
parentheses, brackets, or indicators (e.g. `B[Compute SMA(20) & SMA(100)]`)
are safely enclosed in double quotes. This prevents Mermaid syntax parse errors
(such as `got 'PS'`).
"""

import re
from typing import List, Tuple

SHAPES: List[Tuple[str, str]] = [
    ("(((", ")))"),
    ("((", "))"),
    ("([", "])"),
    ("[[", "]]"),
    ("[(", ")]"),
    ("{{", "}}"),
    ("[/", "/]"),
    ("[\\", "\\]"),
    ("[", "]"),
    ("(", ")"),
    ("{", "}"),
    (">", "]"),
]


def sanitize_mermaid_line(line: str) -> str:
    """Sanitize a single line of Mermaid flowchart code."""
    trimmed = line.strip()
    if (
        not trimmed
        or trimmed.startswith("%%")
        or trimmed == "end"
        or trimmed.startswith("classDef")
        or trimmed.startswith("class ")
        or trimmed.startswith("style ")
        or trimmed.startswith("linkStyle")
        or trimmed.startswith("flowchart")
        or trimmed.startswith("graph")
    ):
        return line

    # Handle subgraph header: subgraph ID [Title (with parens)]
    if trimmed.startswith("subgraph"):
        m = re.search(r"subgraph\s+([a-zA-Z0-9_-]+)\s*\[(.*?)\]", line)
        if m:
            sub_id, title = m.group(1), m.group(2).strip()
            if not ((title.startswith('"') and title.endswith('"')) or (title.startswith("'") and title.endswith("'"))):
                escaped = title.replace('"', "#quot;")
                prefix = line[: m.start()]
                suffix = line[m.end() :]
                return f'{prefix}subgraph {sub_id} ["{escaped}"]{suffix}'
        return line

    result: List[str] = []
    i = 0
    n = len(line)

    while i < n:
        # 1. Pipe edge label: |...|
        if line[i] == "|":
            next_pipe = line.find("|", i + 1)
            if next_pipe != -1:
                content = line[i + 1 : next_pipe]
                trimmed_c = content.strip()
                if (trimmed_c.startswith('"') and trimmed_c.endswith('"')) or (
                    trimmed_c.startswith("'") and trimmed_c.endswith("'")
                ):
                    result.append(line[i : next_pipe + 1])
                else:
                    escaped = trimmed_c.replace('"', "#quot;")
                    result.append(f'|"{escaped}"|')
                i = next_pipe + 1
                continue

        # 2. Node definition
        prev_char = line[i - 1] if i > 0 else " "
        if (line[i].isalnum() or line[i] == "_") and (prev_char.isspace() or prev_char in ";&,()|->="):
            id_end = i
            while id_end < n and (line[id_end].isalnum() or line[id_end] in "_-"):
                id_end += 1
            node_id = line[i:id_end]

            matched_shape = None
            for open_delim, close_delim in SHAPES:
                if line.startswith(open_delim, id_end):
                    matched_shape = (open_delim, close_delim)
                    break

            if matched_shape:
                open_delim, close_delim = matched_shape
                content_start = id_end + len(open_delim)
                close_idx = line.find(close_delim, content_start)
                if close_idx != -1:
                    raw_content = line[content_start:close_idx]
                    trimmed_c = raw_content.strip()
                    if (trimmed_c.startswith('"') and trimmed_c.endswith('"')) or (
                        trimmed_c.startswith("'") and trimmed_c.endswith("'")
                    ):
                        new_content = raw_content
                    else:
                        escaped = trimmed_c.replace('"', "#quot;")
                        new_content = f'"{escaped}"'
                    result.append(f"{node_id}{open_delim}{new_content}{close_delim}")
                    i = close_idx + len(close_delim)
                    continue

        result.append(line[i])
        i += 1

    return "".join(result)


def sanitize_mermaid(chart: str) -> str:
    """Sanitize a full Mermaid code block."""
    if not chart:
        return ""
    return "\n".join(sanitize_mermaid_line(l) for l in chart.splitlines())


def sanitize_overview_markdown(md: str) -> str:
    """Find all ```mermaid code blocks in markdown and sanitize them."""
    if not md:
        return ""
    pattern = re.compile(r"(```mermaid[ \t]*\n)([\s\S]*?)(```)")

    def repl(match: re.Match) -> str:
        prefix = match.group(1)
        code = match.group(2)
        suffix = match.group(3)
        return prefix + sanitize_mermaid(code).rstrip("\n") + "\n" + suffix

    return pattern.sub(repl, md)
