import { cn } from "@/lib/utils";

export type ReadoutTone = "neutral" | "long" | "short" | "muted";

export interface ReadoutItem {
    label: string;
    value: string;
    /** Market meaning of the value. Drives colour; never set it for decoration. */
    tone?: ReadoutTone;
    /** Secondary line under the value — a window, a count, a unit. */
    note?: string;
}

const toneClass: Record<ReadoutTone, string> = {
    neutral: "text-foreground",
    long: "text-long",
    short: "text-short",
    muted: "text-muted-foreground",
};

/**
 * A row of headline figures sharing one hairline lattice, the way a fill report
 * or a terminal readout is set — rather than as separate floating cards.
 * Values are monospaced and column-aligned so digits line up across the row.
 */
export const Readout = ({
    items,
    className,
    columns = 4,
}: {
    items: ReadoutItem[];
    className?: string;
    columns?: 2 | 3 | 4;
}) => (
    <dl
        className={cn(
            "grid border-l border-t border-border bg-card",
            columns === 2 && "grid-cols-2",
            columns === 3 && "grid-cols-2 sm:grid-cols-3",
            columns === 4 && "grid-cols-2 lg:grid-cols-4",
            className,
        )}
    >
        {items.map((item) => (
            <div key={item.label} className="border-b border-r border-border px-4 py-3">
                <dt className="text-xs text-muted-foreground">{item.label}</dt>
                <dd className={cn("numeric mt-1 text-xl font-medium", toneClass[item.tone ?? "neutral"])}>
                    {item.value}
                </dd>
                {item.note && <p className="mt-0.5 text-xs text-muted-foreground">{item.note}</p>}
            </div>
        ))}
    </dl>
);

/**
 * Label/value pairs stacked in a column — the long tail of run details that sits
 * under the headline readout.
 */
export const ReadoutList = ({
    items,
    className,
}: {
    items: ReadoutItem[];
    className?: string;
}) => (
    <dl className={cn("divide-y divide-border text-sm", className)}>
        {items.map((item) => (
            <div key={item.label} className="flex items-baseline justify-between gap-4 py-2">
                <dt className="text-muted-foreground">{item.label}</dt>
                <dd className={cn("numeric text-right font-medium", toneClass[item.tone ?? "neutral"])}>
                    {item.value}
                </dd>
            </div>
        ))}
    </dl>
);
