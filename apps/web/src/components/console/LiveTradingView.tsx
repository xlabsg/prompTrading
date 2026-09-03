import { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Strategy } from "@/pages/Console";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Shield,
    Zap,
    Play,
    Square,
    RefreshCw,
    Activity,
    Clock,
    Wallet,
    TrendingUp,
    Settings,
    FileText,
    ArrowUpRight,
    ArrowDownRight,
    Loader2
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { tradingApi, type TradingStatus, type Position, type Order } from "@/lib/api/trading";
import { exchangeAccountsApi, tradingLogsApi, LogEntry } from "@/lib/api";
import ExchangeAccountsDialog from "@/components/console/ExchangeAccountsDialog";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cn } from "@/lib/utils";

interface LiveTradingViewProps {
    strategy: Strategy | null;
    onNavigateToPortfolio?: () => void;
    onNavigateToChat?: (message?: string) => void;
}

export const LiveTradingView = ({ strategy }: LiveTradingViewProps) => {
    const { t } = useTranslation();
    const queryClient = useQueryClient();

    const [selectedMode, setSelectedMode] = useState<"paper" | "live">("paper");
    const [selectedAccountId, setSelectedAccountId] = useState<string>("");
    const [symbol, setSymbol] = useState("BTC-USDT-SWAP");
    const [interval, setInterval] = useState("1m");
    const [maxPositionPct, setMaxPositionPct] = useState("10");
    const [stopLossPct, setStopLossPct] = useState("2");
    const [leverage] = useState("1");
    const [showConfigDrawer, setShowConfigDrawer] = useState(false);
    const [liveLogs, setLiveLogs] = useState<LogEntry[]>([]);

    // Fetch exchange accounts for strategy (paper account is auto-created by API)
    const { data: accounts = [] } = useQuery({
        queryKey: ["exchange-accounts", strategy?.id],
        queryFn: () => strategy?.id ? exchangeAccountsApi.list(strategy.id) : Promise.resolve([]),
        enabled: Boolean(strategy?.id),
    });

    const paperAccount = useMemo(() => accounts.find((a) => a.exchange === "paper"), [accounts]);
    const liveAccounts = useMemo(() => accounts.filter((a) => a.exchange !== "paper"), [accounts]);

    // Ensure account selection matches active mode
    useEffect(() => {
        if (selectedMode === "paper") {
            if (paperAccount && selectedAccountId !== paperAccount.id) {
                setSelectedAccountId(paperAccount.id);
            }
        } else {
            if (liveAccounts.length > 0 && (!selectedAccountId || selectedAccountId === paperAccount?.id)) {
                setSelectedAccountId(liveAccounts[0].id);
            }
        }
    }, [selectedMode, paperAccount, liveAccounts, selectedAccountId]);

    // Query trading status
    const {
        data: tradingStatus,
        refetch: refetchStatus,
        isLoading: isLoadingStatus,
    } = useQuery<TradingStatus>({
        queryKey: ["trading-status", strategy?.id],
        queryFn: () => strategy?.id ? tradingApi.getStatus(strategy.id) : Promise.reject("No strategy"),
        enabled: Boolean(strategy?.id),
        refetchInterval: (query) => {
            const status = query.state.data?.status;
            return status === "running" || status === "starting" ? 3000 : 10000;
        },
    });

    const isRunning = tradingStatus?.status === "running" || tradingStatus?.status === "starting";
    const activeSessionId = tradingStatus?.session?.id;

    // Fetch active session positions & orders when running
    const { data: activePositions = [], refetch: refetchPositions } = useQuery<Position[]>({
        queryKey: ["trading-positions", activeSessionId],
        queryFn: () => activeSessionId ? tradingApi.getPositions(activeSessionId) : Promise.resolve([]),
        enabled: Boolean(activeSessionId && isRunning),
        refetchInterval: isRunning ? 4000 : false,
    });

    const { data: activeOrders = [], refetch: refetchOrders } = useQuery<Order[]>({
        queryKey: ["trading-orders", activeSessionId],
        queryFn: () => activeSessionId ? tradingApi.getOrders(activeSessionId) : Promise.resolve([]),
        enabled: Boolean(activeSessionId && isRunning),
        refetchInterval: isRunning ? 4000 : false,
    });

    // Fetch recent trading logs
    const { refetch: refetchLogs } = useQuery({
        queryKey: ["trading-logs", strategy?.id],
        queryFn: async () => {
            if (!strategy?.id) return [];
            const res = await tradingLogsApi.list(strategy.id, { limit: 50 });
            setLiveLogs(res.logs || []);
            return res.logs || [];
        },
        enabled: Boolean(strategy?.id),
    });

    // Real-time WebSocket logs & position events
    useWebSocket(`/ws/strategies/${strategy?.id}`, {
        enabled: Boolean(strategy?.id),
        onMessage: (message) => {
            if (message.type === "log_new" && message.data) {
                setLiveLogs((prev) => [message.data as LogEntry, ...prev.slice(0, 99)]);
            } else if (message.type === "position_update") {
                refetchPositions();
                refetchStatus();
            }
        },
    });

    // Start Trading Mutation
    const startMutation = useMutation({
        mutationFn: async () => {
            if (!strategy?.id) throw new Error("Strategy not found");
            const accountId = selectedAccountId || paperAccount?.id;
            if (!accountId) {
                throw new Error(t("liveTradingView.pleaseSelectAccount"));
            }

            // Save config first
            await tradingApi.createConfig(strategy.id, {
                exchange: selectedMode === "paper" ? "paper" : (accounts.find((a) => a.id === accountId)?.exchange || "okx"),
                symbol,
                symbols: [symbol],
                interval,
                intervals: [interval],
                max_position_pct: parseFloat(maxPositionPct) || 10,
                stop_loss_pct: parseFloat(stopLossPct) || 2,
                leverage: parseInt(leverage) || 1,
            });

            return tradingApi.startTrading(strategy.id, accountId);
        },
        onSuccess: () => {
            toast.success(selectedMode === "paper" ? t("liveTradingView.toastPaperStarted") : t("liveTradingView.toastLiveStarted"));
            queryClient.invalidateQueries({ queryKey: ["trading-status", strategy?.id] });
            refetchStatus();
        },
        onError: (err: any) => {
            const detail = err?.message || t("liveTradingView.toastStartFailed");
            toast.error(`${t("liveTradingView.toastStartFailed")}: ${detail}`);
        },
    });

    // Stop Trading Mutation
    const stopMutation = useMutation({
        mutationFn: async () => {
            if (!strategy?.id) throw new Error("Strategy not found");
            return tradingApi.stopTrading(strategy.id);
        },
        onSuccess: () => {
            toast.success(t("liveTradingView.toastStopped"));
            queryClient.invalidateQueries({ queryKey: ["trading-status", strategy?.id] });
            refetchStatus();
        },
        onError: (err: any) => {
            toast.error(`${t("liveTradingView.toastStopFailed")}: ${err?.message || "Error"}`);
        },
    });

    if (!strategy) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                {t("liveTradingView.selectStrategyPrompt")}
            </div>
        );
    }

    return (
        <div className="h-full overflow-y-auto bg-background p-6 space-y-6">
            {/* Top Header Card */}
            <Card className="border-border shadow-sm">
                <CardContent className="p-6">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="space-y-1">
                            <div className="flex items-center gap-3">
                                <h1 className="text-2xl font-bold tracking-tight text-foreground">
                                    {strategy.name}
                                </h1>
                                {isRunning ? (
                                    <Badge className="bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 gap-1.5 py-0.5 px-2.5">
                                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                                        <span>{t("liveTradingView.running")} ({selectedMode === "paper" ? "Paper" : "Live"})</span>
                                    </Badge>
                                ) : (
                                    <Badge variant="outline" className="text-muted-foreground gap-1.5 py-0.5 px-2.5">
                                        <span className="w-2 h-2 rounded-full bg-muted-foreground/50" />
                                        <span>{t("liveTradingView.ready")}</span>
                                    </Badge>
                                )}
                            </div>
                            <p className="text-xs text-muted-foreground">
                                {t("liveTradingView.subtitle")}
                            </p>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-3 shrink-0">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                    refetchStatus();
                                    refetchPositions();
                                    refetchOrders();
                                    refetchLogs();
                                }}
                                disabled={isLoadingStatus}
                                className="gap-1.5 text-xs"
                            >
                                <RefreshCw size={13} className={cn(isLoadingStatus && "animate-spin")} />
                                <span>{t("liveTradingView.refresh")}</span>
                            </Button>

                            {isRunning ? (
                                <Button
                                    variant="destructive"
                                    size="sm"
                                    onClick={() => stopMutation.mutate()}
                                    disabled={stopMutation.isPending}
                                    className="gap-1.5 text-xs shadow"
                                >
                                    {stopMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Square size={14} />}
                                    <span>{t("liveTradingView.stopTrading")}</span>
                                </Button>
                            ) : (
                                <Button
                                    variant="default"
                                    size="sm"
                                    onClick={() => startMutation.mutate()}
                                    disabled={startMutation.isPending}
                                    className="gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white shadow"
                                >
                                    {startMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                                    <span>{selectedMode === "paper" ? t("liveTradingView.startPaperTrading") : t("liveTradingView.startLiveTrading")}</span>
                                </Button>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Trading Mode & Config Section */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Left 2 Cols: Mode Selection & Parameters */}
                <Card className="md:col-span-2 border-border">
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-base font-semibold flex items-center gap-2">
                                    <Activity className="w-4 h-4 text-primary" />
                                    <span>{t("liveTradingView.modeConfigTitle")}</span>
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    {t("liveTradingView.modeConfigSubtitle")}
                                </CardDescription>
                            </div>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setShowConfigDrawer(!showConfigDrawer)}
                                className="text-xs gap-1"
                            >
                                <Settings size={13} />
                                <span>{showConfigDrawer ? t("liveTradingView.collapseParams") : t("liveTradingView.adjustRiskParams")}</span>
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-4 pt-1">
                        {/* Mode Tabs */}
                        <div className="grid grid-cols-2 gap-3">
                            <button
                                type="button"
                                disabled={isRunning}
                                onClick={() => setSelectedMode("paper")}
                                className={cn(
                                    "p-4 rounded-xl border text-left transition-all flex flex-col justify-between gap-2",
                                    selectedMode === "paper"
                                        ? "border-emerald-500/50 bg-emerald-500/5 ring-1 ring-emerald-500/30"
                                        : "border-border hover:border-border/80 bg-card/60",
                                    isRunning && "opacity-60 cursor-not-allowed"
                                )}
                            >
                                <div className="flex items-center justify-between w-full">
                                    <div className="flex items-center gap-2">
                                        <Zap className="w-4 h-4 text-emerald-500" />
                                        <span className="font-semibold text-sm">{t("liveTradingView.paperTradingTitle")}</span>
                                    </div>
                                    <Badge variant="secondary" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-0">
                                        {t("liveTradingView.paperBadge")}
                                    </Badge>
                                </div>
                                <p className="text-xs text-muted-foreground leading-relaxed">
                                    {t("liveTradingView.paperTradingDesc")}
                                </p>
                            </button>

                            <button
                                type="button"
                                disabled={isRunning}
                                onClick={() => setSelectedMode("live")}
                                className={cn(
                                    "p-4 rounded-xl border text-left transition-all flex flex-col justify-between gap-2",
                                    selectedMode === "live"
                                        ? "border-primary/50 bg-primary/5 ring-1 ring-primary/30"
                                        : "border-border hover:border-border/80 bg-card/60",
                                    isRunning && "opacity-60 cursor-not-allowed"
                                )}
                            >
                                <div className="flex items-center justify-between w-full">
                                    <div className="flex items-center gap-2">
                                        <Shield className="w-4 h-4 text-primary" />
                                        <span className="font-semibold text-sm">{t("liveTradingView.liveExchangeTitle")}</span>
                                    </div>
                                    <Badge variant="outline" className="text-[10px]">
                                        {t("liveTradingView.liveBadge")}
                                    </Badge>
                                </div>
                                <p className="text-xs text-muted-foreground leading-relaxed">
                                    {t("liveTradingView.liveExchangeDesc")}
                                </p>
                            </button>
                        </div>

                        {/* Live account selector if Live mode */}
                        {selectedMode === "live" && (
                            <div className="p-3 rounded-lg border border-primary/20 bg-primary/5 flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                    <Wallet size={16} className="text-primary" />
                                    <span className="text-xs font-medium">{t("liveTradingView.exchangeAccountLabel")}</span>
                                    {liveAccounts.length > 0 ? (
                                        <Select
                                            value={selectedAccountId}
                                            onValueChange={setSelectedAccountId}
                                            disabled={isRunning}
                                        >
                                            <SelectTrigger className="h-8 text-xs w-48">
                                                <SelectValue placeholder={t("liveTradingView.selectAccountPlaceholder")} />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {liveAccounts.map((acc) => (
                                                    <SelectItem key={acc.id} value={acc.id}>
                                                        {acc.name} ({acc.exchange.toUpperCase()})
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    ) : (
                                        <span className="text-xs text-amber-600 dark:text-amber-400">
                                            {t("liveTradingView.noAccountsBound")}
                                        </span>
                                    )}
                                </div>

                                <ExchangeAccountsDialog strategyId={strategy.id}>
                                    <Button variant="outline" size="sm" className="h-7 text-xs">
                                        {t("liveTradingView.manageAccountsBtn")}
                                    </Button>
                                </ExchangeAccountsDialog>
                            </div>
                        )}

                        {/* Collapsible Risk & Market Config */}
                        {showConfigDrawer && (
                            <div className="p-4 rounded-xl border border-border bg-muted/20 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">{t("liveTradingView.symbolLabel")}</Label>
                                    <Input
                                        value={symbol}
                                        onChange={(e) => setSymbol(e.target.value)}
                                        disabled={isRunning}
                                        className="h-8 text-xs font-mono"
                                        placeholder="BTC-USDT-SWAP"
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">{t("liveTradingView.intervalLabel")}</Label>
                                    <Select value={interval} onValueChange={setInterval} disabled={isRunning}>
                                        <SelectTrigger className="h-8 text-xs">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {["1m", "5m", "15m", "1h", "4h", "1d"].map((intv) => (
                                                <SelectItem key={intv} value={intv}>{intv}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">{t("liveTradingView.maxPositionPctLabel")}</Label>
                                    <Input
                                        type="number"
                                        value={maxPositionPct}
                                        onChange={(e) => setMaxPositionPct(e.target.value)}
                                        disabled={isRunning}
                                        className="h-8 text-xs"
                                        min="1"
                                        max="100"
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">{t("liveTradingView.stopLossPctLabel")}</Label>
                                    <Input
                                        type="number"
                                        value={stopLossPct}
                                        onChange={(e) => setStopLossPct(e.target.value)}
                                        disabled={isRunning}
                                        className="h-8 text-xs"
                                        min="0.5"
                                        max="20"
                                    />
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Right Col: Performance Summary */}
                <Card className="border-border">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base font-semibold flex items-center gap-2">
                            <TrendingUp className="w-4 h-4 text-primary" />
                            <span>{t("liveTradingView.sessionSummaryTitle")}</span>
                        </CardTitle>
                        <CardDescription className="text-xs">
                            {t("liveTradingView.sessionSummarySubtitle")}
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 pt-1">
                        <div className="grid grid-cols-2 gap-2">
                            <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                                <div className="text-[11px] text-muted-foreground">{t("liveTradingView.totalPnlLabel")}</div>
                                <div className={cn(
                                    "text-lg font-bold font-mono mt-0.5",
                                    (tradingStatus?.total_pnl || 0) >= 0 ? "text-emerald-500" : "text-red-500"
                                )}>
                                    {(tradingStatus?.total_pnl || 0) >= 0 ? "+" : ""}
                                    {(tradingStatus?.total_pnl || 0).toFixed(2)}
                                </div>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                                <div className="text-[11px] text-muted-foreground">{t("liveTradingView.filledTradesLabel")}</div>
                                <div className="text-lg font-bold font-mono mt-0.5 text-foreground">
                                    {tradingStatus?.trade_count || activeOrders.length || 0}
                                </div>
                            </div>
                        </div>

                        <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-xs space-y-1.5">
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">{t("liveTradingView.activePositionsLabel")}</span>
                                <span className="font-mono font-medium">{activePositions.length ? activePositions.map(p => p.symbol).join(", ") : t("liveTradingView.flatPosition")}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">{t("liveTradingView.sessionStatusLabel")}</span>
                                <span className="font-medium text-foreground capitalize">{tradingStatus?.status || "stopped"}</span>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Bottom Section: Real-time Positions, Orders & Logs */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Positions & Orders Tabs */}
                <Card className="border-border flex flex-col h-[340px]">
                    <CardHeader className="py-3 px-4 border-b border-border">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Shield size={16} className="text-primary" />
                                <span className="font-semibold text-sm">{t("liveTradingView.positionsOrdersTitle")}</span>
                            </div>
                            <Badge variant="outline" className="text-[11px]">
                                {activePositions.length} / {activeOrders.length}
                            </Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0 flex-1 min-h-0">
                        <ScrollArea className="h-full">
                            {activePositions.length === 0 && activeOrders.length === 0 ? (
                                <div className="h-48 flex flex-col items-center justify-center text-muted-foreground gap-2 text-xs">
                                    <Clock size={24} className="opacity-40" />
                                    <span>{t("liveTradingView.noPositionsOrOrders")}</span>
                                </div>
                            ) : (
                                <div className="p-4 space-y-3">
                                    {activePositions.map((pos) => (
                                        <div key={pos.id} className="p-3 rounded-lg border border-border/60 bg-muted/20 flex items-center justify-between text-xs">
                                            <div className="space-y-0.5">
                                                <div className="font-semibold font-mono flex items-center gap-1.5">
                                                    <span>{pos.symbol}</span>
                                                    <Badge variant="outline" className={cn("text-[10px] px-1.5", pos.side === "long" ? "text-emerald-500" : "text-red-500")}>
                                                        {pos.side.toUpperCase()}
                                                    </Badge>
                                                </div>
                                                <div className="text-muted-foreground text-[11px]">
                                                    {t("liveTradingView.entryPriceLabel")}: {pos.entry_price} | {t("liveTradingView.markPriceLabel")}: {pos.current_price}
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className="font-mono font-medium">{pos.size}</div>
                                                <div className={cn("text-[11px] font-mono", (pos.unrealized_pnl || 0) >= 0 ? "text-emerald-500" : "text-red-500")}>
                                                    {(pos.unrealized_pnl || 0) >= 0 ? "+" : ""}{(pos.unrealized_pnl || 0).toFixed(2)} USD
                                                </div>
                                            </div>
                                        </div>
                                    ))}

                                    {activeOrders.slice(0, 5).map((order) => (
                                        <div key={order.id} className="p-2.5 rounded-lg border border-border/40 bg-card flex items-center justify-between text-xs">
                                            <div className="flex items-center gap-2">
                                                {order.side === "buy" ? <ArrowUpRight size={14} className="text-emerald-500" /> : <ArrowDownRight size={14} className="text-red-500" />}
                                                <div>
                                                    <span className="font-mono font-medium">{order.symbol}</span>
                                                    <span className="text-[11px] text-muted-foreground ml-2 capitalize">{order.side} {order.order_type}</span>
                                                </div>
                                            </div>
                                            <div className="font-mono text-right text-[11px]">
                                                <span>{order.size}</span>
                                                <Badge variant="outline" className="ml-2 text-[10px] uppercase">
                                                    {order.status}
                                                </Badge>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </ScrollArea>
                    </CardContent>
                </Card>

                {/* Live Engine Event Logs */}
                <Card className="border-border flex flex-col h-[340px]">
                    <CardHeader className="py-3 px-4 border-b border-border flex flex-row items-center justify-between">
                        <div className="flex items-center gap-2">
                            <FileText size={16} className="text-primary" />
                            <span className="font-semibold text-sm">{t("liveTradingView.engineLogsTitle")}</span>
                        </div>
                        <span className="text-[11px] text-muted-foreground font-mono">
                            {liveLogs.length} {t("liveTradingView.recordsCount")}
                        </span>
                    </CardHeader>
                    <CardContent className="p-0 flex-1 min-h-0 bg-muted/10 font-mono text-xs">
                        <ScrollArea className="h-full p-4">
                            {liveLogs.length === 0 ? (
                                <div className="h-48 flex items-center justify-center text-muted-foreground text-xs">
                                    {t("liveTradingView.noEngineLogs")}
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {liveLogs.map((log, idx) => (
                                        <div key={log.id || idx} className="flex items-start gap-2 leading-relaxed hover:bg-muted/40 p-1 rounded">
                                            <span className="text-[10px] text-muted-foreground shrink-0 mt-0.5">
                                                {log.created_at ? new Date(log.created_at).toLocaleTimeString() : "--:--:--"}
                                            </span>
                                            <Badge
                                                variant="outline"
                                                className={cn(
                                                    "text-[9px] px-1 py-0 uppercase shrink-0",
                                                    log.level === "error" ? "text-red-500 border-red-500/30" :
                                                    log.level === "warning" ? "text-amber-500 border-amber-500/30" :
                                                    "text-muted-foreground border-border"
                                                )}
                                            >
                                                {log.level}
                                            </Badge>
                                            <span className="text-foreground break-all text-[11px]">
                                                {log.message}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </ScrollArea>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
};

export default LiveTradingView;
