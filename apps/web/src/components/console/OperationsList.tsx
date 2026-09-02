import { FC } from "react";
import { FileEdit, ArrowDown, ArrowUp, Replace, FileCode } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChangeOperation } from "@/lib/types";

const operationIcons: Record<string, JSX.Element> = {
    exact_replace: <Replace size={14} className="text-primary" />,
    range_replace: <FileEdit size={14} className="text-primary" />,
    insert_after: <ArrowDown size={14} className="text-long" />,
    insert_before: <ArrowUp size={14} className="text-muted-foreground" />,
    unified_diff: <FileCode size={14} className="text-muted-foreground" />,
};

const operationLabels: Record<string, string> = {
    exact_replace: "Replace Text",
    range_replace: "Replace Lines",
    insert_after: "Insert After",
    insert_before: "Insert Before",
    unified_diff: "Unified Diff",
};

interface OperationsListProps {
    operations: ChangeOperation[];
}

export const OperationsList: FC<OperationsListProps> = ({ operations }) => {
    if (!operations || operations.length === 0) {
        return null;
    }

    return (
        <div className="space-y-2">
            {operations.map((op, idx) => (
                <div
                    key={idx}
                    className={cn(
                        "flex items-start gap-2 p-2 rounded-md",
                        "bg-muted/30 hover:bg-muted/50 transition-colors"
                    )}
                >
                    <div className="mt-0.5 flex-shrink-0">
                        {operationIcons[op.type] || <FileEdit size={14} />}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-medium text-foreground">
                                {operationLabels[op.type] || op.type}
                            </span>
                            {op.start_line && op.end_line && (
                                <span className="text-xs text-muted-foreground">
                                    Lines {op.start_line}-{op.end_line}
                                </span>
                            )}
                        </div>

                        {op.description && (
                            <div className="text-xs text-muted-foreground mt-0.5">
                                {op.description}
                            </div>
                        )}

                        {op.anchor && (
                            <code className="block text-xs bg-background px-1.5 py-0.5 rounded mt-1 font-mono text-foreground/80 truncate">
                                {op.anchor.length > 60 ? `${op.anchor.slice(0, 60)}...` : op.anchor}
                            </code>
                        )}

                        {op.old_text && op.new_text && (
                            <div className="mt-1 space-y-0.5">
                                <div className="flex items-center gap-1">
                                    <span className="text-xs text-short">-</span>
                                    <code className="text-xs font-mono text-short/80 truncate">
                                        {op.old_text.length > 40 ? `${op.old_text.slice(0, 40)}...` : op.old_text}
                                    </code>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span className="text-xs text-long">+</span>
                                    <code className="text-xs font-mono text-long/80 truncate">
                                        {op.new_text.length > 40 ? `${op.new_text.slice(0, 40)}...` : op.new_text}
                                    </code>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
};
