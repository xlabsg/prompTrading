import React from "react";
import { useTranslation } from "react-i18next";
import { BarChart2, TrendingUp, TrendingDown, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ActionHandler, ActionCardProps, ActionContext } from "../actionTypes";

export interface MetricsData {
    total_return?: number;
    sharpe_ratio?: number;
    max_drawdown?: number;
    win_rate?: number;
    [key: string]: any;
}

export interface MetricsComparisonParams {
    benchmark?: {
        exchange?: string;
        symbol?: string;
        interval?: string;
    };
    before?: MetricsData;
    after?: MetricsData;
}

export class MetricsComparisonActionHandler implements ActionHandler<MetricsComparisonParams, MetricsComparisonParams> {
    type = "metrics_comparison";

    async execute(_context: ActionContext, params: MetricsComparisonParams): Promise<{ result: MetricsComparisonParams }> {
        return { result: params };
    }

    renderRunning(props: ActionCardProps<MetricsComparisonParams, MetricsComparisonParams>): React.ReactNode {
        return <MetricsComparisonCard payload={props.payload} />;
    }

    renderSuccess(props: ActionCardProps<MetricsComparisonParams, MetricsComparisonParams>): React.ReactNode {
        return <MetricsComparisonCard payload={props.payload} />;
    }

    renderError(_props: ActionCardProps<MetricsComparisonParams, MetricsComparisonParams>): React.ReactNode {
        return null;
    }
}

const MetricsComparisonCard: React.FC<{ payload: any }> = ({ payload }) => {
    const { t } = useTranslation();
    const params: MetricsComparisonParams = payload.params || {};
    const before = params.before;
    const after = params.after;

    if (!after) return null;

    const benchmarkSymbol = params.benchmark?.symbol || "BTC-USDT-SWAP";
    const benchmarkInterval = params.benchmark?.interval || "1h";

    const formatPct = (val?: number) => {
        if (val === undefined || val === null || isNaN(val)) return "N/A";
        const pct = val * 100;
        return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
    };

    const formatNum = (val?: number) => {
        if (val === undefined || val === null || isNaN(val)) return "N/A";
        return val.toFixed(2);
    };

    const items = [
        {
            label: t("metricsComparison.totalReturn", { defaultValue: "Total Return" }),
            afterVal: formatPct(after.total_return),
            beforeVal: before?.total_return !== undefined ? formatPct(before.total_return) : null,
            delta: before?.total_return !== undefined && after.total_return !== undefined
                ? (after.total_return - before.total_return) * 100
                : null,
            isPct: true,
            higherIsBetter: true,
        },
        {
            label: t("metricsComparison.sharpeRatio", { defaultValue: "Sharpe Ratio" }),
            afterVal: formatNum(after.sharpe_ratio),
            beforeVal: before?.sharpe_ratio !== undefined ? formatNum(before.sharpe_ratio) : null,
            delta: before?.sharpe_ratio !== undefined && after.sharpe_ratio !== undefined
                ? after.sharpe_ratio - before.sharpe_ratio
                : null,
            isPct: false,
            higherIsBetter: true,
        },
        {
            label: t("metricsComparison.maxDrawdown", { defaultValue: "Max Drawdown" }),
            afterVal: formatPct(after.max_drawdown ? -Math.abs(after.max_drawdown) : 0),
            beforeVal: before?.max_drawdown !== undefined ? formatPct(-Math.abs(before.max_drawdown)) : null,
            delta: before?.max_drawdown !== undefined && after.max_drawdown !== undefined
                ? Math.abs(after.max_drawdown) - Math.abs(before.max_drawdown)
                : null,
            isPct: true,
            higherIsBetter: false,
        },
        {
            label: t("metricsComparison.winRate", { defaultValue: "Win Rate" }),
            afterVal: formatPct(after.win_rate),
            beforeVal: before?.win_rate !== undefined ? formatPct(before.win_rate) : null,
            delta: before?.win_rate !== undefined && after.win_rate !== undefined
                ? (after.win_rate - before.win_rate) * 100
                : null,
            isPct: true,
            higherIsBetter: true,
        },
    ];

    const hasAnyImprovement = items.some((i) => i.delta !== null && (i.higherIsBetter ? i.delta > 0 : i.delta < 0));

    return (
        <Card className="my-2 border-border/80 bg-card/90 backdrop-blur-sm shadow-sm overflow-hidden">
            <div className="bg-muted/40 px-3.5 py-2.5 border-b border-border/50 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-primary" />
                    <span className="text-xs font-semibold text-foreground">
                        {t("metricsComparison.title", {
                            symbol: benchmarkSymbol,
                            interval: benchmarkInterval,
                            defaultValue: `Backtest Evaluation (${benchmarkSymbol} ${benchmarkInterval})`,
                        })}
                    </span>
                </div>
                {before && (
                    <Badge
                        variant="secondary"
                        className={`text-[10px] px-1.5 py-0 flex items-center gap-1 ${
                            hasAnyImprovement ? "text-green-500 bg-green-500/10" : "text-amber-500 bg-amber-500/10"
                        }`}
                    >
                        {hasAnyImprovement ? (
                            <>
                                <TrendingUp className="w-3 h-3" />
                                <span>{t("metricsComparison.improved", { defaultValue: "Improved" })}</span>
                            </>
                        ) : (
                            <>
                                <TrendingDown className="w-3 h-3" />
                                <span>{t("metricsComparison.declined", { defaultValue: "Changed" })}</span>
                            </>
                        )}
                    </Badge>
                )}
            </div>
            <CardContent className="p-3 grid grid-cols-2 gap-2 text-xs">
                {items.map((item, idx) => {
                    const isImproved = item.delta !== null && (item.higherIsBetter ? item.delta > 0 : item.delta < 0);
                    const isDegraded = item.delta !== null && (item.higherIsBetter ? item.delta < 0 : item.delta > 0);

                    return (
                        <div key={idx} className="p-2 rounded-md bg-muted/20 border border-border/40 space-y-1">
                            <div className="text-[11px] text-muted-foreground">{item.label}</div>
                            <div className="flex items-baseline gap-1.5 flex-wrap">
                                <span className="font-semibold text-foreground text-sm">{item.afterVal}</span>
                                {item.beforeVal && (
                                    <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                                        <span>({item.beforeVal}</span>
                                        <ArrowRight className="w-2.5 h-2.5 inline" />
                                        <span
                                            className={
                                                isImproved
                                                    ? "text-green-500 font-medium"
                                                    : isDegraded
                                                    ? "text-red-500 font-medium"
                                                    : ""
                                            }
                                        >
                                            {item.afterVal})
                                        </span>
                                    </span>
                                )}
                            </div>
                        </div>
                    );
                })}
            </CardContent>
        </Card>
    );
};
