import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { templatesApi } from "@/lib/api";
import type { TemplatePerformanceRunDetailResponse } from "@/lib/types";
import { ResponsiveContainer, Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";

function toNumber(value: unknown): number | null {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
        const n = Number(value);
        if (Number.isFinite(n)) return n;
    }
    return null;
}

export function TemplateBacktestRunDialog({
    runId,
    open,
    onOpenChange,
}: {
    runId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}) {
    const { t, i18n } = useTranslation();
    const runQuery = useQuery<TemplatePerformanceRunDetailResponse>({
        queryKey: ["template-performance-run", runId],
        queryFn: () => templatesApi.getPerformanceRunDetail(runId!),
        enabled: Boolean(runId) && open,
        refetchOnWindowFocus: false,
        retry: false,
    });

    const chartData = useMemo(() => {
        const metrics = runQuery.data?.metrics ?? {};
        const curve = metrics["equity_curve"];
        if (!Array.isArray(curve)) return [];
        return curve
            .map((pt) => {
                if (!Array.isArray(pt) || pt.length < 2) return null;
                const ts = toNumber(pt[0]);
                const equity = toNumber(pt[1]);
                if (ts == null || equity == null) return null;
                return { timestamp: ts, equity };
            })
            .filter((x): x is { timestamp: number; equity: number } => Boolean(x));
    }, [runQuery.data]);

    const trades = useMemo(() => {
        const metrics = runQuery.data?.metrics ?? {};
        const list = metrics["trades"];
        if (!Array.isArray(list)) return [];
        return list.slice(-200).filter((t) => typeof t === "object" && t !== null) as Array<Record<string, unknown>>;
    }, [runQuery.data]);

    const formatPercent = (value: number | null | undefined) => {
        if (value == null || !Number.isFinite(value)) return t("common.notAvailable");
        return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
    };
    const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";

    const title = runQuery.data
        ? `${runQuery.data.exchange.toUpperCase()} · ${runQuery.data.symbol} · ${runQuery.data.interval}`
        : t("templateRun.titleFallback");

    const metrics = (runQuery.data?.metrics ?? {}) as Record<string, unknown>;
    const totalReturn = toNumber(metrics["total_return"]);
    const maxDrawdown = toNumber(metrics["max_drawdown"]);
    const sharpe = toNumber(metrics["sharpe_ratio"]);
    const winRate = toNumber(metrics["win_rate"]);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-3">
                        <span>{title}</span>
                        {typeof totalReturn === "number" && (
                            <Badge variant={totalReturn >= 0 ? "default" : "destructive"}>
                                {formatPercent(totalReturn)}
                            </Badge>
                        )}
                    </DialogTitle>
                </DialogHeader>

                {runQuery.isLoading ? (
                    <div className="flex items-center justify-center h-48">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                    </div>
                ) : runQuery.error ? (
                    <div className="text-sm text-destructive">
                        {runQuery.error instanceof Error ? runQuery.error.message : t("templateRun.errors.load")}
                    </div>
                ) : !runQuery.data ? (
                    <div className="text-sm text-muted-foreground">{t("templateRun.empty.run")}</div>
                ) : (
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="text-xs text-muted-foreground">{t("templateRun.metrics.totalReturn")}</div>
                                    <div className="text-xl font-semibold">{formatPercent(totalReturn)}</div>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="text-xs text-muted-foreground">{t("templateRun.metrics.maxDrawdown")}</div>
                                    <div className="text-xl font-semibold">{formatPercent(maxDrawdown)}</div>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="text-xs text-muted-foreground">{t("templateRun.metrics.sharpe")}</div>
                                    <div className="text-xl font-semibold">
                                        {sharpe == null ? t("common.notAvailable") : sharpe.toFixed(2)}
                                    </div>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="text-xs text-muted-foreground">{t("templateRun.metrics.winRate")}</div>
                                    <div className="text-xl font-semibold">
                                        {winRate == null ? t("common.notAvailable") : `${winRate.toFixed(1)}%`}
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {chartData.length > 0 ? (
                            <Card>
                                <CardContent className="p-4">
                                    <div className="text-sm font-medium mb-3">{t("templateRun.equityCurve")}</div>
                                    <div className="h-64">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" />
                                                <XAxis
                                                    dataKey="timestamp"
                                                    tickFormatter={(ts) => new Date(ts).toLocaleDateString(locale)}
                                                    minTickGap={36}
                                                />
                                                <YAxis domain={["auto", "auto"]} />
                                                <Tooltip
                                                    labelFormatter={(ts) => new Date(Number(ts)).toLocaleString(locale)}
                                                    formatter={(v) => [`${Number(v).toFixed(2)}`, t("templateRun.equityLegend")]}
                                                />
                                                <Area type="monotone" dataKey="equity" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.2} />
                                            </AreaChart>
                                        </ResponsiveContainer>
                                    </div>
                                </CardContent>
                            </Card>
                        ) : (
                            <div className="text-sm text-muted-foreground">
                                {t("templateRun.empty.equity")}
                            </div>
                        )}

                        <Card>
                            <CardContent className="p-4">
                                <div className="text-sm font-medium mb-3">{t("templateRun.trades.title")}</div>
                                {trades.length === 0 ? (
                                    <div className="text-sm text-muted-foreground">{t("templateRun.trades.empty")}</div>
                                ) : (
                                    <div className="overflow-auto">
                                        <table className="w-full text-sm">
                                            <thead className="text-xs text-muted-foreground">
                                                <tr className="border-b border-border">
                                                    <th className="text-left py-2 pr-2">{t("templateRun.trades.columns.side")}</th>
                                                    <th className="text-left py-2 pr-2">{t("templateRun.trades.columns.entry")}</th>
                                                    <th className="text-left py-2 pr-2">{t("templateRun.trades.columns.exit")}</th>
                                                    <th className="text-right py-2 pl-2">{t("templateRun.trades.columns.return")}</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {trades.map((t, i) => {
                                                    const side = String(t["side"] ?? "");
                                                    const entry = toNumber(t["entry_time_ms"]);
                                                    const exit = toNumber(t["exit_time_ms"]);
                                                    const ret = toNumber(t["return_pct"]);
                                                    return (
                                                        <tr key={i} className="border-b border-border/50">
                                                            <td className="py-2 pr-2">{side}</td>
                                                            <td className="py-2 pr-2">
                                                                {entry == null ? "-" : new Date(entry).toLocaleString(locale)}
                                                            </td>
                                                            <td className="py-2 pr-2">
                                                                {exit == null ? "-" : new Date(exit).toLocaleString(locale)}
                                                            </td>
                                                            <td className="py-2 pl-2 text-right">
                                                                {ret == null ? "-" : `${ret.toFixed(2)}%`}
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                                {trades.length > 0 && (
                                    <div className="mt-2 text-xs text-muted-foreground">
                                        {t("templateRun.trades.showing", { count: Math.min(200, trades.length) })}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

export default TemplateBacktestRunDialog;
