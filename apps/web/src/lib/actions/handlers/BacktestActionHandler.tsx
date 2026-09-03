import React, { useState, useEffect } from "react";
import { Loader2, Play, CheckCircle2, XCircle, ArrowUpRight, TrendingUp, TrendingDown, RefreshCw, BarChart2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { backtestsApi, jobsApi } from "@/lib/api";
import { ActionHandler, ActionCardProps, ActionContext } from "../actionTypes";
import type { BacktestRun } from "@/lib/types";

export interface BacktestParams {
    symbol?: string;
    range?: string;
    exchange?: string;
    interval?: string;
    initial_cash?: number;
    [key: string]: any;
}

export interface BacktestResult {
    run: BacktestRun;
}

export class BacktestActionHandler implements ActionHandler<BacktestParams, BacktestResult> {
    type = "backtest";

    async execute(context: ActionContext, params: BacktestParams): Promise<{ jobId?: string; result?: BacktestResult }> {
        const strategyId = context.strategy?.id;
        if (!strategyId) {
            throw new Error("No active strategy selected");
        }

        const symbol = params.symbol || "BTC-USDT";
        const exchange = params.exchange || "okx";
        const interval = params.interval || "1h";
        const range = params.range || "30d";

        const now = Date.now();
        let start_ms: number | undefined;
        let end_ms: number = now;

        if (range === "30d") start_ms = now - 30 * 24 * 60 * 60 * 1000;
        else if (range === "60d") start_ms = now - 60 * 24 * 60 * 60 * 1000;
        else if (range === "90d") start_ms = now - 90 * 24 * 60 * 60 * 1000;
        else if (range === "180d") start_ms = now - 180 * 24 * 60 * 60 * 1000;
        else if (range === "1y") start_ms = now - 365 * 24 * 60 * 60 * 1000;
        else start_ms = now - 30 * 24 * 60 * 60 * 1000;

        const response = await backtestsApi.create(strategyId, {
            dataset: {
                exchange,
                symbol,
                interval,
                start_ms,
                end_ms,
            },
            params: {
                initial_cash: params.initial_cash || 10000,
            },
        });

        // Invalidate backtests cache so BacktestView will see the new run
        context.queryClient.invalidateQueries({ queryKey: ["backtests", "strategy", strategyId] });

        return {
            jobId: response.job.id,
            result: response.backtest_run ? { run: response.backtest_run } : undefined,
        };
    }

    async pollCompletion(context: ActionContext, jobId: string, params: BacktestParams): Promise<BacktestResult> {
        const strategyId = context.strategy?.id;
        if (!strategyId) throw new Error("No active strategy");

        // Wait for job completion (polling every 1.5s, max 7 mins)
        const job = await jobsApi.waitForCompletion(jobId, undefined, 1500, 420000);
        context.queryClient.invalidateQueries({ queryKey: ["backtests", "strategy", strategyId] });

        if (job.status !== "succeeded") {
            throw new Error(job.error_message || "回测执行失败");
        }

        // Fetch backtest list to find the latest run
        const runs = await backtestsApi.list(strategyId);
        const matched = runs.find((r) => r.job_id === jobId) || runs[0];
        if (!matched) {
            throw new Error("未能获取回测运行结果");
        }

        return { run: matched };
    }

    renderRunning(props: ActionCardProps<BacktestParams, BacktestResult>): React.ReactNode {
        return <RunningCard {...props} />;
    }

    renderSuccess(props: ActionCardProps<BacktestParams, BacktestResult>): React.ReactNode {
        return <SuccessCard {...props} />;
    }

    renderError(props: ActionCardProps<BacktestParams, BacktestResult>): React.ReactNode {
        return <ErrorCard {...props} />;
    }
}

// Subcomponent: Running State Card
const RunningCard: React.FC<ActionCardProps<BacktestParams, BacktestResult>> = ({ payload }) => {
    const [seconds, setSeconds] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setSeconds(Math.floor((Date.now() - payload.createdAt) / 1000));
        }, 1000);
        return () => clearInterval(interval);
    }, [payload.createdAt]);

    const { symbol = "BTC-USDT", range = "30d", interval = "1h" } = payload.params || {};

    return (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-3.5 text-xs text-foreground shadow-sm space-y-3">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-medium text-primary">
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    <span>策略回测执行中...</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono">{seconds}s</span>
            </div>

            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="px-2 py-0.5 rounded-full bg-background/80 border text-muted-foreground font-mono font-medium">
                    {symbol}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-background/80 border text-muted-foreground font-mono">
                    {interval}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-background/80 border text-muted-foreground font-mono">
                    近 {range}
                </span>
            </div>

            <div className="text-[11px] text-muted-foreground">
                正在加载历史 K 线数据并回放策略信号，请稍候...
            </div>
        </div>
    );
};

