import { FC, useMemo } from "react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";

interface DiffViewerProps {
    diffText: string;
    filename?: string;
    scrollClassName?: string;
}

interface DiffLine {
    type: "context" | "add" | "remove" | "header" | "hunk";
    content: string;
    lineNumber?: number;
}

/**
 * Parse unified diff format into structured lines.
 */
function parseDiffLines(diffText: string): DiffLine[] {
    const lines = diffText.split("\n");
    const parsed: DiffLine[] = [];
    let oldLineNum = 0;
    let newLineNum = 0;

    for (const line of lines) {
        if (line.startsWith("---") || line.startsWith("+++")) {
            // File header
            parsed.push({ type: "header", content: line });
        } else if (line.startsWith("@@")) {
            // Hunk header
            parsed.push({ type: "hunk", content: line });

            // Parse hunk to reset line numbers
            const match = line.match(/@@ -(\d+),?\d* \+(\d+),?\d* @@/);
            if (match) {
                oldLineNum = parseInt(match[1], 10);
                newLineNum = parseInt(match[2], 10);
            }
        } else if (line.startsWith("+")) {
            // Addition
            parsed.push({
                type: "add",
                content: line.slice(1),
                lineNumber: newLineNum
            });
            newLineNum++;
        } else if (line.startsWith("-")) {
            // Deletion
            parsed.push({
                type: "remove",
                content: line.slice(1),
                lineNumber: oldLineNum
            });
            oldLineNum++;
        } else if (line.startsWith(" ")) {
            // Context
            parsed.push({
                type: "context",
                content: line.slice(1),
                lineNumber: newLineNum
            });
            oldLineNum++;
            newLineNum++;
        } else if (line === "") {
            // Empty line (context)
            parsed.push({
                type: "context",
                content: "",
                lineNumber: newLineNum
            });
            oldLineNum++;
            newLineNum++;
        }
    }

    return parsed;
}

export const DiffViewer: FC<DiffViewerProps> = ({ diffText, filename = "strategy.py", scrollClassName }) => {
    const parsedLines = useMemo(() => parseDiffLines(diffText), [diffText]);
    const hasCustomScrollClass = Boolean(scrollClassName?.trim());

    if (!diffText || diffText.trim() === "") {
        return (
            <div className="text-sm text-muted-foreground p-4 text-center">
                No changes to display
            </div>
        );
    }

    return (
        <div className={cn(
            "border border-border rounded-md overflow-hidden",
            hasCustomScrollClass && "flex h-full min-h-0 flex-col"
        )}>
            {/* Header */}
            <div className="bg-muted px-3 py-2 border-b border-border">
                <span className="text-sm font-mono font-medium text-foreground">
                    {filename}
                </span>
            </div>

            {/* Diff content */}
            <ScrollArea className={cn(hasCustomScrollClass ? "flex-1 min-h-0" : "h-[400px]", scrollClassName)}>
                <div className="font-mono text-xs">
                    {parsedLines.map((line, idx) => (
                        <div
                            key={idx}
                            className={cn(
                                "px-3 py-0.5 whitespace-pre flex items-center gap-3",
                                line.type === "add" && "bg-long/10 text-long dark:text-long",
                                line.type === "remove" && "bg-short/10 text-short dark:text-short",
                                line.type === "context" && "text-foreground/70",
                                line.type === "header" && "bg-muted font-medium text-foreground",
                                line.type === "hunk" && "bg-muted/50 text-primary font-medium"
                            )}
                        >
                            {/* Line number */}
                            {line.type !== "header" && line.type !== "hunk" && (
                                <span className="text-muted-foreground w-12 text-right flex-shrink-0 select-none">
                                    {line.lineNumber || ""}
                                </span>
                            )}

                            {/* Line type indicator */}
                            {line.type === "add" && (
                                <span className="text-long dark:text-long w-4 flex-shrink-0">+</span>
                            )}
                            {line.type === "remove" && (
                                <span className="text-short dark:text-short w-4 flex-shrink-0">-</span>
                            )}
                            {line.type === "context" && (
                                <span className="text-muted-foreground w-4 flex-shrink-0"> </span>
                            )}

                            {/* Line content */}
                            <span className="flex-1">{line.content}</span>
                        </div>
                    ))}
                </div>
            </ScrollArea>
        </div>
    );
};
