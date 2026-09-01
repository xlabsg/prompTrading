import { Star, Users, Tag, Bell, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TemplateListItem } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface TemplateCardProps {
    template: TemplateListItem;
    onOpenDetail: (templateId: string) => void;
    onSubscribeSignal: (template: TemplateListItem) => void;
    onViewPerformance: (template: TemplateListItem) => void;
}

const templateTypeColors: Record<string, string> = {
    builtin: "bg-blue-500/10 text-blue-500",
    tradingview: "bg-purple-500/10 text-purple-500",
    community: "bg-green-500/10 text-green-500",
};

export function TemplateCard({ template, onOpenDetail, onSubscribeSignal, onViewPerformance }: TemplateCardProps) {
    const { t } = useTranslation();
    const templateTypeLabels: Record<string, string> = {
        builtin: t("templates.filters.builtin"),
        tradingview: t("templates.filters.tradingview"),
        community: t("templates.filters.community"),
    };
    return (
        <div
            role="button"
            tabIndex={0}
            onClick={() => onOpenDetail(template.id)}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onOpenDetail(template.id);
                }
            }}
            className="group bg-card border border-border rounded-xl p-4 transition-all duration-200 cursor-pointer hover:border-primary/40 sm:p-5"
        >
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                        <span className={cn(
                            "text-xs font-medium px-2 py-0.5 rounded-full",
                            templateTypeColors[template.template_type] || "bg-gray-500/10 text-gray-500"
                        )}>
                            {templateTypeLabels[template.template_type] || template.template_type}
                        </span>
                        {template.is_featured && (
                            <span className="flex items-center gap-1 text-xs text-amber-500">
                                <Star size={12} fill="currentColor" />
                                {t("templates.featured")}
                            </span>
                        )}
                    </div>

                    <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-base truncate group-hover:text-primary transition-colors sm:text-lg">
                            {template.name}
                        </h3>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                onViewPerformance(template);
                            }}
                            className="flex-shrink-0 p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
                            title={t("templates.viewPerformance")}
                        >
                            <BarChart3 size={16} />
                        </button>
                    </div>

                    {template.description && (
                        <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                            {template.description}
                        </p>
                    )}

                    <div className="flex flex-wrap gap-1 mb-3">
                        {template.tags?.slice(0, 3).map((tag) => (
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
                        {template.author && (
                            <span>{t("templates.byAuthor", { author: template.author })}</span>
                        )}
                        <span className="flex items-center gap-1">
                            <Users size={12} />
                            {t("templates.subscribers", { count: template.subscriber_count })}
                        </span>
                    </div>

                    {/* Action Buttons */}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onSubscribeSignal(template);
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