// Subcomponent: Succeeded State Card
const SuccessCard: React.FC<ActionCardProps<BacktestParams, BacktestResult>> = ({ payload, context }) => {
    const run = payload.result?.run;
    const metrics = run?.metrics;

    const totalReturn = metrics?.total_return !== undefined ? Number(metrics.total_return) * 100 : null;
    const maxDrawdown = metrics?.max_drawdown !== undefined ? Number(metrics.max_drawdown) * 100 : null;
    const sharpe = metrics?.sharpe_ratio !== undefined ? Number(metrics.sharpe_ratio) : null;
    const winRate = metrics?.win_rate !== undefined ? Number(metrics.win_rate) * 100 : null;
    const tradesCount = metrics?.total_trades !== undefined ? metrics.total_trades : null;

    const isPositive = totalReturn !== null && totalReturn >= 0;

    const handleViewReport = () => {
        if (context.onNavigateView) {
            context.onNavigateView("backtest", run?.id);
        }
    };

    const handleOptimize = () => {
        if (context.onSendMessage) {
            context.onSendMessage(
                `根据当前回测结果（收益率: ${totalReturn !== null ? totalReturn.toFixed(2) + "%" : "N/A"}, 最大回撤: ${maxDrawdown !== null ? maxDrawdown.toFixed(2) + "%" : "N/A"}），请帮我分析不足并优化策略。`
            );
        }
    };

    return (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3.5 text-xs text-foreground shadow-sm space-y-3">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>回测完成</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono">
                    {payload.params?.symbol || "BTC-USDT"} ({payload.params?.range || "30d"})
                </span>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-2 bg-background/60 rounded-lg p-2.5 border">
                <div>
                    <div className="text-[10px] text-muted-foreground">总收益率 (Return)</div>
                    <div className={`text-sm font-semibold font-mono flex items-center gap-0.5 ${isPositive ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                        {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                        {totalReturn !== null ? `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%` : "--"}
                    </div>
                </div>

                <div>
                    <div className="text-[10px] text-muted-foreground">最大回撤 (Max DD)</div>
                    <div className="text-sm font-semibold font-mono text-rose-500">
                        {maxDrawdown !== null ? `-${Math.abs(maxDrawdown).toFixed(2)}%` : "--"}
                    </div>
                </div>

                <div>
                    <div className="text-[10px] text-muted-foreground">夏普比率 (Sharpe)</div>
                    <div className="text-xs font-semibold font-mono">
                        {sharpe !== null ? sharpe.toFixed(2) : "--"}
                    </div>
                </div>

                <div>
                    <div className="text-[10px] text-muted-foreground">胜率 / 交易数</div>
                    <div className="text-xs font-semibold font-mono">
                        {winRate !== null ? `${winRate.toFixed(1)}%` : "--"} / {tradesCount !== null ? `${tradesCount}笔` : "--"}
                    </div>
                </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2 pt-1">
                <Button
                    size="sm"
                    className="flex-1 h-8 gap-1 text-xs"
                    onClick={handleViewReport}
                >
                    <BarChart2 className="w-3.5 h-3.5" />
                    查看回测详细报告
                </Button>
                <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1 text-xs text-muted-foreground hover:text-foreground"
                    onClick={handleOptimize}
                    title="基于此结果向 AI 发起优化讨论"
                >
                    <ArrowUpRight className="w-3.5 h-3.5" />
                    调优
                </Button>
            </div>
        </div>
    );
};

// Subcomponent: Error State Card
const ErrorCard: React.FC<ActionCardProps<BacktestParams, BacktestResult>> = ({ payload, onRetry }) => {
    return (
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3.5 text-xs text-foreground shadow-sm space-y-2">
            <div className="flex items-center gap-1.5 font-medium text-rose-600 dark:text-rose-400">
                <XCircle className="w-4 h-4" />
                <span>回测执行失败</span>
            </div>
            <div className="text-[11px] text-muted-foreground bg-background/60 rounded p-2 border font-mono">
                {payload.error || "未知异常，请检查策略代码或数据接口。"}
            </div>
            {onRetry && (
                <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={onRetry}>
                    <RefreshCw className="w-3 h-3" />
                    重试
                </Button>
            )}
        </div>
    );
};
