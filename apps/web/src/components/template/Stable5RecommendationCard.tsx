import { Star, Tag, Bell, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Stable5RecommendationItem } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface Stable5RecommendationCardProps {
    item: Stable5RecommendationItem;
    onOpenDetail: (templateId: string) => void;
    onSubscribeSignal: (item: Stable5RecommendationItem) => void;
    onViewPerformance: (item: Stable5RecommendationItem) => void;
}

const templateTypeColors: Record<string, string> = {
    builtin: "bg-blue-500/10 text-blue-500",
    tradingview: "bg-purple-500/10 text-purple-500",
    community: "bg-green-500/10 text-green-500",
};

function toNumber(value: unknown): number | null {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
        const n = Number(value);
        if (Number.isFinite(n)) return n;
    }
    return null;
}

export function Stable5RecommendationCard({ item, onOpenDetail, onSubscribeSignal, onViewPerformance }: Stable5RecommendationCardProps) {
    const { t } = useTranslation();
    const stable5 = item.stable5 as Record<string, unknown>;
    const worst = (stable5?.worst as Record<string, unknown>) || {};
    const maxDd = toNumber(worst.max_drawdown_pct);
    const minRet = toNumber(worst.min_return_pct);
    const score = toNumber(stable5?.score);
    const qualifies = Boolean((stable5 as Record<string, unknown>)?.qualifies);
    const templateTypeLabels: Record<string, string> = {
        builtin: t("templates.filters.builtin"),
        tradingview: t("templates.filters.tradingview"),
        community: t("templates.filters.community"),
    };

    return (
        <div
            role="button"
            tabIndex={0}
            onClick={() => onOpenDetail(item.id)}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onOpenDetail(item.id);
                }
            }}
            className="group bg-card border border-border rounded-xl p-5 transition-all duration-200 cursor-pointer hover:border-primary/40"
        >
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                        <span
                            className={cn(
                                "text-xs font-medium px-2 py-0.5 rounded-full",
                                templateTypeColors[item.template_type] || "bg-gray-500/10 text-gray-500"
                            )}
                        >
                            {templateTypeLabels[item.template_type] || item.template_type}
                        </span>
                        {item.is_featured && (
                            <span className="flex items-center gap-1 text-xs text-amber-500">
                                <Star size={12} fill="currentColor" />
                                {t("templates.featured")}
                            </span>
                        )}
                        {qualifies ? (
                            <span className="ml-auto text-xs font-medium text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                                Stable5
                            </span>
                        ) : (
                            <span className="ml-auto text-xs font-medium text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded-full">
                                {t("templates.candidate")}
                            </span>
                        )}
                    </div>

                    <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-lg truncate group-hover:text-primary transition-colors">
                            {item.name}
                        </h3>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                onViewPerformance(item);
                            }}
                            className="flex-shrink-0 p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
                            title={t("templates.viewPerformance")}
                        >
                            <BarChart3 size={16} />
                        </button>
                    </div>

                    {item.description && (
                        <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                            {item.description}
                        </p>
                    )}

                    <div className="flex flex-wrap gap-1 mb-3">
                        {item.tags?.slice(0, 3).map((tag) => (
                            <span
                                key={tag}
                                className="flex items-center gap-1 text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded"
                            >
                                <Tag size={10} />
                                {tag}
                            </span>
                        ))}
                    </div>

                    <div className="flex items-center gap-4 text-xs text-muted-foreground mb-4">
                        <span className="text-foreground/90">
                            {maxDd !== null ? `${t("templates.mdd")} ${maxDd.toFixed(2)}%` : `${t("templates.mdd")} -`}
                        </span>
                        <span className="text-foreground/90">
                            {minRet !== null ? `${t("templates.minRet")} ${minRet.toFixed(2)}%` : `${t("templates.minRet")} -`}
                        </span>
                        <span className="text-muted-foreground">
                            {score !== null ? `${t("templates.score")} ${score.toFixed(3)}` : `${t("templates.score")} -`}
                        </span>
                    </div>

                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onSubscribeSignal(item);
                        }}
                        className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary bg-primary text-primary-foreground hover:bg-primary/90 transition-colors text-xs font-medium"
                    >
                        <Bell size={12} />
                        {t("templates.subscribeSignals")}
                    </button>
                </div>

            </div>
        </div>
    );
}

export default Stable5RecommendationCard;
