import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
    TrendingUp,
    TrendingDown,
    BarChart3,
    Activity,
    Signal,
    Target,
    type LucideIcon,
} from "lucide-react";
import { templatesApi } from "@/lib/api";
import type { TemplateDetail, TemplatePerformanceResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface TemplatePerformanceDialogProps {
    template: TemplateDetail | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function TemplatePerformanceDialog({
    template,
    open,
    onOpenChange,
}: TemplatePerformanceDialogProps) {
    const [activeTab, setActiveTab] = useState("overview");
    const { t, i18n } = useTranslation();

    const { data: performance, isLoading, error } = useQuery<TemplatePerformanceResponse>({
        queryKey: ["template-performance", template?.id],
        queryFn: () => templatesApi.getPerformance(template!.id),
        enabled: !!template && open,
        refetchOnWindowFocus: false,
    });

    if (!template) return null;

    const metrics = performance?.aggregated_metrics;

    const formatMetric = (value: number | null | undefined, decimals = 2) =>
        value == null ? t("common.notAvailable") : value.toFixed(decimals);
    const formatPercent = (value: number | null | undefined) =>
        value == null ? t("common.notAvailable") : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
    const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <BarChart3 size={20} />
                        {t("templatePerformance.title", { name: template.name })}
                    </DialogTitle>
                    <DialogDescription>
                        {t("templatePerformance.subtitle")}
                    </DialogDescription>
                </DialogHeader>

                {isLoading ? (
                    <div className="flex items-center justify-center h-64">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                    </div>
                ) : error ? (
                    <div className="text-center py-8 text-destructive">
                        <div className="text-lg font-medium mb-2">{t("templatePerformance.errors.load")}</div>
                        <div className="text-sm text-muted-foreground">
                            {error instanceof Error ? error.message : t("templatePerformance.errors.unknown")}
                        </div>
                    </div>
                ) : !performance ? (
                    <div className="text-center py-8 text-muted-foreground">
                        {t("templatePerformance.empty.performance")}
                    </div>
                ) : !metrics ? (
                    <div className="text-center py-8 text-muted-foreground">
                        {t("templatePerformance.empty.metrics")}
                    </div>
                ) : (
                    <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                        <TabsList className="grid w-full grid-cols-3">
                            <TabsTrigger value="overview">{t("templatePerformance.tabs.overview")}</TabsTrigger>
                            <TabsTrigger value="backtests">{t("templatePerformance.tabs.backtests")}</TabsTrigger>
                            <TabsTrigger value="signals">{t("templatePerformance.tabs.signals")}</TabsTrigger>
                        </TabsList>

                        {/* Overview Tab */}
                        <TabsContent value="overview" className="mt-4 space-y-4">
                            {/* Key Metrics Grid */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <MetricCard
                                    label={t("templatePerformance.metrics.totalReturn")}
                                    value={formatPercent(metrics.total_return)}
                                    icon={TrendingUp}
                                    trend={metrics.total_return && metrics.total_return > 0 ? "up" : "down"}
                                />
                                <MetricCard
                                    label={t("templatePerformance.metrics.sharpeRatio")}
                                    value={formatMetric(metrics.sharpe_ratio)}
                                    icon={Activity}
                                />
                                <MetricCard
                                    label={t("templatePerformance.metrics.maxDrawdown")}
                                    value={formatPercent(metrics.max_drawdown)}
                                    icon={TrendingDown}
                                    trend="down"
                                />
                                <MetricCard
                                    label={t("templatePerformance.metrics.winRate")}
                                    value={`${formatMetric(metrics.win_rate, 1)}%`}
                                    icon={Target}
                                />
                            </div>

                            {/* Additional Metrics */}
                            <div className="grid grid-cols-3 gap-4">
                                <Card>
                                    <CardContent className="pt-4">
                                        <div className="text-sm text-muted-foreground mb-1">
                                            {t("templatePerformance.metrics.totalTrades")}
                                        </div>
                                        <div className="text-2xl font-bold">
                                            {metrics.total_trades ?? t("common.notAvailable")}
                                        </div>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardContent className="pt-4">
                                        <div className="text-sm text-muted-foreground mb-1">
                                            {t("templatePerformance.metrics.profitFactor")}
                                        </div>
                                        <div className="text-2xl font-bold">
                                            {formatMetric(metrics.profit_factor)}
                                        </div>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardContent className="pt-4">
                                        <div className="text-sm text-muted-foreground mb-1">
                                            {t("templatePerformance.metrics.avgTradePnl")}
                                        </div>
                                        <div className="text-2xl font-bold">
                                            ${formatMetric(metrics.avg_trade_pnl)}
                                        </div>
                                    </CardContent>
                                </Card>
                            </div>

                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-base">
                                        <Signal size={16} className="inline mr-2" />
                                        {t("templatePerformance.summary.title")}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">{t("templatePerformance.summary.backtests")}:</span>
                                        <span className="font-medium">{performance.backtest_runs.length}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">{t("templatePerformance.summary.signals")}:</span>
                                        <span className="font-medium">{performance.total_signals}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">{t("templatePerformance.summary.recentSignals")}:</span>
                                        <span className="font-medium">{performance.recent_signals.length}</span>
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* Backtests Tab */}
                        <TabsContent value="backtests" className="mt-4 space-y-2 max-h-[60vh] overflow-y-auto">
                            {performance.backtest_runs.map((run) => (
                                <Card key={run.id}>
                                    <CardContent className="p-4">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-4">
                                                <div>
                                                    <div className="text-sm font-medium">
                                                        {new Date(run.run_date).toLocaleDateString(locale)}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {run.exchange} · {run.symbol}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-4 text-sm">
                                                <Badge
                                                    variant={run.total_return != null && run.total_return >= 0 ? "default" : "destructive"}
                                                >
                                                    {formatPercent(run.total_return)}
                                                </Badge>
                                                <span className="text-muted-foreground">
                                                    {t("templatePerformance.metrics.sharpeShort")}: {formatMetric(run.sharpe_ratio)}
                                                </span>
                                                <span className="text-muted-foreground">
                                                    {t("templatePerformance.metrics.winRate")}: {formatMetric(run.win_rate, 1)}%
                                                </span>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                        </TabsContent>

                        {/* Signals Tab */}
                        <TabsContent value="signals" className="mt-4 space-y-2 max-h-[60vh] overflow-y-auto">
                            {performance.recent_signals.map((signal) => (
                                <Card key={signal.id}>
                                    <CardContent className="p-4">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <Signal
                                                    size={16}
                                                    className={cn(
                                                        signal.side === "buy"
                                                            ? "text-green-500"
                                                            : "text-red-500"
                                                    )}
                                                />
                                                <div>
                                                    <div className="text-sm font-medium">
                                                        {signal.symbol} · {signal.side.toUpperCase()}
                                                    </div>
                                            <div className="text-xs text-muted-foreground">
                                                {new Date(signal.created_at).toLocaleString(locale)}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4 text-sm">
                                        <span className="text-muted-foreground">
                                            ${formatMetric(signal.price)}
                                                </span>
                                                {signal.pnl != null && (
                                                    <Badge
                                                        variant={signal.pnl >= 0 ? "default" : "destructive"}
                                                    >
                                                        {formatPercent(signal.pnl)}
                                                    </Badge>
                                        )}
                                        <span className="text-muted-foreground">
                                            {t("templatePerformance.confidence")}: {formatMetric(signal.confidence * 100, 0)}%
                                        </span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                    <div className="text-center text-sm text-muted-foreground py-4">
                        {t("templatePerformance.signalsCount", { shown: performance.recent_signals.length, total: performance.total_signals })}
                    </div>
                </TabsContent>
            </Tabs>
                )}
            </DialogContent>
        </Dialog>
    );
}

// Helper Component
interface MetricCardProps {
    label: string;
    value: string;
    icon: LucideIcon;
    trend?: "up" | "down";
}

function MetricCard({ label, value, icon: Icon, trend }: MetricCardProps) {
    return (
        <Card>
            <CardContent className="pt-4">
                <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-muted-foreground">{label}</span>
                    <Icon size={16} className="text-muted-foreground" />
                </div>
                <div
                    className={cn(
                        "text-2xl font-bold",
                        trend === "up" && "text-green-500",
                        trend === "down" && "text-red-500"
                    )}
                >
                    {value}
                </div>
            </CardContent>
        </Card>
    );
}
