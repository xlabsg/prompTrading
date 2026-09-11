/**
 * Mermaid diagram sanitizer utility.
 *
 * In Mermaid flowcharts, unquoted parentheses `(` and `)` inside shape delimiters
 * (e.g. `B[Compute SMA(20) & SMA(100)]` or `-->|entry (long)|`) cause syntax parse errors
 * because `(` is treated as the `PS` (Paren Start) token.
 *
 * This utility safely pre-processes Mermaid code to wrap unquoted node and edge
 * labels in double quotes (e.g. `B["Compute SMA(20) & SMA(100)"]`), while preserving
 * already-quoted strings, styling directives, and subgraphs.
 */

const SHAPES: Array<{ open: string; close: string }> = [
  { open: "(((", close: ")))" },
  { open: "((",  close: "))" },
  { open: "([",  close: "])" },
  { open: "[[",  close: "]]" },
  { open: "[(",  close: ")]" },
  { open: "{{",  close: "}}" },
  { open: "[/",  close: "/]" },
  { open: "[\\", close: "\\]" },
  { open: "[",   close: "]" },
  { open: "(",   close: ")" },
  { open: "{",   close: "}" },
  { open: ">",   close: "]" },
];

function sanitizeLine(line: string): string {
  const trimmed = line.trim();
  if (
    !trimmed ||
    trimmed.startsWith("%%") ||
    trimmed === "end" ||
    trimmed.startsWith("classDef") ||
    trimmed.startsWith("class ") ||
    trimmed.startsWith("style ") ||
    trimmed.startsWith("linkStyle") ||
    trimmed.startsWith("flowchart") ||
    trimmed.startsWith("graph")
  ) {
    return line;
  }

  // Handle subgraph header: subgraph ID [Title (with parens)]
  if (trimmed.startsWith("subgraph")) {
    return line.replace(/subgraph\s+([a-zA-Z0-9_-]+)\s*\[(.*?)\]/, (m, id, title) => {
      const trimmedTitle = title.trim();
      if (
        (trimmedTitle.startsWith('"') && trimmedTitle.endsWith('"')) ||
        (trimmedTitle.startsWith("'") && trimmedTitle.endsWith("'"))
      ) {
        return m;
      }
      const escaped = trimmedTitle.replace(/"/g, "#quot;");
      return `subgraph ${id} ["${escaped}"]`;
    });
  }

  let result = "";
  let i = 0;

  while (i < line.length) {
    // 1. Pipe edge label: |...|
    if (line[i] === "|") {
      const nextPipe = line.indexOf("|", i + 1);
      if (nextPipe !== -1) {
        const rawContent = line.slice(i + 1, nextPipe);
        const trimmedContent = rawContent.trim();
        let newContent = rawContent;
        if (
          !(
            (trimmedContent.startsWith('"') && trimmedContent.endsWith('"')) ||
            (trimmedContent.startsWith("'") && trimmedContent.endsWith("'"))
          )
        ) {
          const escaped = trimmedContent.replace(/"/g, "#quot;");
          newContent = `"${escaped}"`;
        }
        result += `|${newContent}|`;
        i = nextPipe + 1;
        continue;
      }
    }

    // 2. Node definition: must start with [a-zA-Z0-9_\u4e00-\u9fa5]
    // preceded by start of line, space, or punctuation (like ; & , ( ) | - > =)
    const prevChar = i > 0 ? line[i - 1] : " ";
    if (
      /[a-zA-Z0-9_\u4e00-\u9fa5]/.test(line[i]) &&
      /[\s;&,()|\->=]/.test(prevChar)
    ) {
      let idEnd = i;
      while (
        idEnd < line.length &&
        /[a-zA-Z0-9_\u4e00-\u9fa5-]/.test(line[idEnd])
      ) {
        idEnd++;
      }
      const id = line.slice(i, idEnd);

      // Check if immediately followed by a shape open delimiter
      let matchedShape: { open: string; close: string } | null = null;
      for (const shape of SHAPES) {
        if (line.startsWith(shape.open, idEnd)) {
          matchedShape = shape;
          break;
        }
      }

      if (matchedShape) {
        const contentStart = idEnd + matchedShape.open.length;
        const closeIdx = line.indexOf(matchedShape.close, contentStart);
        if (closeIdx !== -1) {
          const rawContent = line.slice(contentStart, closeIdx);
          const trimmedContent = rawContent.trim();
          let newContent = rawContent;
          if (
            !(
              (trimmedContent.startsWith('"') && trimmedContent.endsWith('"')) ||
              (trimmedContent.startsWith("'") && trimmedContent.endsWith("'"))
            )
          ) {
            const escaped = trimmedContent.replace(/"/g, "#quot;");
            newContent = `"${escaped}"`;
          }
          result += id + matchedShape.open + newContent + matchedShape.close;
          i = closeIdx + matchedShape.close.length;
          continue;
        }
      }
    }

    result += line[i];
    i++;
  }

  return result;
}

/**
 * Sanitize a full Mermaid code string before passing to mermaid.render / mermaid.parse.
 */
export function sanitizeMermaid(chart: string): string {
  if (!chart || typeof chart !== "string") return chart;
  return chart.split("\n").map(sanitizeLine).join("\n");
}
