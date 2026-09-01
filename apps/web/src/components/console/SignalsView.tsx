import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
    Radio,
    TrendingUp,
    Clock,
    Search,
    ArrowUpRight,
    ArrowDownRight,
    CheckCircle2,
    RefreshCw,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { signalsApi, tradesApi } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface SignalsViewProps {
    strategy: Strategy | null;
}

const SignalsView = ({ strategy }: SignalsViewProps) => {
    const [activeTab, setActiveTab] = useState("signals");
    const [signalFilter, setSignalFilter] = useState("all");
    const [searchQuery, setSearchQuery] = useState("");
    const { t, i18n } = useTranslation();

    const formatTime = (value: string) => {
        const date = new Date(value);
        const now = new Date();
        const diff = now.getTime() - date.getTime();
        const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";
        const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
        if (diff < 3600000) return rtf.format(-Math.floor(diff / 60000), "minute");
        if (diff < 86400000) return rtf.format(-Math.floor(diff / 3600000), "hour");
        return date.toLocaleDateString(locale);
    };

    const { data: signals = [], refetch: refetchSignals } = useQuery({
        queryKey: ["signals", strategy?.id],
        queryFn: () => (strategy ? signalsApi.list(strategy.id) : Promise.resolve([])),
        enabled: !!strategy,
    });

    const { data: trades = [], refetch: refetchTrades } = useQuery({
        queryKey: ["trades", strategy?.id],
        queryFn: () => (strategy ? tradesApi.list(strategy.id) : Promise.resolve([])),
        enabled: !!strategy,
    });

    const filteredSignals = useMemo(() => {
        return signals.filter((signal) => {
            if (signalFilter !== "all" && signal.status !== signalFilter) return false;
            if (searchQuery && !signal.symbol.toLowerCase().includes(searchQuery.toLowerCase())) return false;
            return true;
        });
    }, [signals, signalFilter, searchQuery]);

    const stats = useMemo(() => {
        const closedTrades = trades.filter((trade) => trade.status === "closed");
        const wins = closedTrades.filter((trade) => (trade.pnl || 0) > 0).length;
        const totalPnl = trades.reduce((acc, trade) => acc + (trade.pnl || 0), 0);
        const winRate = closedTrades.length ? (wins / closedTrades.length) * 100 : 0;
        return {
            totalTrades: trades.length,
            openPositions: trades.filter((trade) => trade.status === "open").length,
            totalPnl,
            winRate,
        };
    }, [trades]);

    if (!strategy) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                {t("signalsView.selectStrategy")}
            </div>
        );
    }

    return (
        <div className="h-full min-h-0 flex flex-col bg-background overflow-hidden">
            <div className="shrink-0 p-4 border-b border-border bg-card/50">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                            <Radio className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-foreground">{t("signalsView.title")}</h1>
                            <p className="text-sm text-muted-foreground">{t("signalsView.subtitle")}</p>
                        </div>
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                            refetchSignals();
                            refetchTrades();
                        }}
                    >
                        <RefreshCw className="mr-2 h-4 w-4" />
                        {t("signalsView.refresh")}
                    </Button>
                </div>

                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList className="bg-muted/50">
                        <TabsTrigger value="signals" className="gap-2">
                            <Radio size={14} />
                            {t("signalsView.tabs.signals")}
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                                {signals.filter((signal) => signal.status === "pending").length}
                            </Badge>
                        </TabsTrigger>
                        <TabsTrigger value="trades" className="gap-2">
                            <TrendingUp size={14} />
                            {t("signalsView.tabs.trades")}
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                                {trades.filter((trade) => trade.status === "open").length}
                            </Badge>
                        </TabsTrigger>
                    </TabsList>
                </Tabs>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden">
                <div className="h-full overflow-y-auto p-4">
                    {activeTab === "signals" && (
                        <div className="space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="relative flex-1 max-w-xs">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                    <Input
                                        placeholder={t("signalsView.searchPlaceholder")}
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                        className="pl-10"
                                    />
                                </div>
                                <Select value={signalFilter} onValueChange={setSignalFilter}>
                                    <SelectTrigger className="w-36">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="all">{t("signalsView.status.all")}</SelectItem>
                                        <SelectItem value="pending">{t("signalsView.status.pending")}</SelectItem>
                                        <SelectItem value="executed">{t("signalsView.status.executed")}</SelectItem>
                                        <SelectItem value="cancelled">{t("signalsView.status.cancelled")}</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-3">
                                {filteredSignals.map((signal, index) => (
                                    <motion.div
                                        key={signal.id}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: index * 0.05 }}
                                        className="p-4 rounded-xl bg-card border border-border hover:shadow-md transition-shadow"
                                    >
                                        <div className="flex items-start justify-between">
                                            <div className="flex items-center gap-4">
                                                <div className={cn(
                                                    "w-10 h-10 rounded-lg flex items-center justify-center",
                                                    signal.side === "buy" ? "bg-green-500/10" : "bg-red-500/10"
                                                )}>
                                                    {signal.side === "buy" ? (
                                                        <ArrowUpRight className="w-5 h-5 text-green-500" />
                                                    ) : (
                                                        <ArrowDownRight className="w-5 h-5 text-red-500" />
                                                    )}
                                                </div>
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-semibold text-foreground">{signal.symbol}</span>
                                                        {signal.interval && (
                                                            <Badge variant="secondary" className="ml-2 text-xs">
                                                                {signal.interval}
                                                            </Badge>
                                                        )}
                                                        <Badge variant={signal.side === "buy" ? "default" : "destructive"} className="uppercase text-xs">
                                                            {signal.side}
                                                        </Badge>
                                                    </div>
                                                    <div className="text-sm text-muted-foreground mt-1">
                                                        @ ${signal.price.toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="text-right">
                                                <div className={cn(
                                                    "inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium",
                                                    signal.status === "pending" && "bg-yellow-500/10 text-yellow-600",
                                                    signal.status === "executed" && "bg-green-500/10 text-green-600",
                                                    signal.status === "cancelled" && "bg-muted text-muted-foreground",
                                                    signal.status === "expired" && "bg-muted text-muted-foreground"
                                                )}>
                                                    {signal.status === "executed" && <CheckCircle2 size={12} />}
                                                    {signal.status === "pending" && <Clock size={12} />}
                                                    <span className="capitalize">
                                                        {t(`signalsView.status.${signal.status}`, { defaultValue: signal.status })}
                                                    </span>
                                                </div>
                                                <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1 justify-end">
                                                    <Clock size={10} />
                                                    {formatTime(signal.created_at)}
                                                </div>
                                            </div>
                                        </div>

                                        <div className="mt-3 pt-3 border-t border-border flex items-center justify-between">
                                            <div className="text-sm text-muted-foreground">
                                                <div>{signal.reason || "-"}</div>
                                                {(signal.target != null || signal.price_source) && (
                                                    <div className="mt-1 text-xs text-muted-foreground">
                                                        {signal.target != null && <span>{t("signalsView.target")}: {signal.target.toFixed(2)}</span>}
                                                        {signal.price_source && (
                                                            <span className={signal.target != null ? "ml-3" : ""}>
                                                                {t("signalsView.price")}: {signal.price_source}
                                                            </span>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs text-muted-foreground">{t("signalsView.confidence")}</span>
                                                <div className="flex items-center gap-1">
                                                    <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                                                        <div
                                                            className={cn(
                                                                "h-full rounded-full",
                                                                signal.confidence >= 0.8 ? "bg-green-500" :
                                                                    signal.confidence >= 0.6 ? "bg-yellow-500" : "bg-red-500"
                                                            )}
                                                            style={{ width: `${Math.min(100, Math.max(0, signal.confidence * 100))}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-xs font-medium">{(signal.confidence * 100).toFixed(0)}%</span>
                                                </div>
                                            </div>
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        </div>
                    )}

                    {activeTab === "trades" && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-4 gap-4">
                                {[
                                    { label: t("signalsView.stats.totalTrades"), value: stats.totalTrades, color: "text-foreground" },
                                    { label: t("signalsView.stats.openPositions"), value: stats.openPositions, color: "text-blue-500" },
                                    { label: t("signalsView.stats.totalPnl"), value: `${stats.totalPnl >= 0 ? "+" : "-"}$${Math.abs(stats.totalPnl).toFixed(2)}`, color: stats.totalPnl >= 0 ? "text-green-500" : "text-red-500" },
                                    { label: t("signalsView.stats.winRate"), value: `${stats.winRate.toFixed(0)}%`, color: "text-primary" },
                                ].map((stat) => (
                                    <div key={stat.label} className="p-4 rounded-xl bg-card border border-border">
                                        <div className="text-sm text-muted-foreground">{stat.label}</div>
                                        <div className={cn("text-2xl font-bold", stat.color)}>{stat.value}</div>
                                    </div>
                                ))}
                            </div>

                            <div className="rounded-xl border border-border overflow-hidden">
                                <table className="w-full">
                                    <thead className="bg-muted/50">
                                        <tr>
                                            <th className="text-left p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.time")}</th>
                                            <th className="text-left p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.symbol")}</th>
                                            <th className="text-left p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.side")}</th>
                                            <th className="text-right p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.entry")}</th>
                                            <th className="text-right p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.exit")}</th>
                                            <th className="text-right p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.qty")}</th>
                                            <th className="text-right p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.pnl")}</th>
                                            <th className="text-center p-3 text-sm font-medium text-muted-foreground">{t("signalsView.table.status")}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {trades.map((trade) => (
                                            <tr key={trade.id} className="border-t border-border hover:bg-muted/30">
                                                <td className="p-3 text-sm text-muted-foreground">
                                                    {formatTime(trade.created_at)}
                                                </td>
                                                <td className="p-3 font-medium">{trade.symbol}</td>
                                                <td className="p-3">
                                                    <Badge variant={trade.side === "buy" ? "default" : "destructive"} className="uppercase text-xs">
                                                        {trade.side}
                                                    </Badge>
                                                </td>
                                                <td className="p-3 text-right font-mono">${trade.entry_price.toLocaleString()}</td>
                                                <td className="p-3 text-right font-mono text-muted-foreground">
                                                    {trade.exit_price ? `$${trade.exit_price.toLocaleString()}` : "-"}
                                                </td>
                                                <td className="p-3 text-right">{trade.quantity}</td>
                                                <td className={cn(
                                                    "p-3 text-right font-medium",
                                                    trade.pnl === undefined ? "text-muted-foreground" :
                                                        trade.pnl >= 0 ? "text-green-500" : "text-red-500"
                                                )}>
                                                    {trade.pnl !== undefined ? (
                                                        trade.pnl >= 0 ? `+$${trade.pnl.toFixed(2)}` : `-$${Math.abs(trade.pnl).toFixed(2)}`
                                                    ) : "-"}
                                                </td>
                                                <td className="p-3 text-center">
                                                    <span className={cn(
                                                        "inline-flex px-2 py-0.5 rounded-full text-xs font-medium",
                                                        trade.status === "open" && "bg-blue-500/10 text-blue-600",
                                                        trade.status === "closed" && "bg-muted text-muted-foreground",
                                                        trade.status === "partial" && "bg-yellow-500/10 text-yellow-600"
                                                    )}>
                                                        {t(`signalsView.tradeStatus.${trade.status}`, { defaultValue: trade.status })}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default SignalsView;
