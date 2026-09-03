import { useState, useEffect, useCallback, useMemo } from "react";
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
    Radio,
    Shield,
    Zap,
    Play,
    Square,
    RefreshCw,
    Activity,
    CheckCircle2,
    AlertCircle,
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

export const LiveTradingView = ({ strategy, onNavigateToPortfolio }: LiveTradingViewProps) => {
    const { t } = useTranslation();
    const queryClient = useQueryClient();

    const [selectedMode, setSelectedMode] = useState<"paper" | "live">("paper");
    const [selectedAccountId, setSelectedAccountId] = useState<string>("");
    const [symbol, setSymbol] = useState("BTC-USDT-SWAP");
    const [interval, setInterval] = useState("1m");
    const [maxPositionPct, setMaxPositionPct] = useState("10");
    const [stopLossPct, setStopLossPct] = useState("2");
    const [leverage, setLeverage] = useState("1");
    const [showConfigDrawer, setShowConfigDrawer] = useState(false);
    const [liveLogs, setLiveLogs] = useState<LogEntry[]>([]);

    // Fetch exchange accounts for strategy (paper account is auto-created by API)
    const { data: accounts = [], isLoading: isLoadingAccounts } = useQuery({
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
                throw new Error("Please select or add an exchange account first");
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
            toast.success(selectedMode === "paper" ? "模拟盘交易已启动" : "实盘交易已启动");
            queryClient.invalidateQueries({ queryKey: ["trading-status", strategy?.id] });
            refetchStatus();
        },
        onError: (err: any) => {
            const detail = err?.message || "启动失败，请检查配置或凭据";
            toast.error(`启动交易失败: ${detail}`);
        },
    });

    // Stop Trading Mutation
    const stopMutation = useMutation({
        mutationFn: async () => {
            if (!strategy?.id) throw new Error("Strategy not found");
            return tradingApi.stopTrading(strategy.id);
        },
        onSuccess: () => {
            toast.success("交易会话已停止");
            queryClient.invalidateQueries({ queryKey: ["trading-status", strategy?.id] });
            refetchStatus();
        },
        onError: (err: any) => {
            toast.error(`停止交易失败: ${err?.message || "未知错误"}`);
        },
    });

    if (!strategy) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                请先选择一个策略
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
                                        <span>运行中 ({tradingStatus?.session?.exchange_account_id ? (selectedMode === "paper" ? "模拟盘" : "实盘") : "执行中"})</span>
                                    </Badge>
                                ) : (
                                    <Badge variant="outline" className="text-muted-foreground gap-1.5 py-0.5 px-2.5">
                                        <span className="w-2 h-2 rounded-full bg-muted-foreground/50" />
                                        <span>已就绪 / 未启动</span>
                                    </Badge>
                                )}
                            </div>
                            <p className="text-xs text-muted-foreground">
                                实时将策略信号转化为交易委托，并通过侵入式风控引擎校验执行。
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
                                <span>刷新</span>
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
                                    <span>停止交易</span>
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
                                    <span>{selectedMode === "paper" ? "启动模拟盘交易 (Paper)" : "启动实盘交易"}</span>
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
                                    <span>运行模式与参数配置</span>
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    选择以零风险模拟盘还是交易所实盘运行此策略
                                </CardDescription>
                            </div>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setShowConfigDrawer(!showConfigDrawer)}
                                className="text-xs gap-1"
                            >
                                <Settings size={13} />
                                <span>{showConfigDrawer ? "收起参数" : "调整风控参数"}</span>
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
                                        <span className="font-semibold text-sm">Paper Trading (模拟盘)</span>
                                    </div>
                                    <Badge variant="secondary" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-0">
                                        推荐 / 免费
                                    </Badge>
                                </div>
                                <p className="text-xs text-muted-foreground leading-relaxed">
                                    免配置 API Key，直连 OKX 实时公共行情，本地撮合零资金风险。
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
                                        <span className="font-semibold text-sm">Live Exchange (实盘交易)</span>
                                    </div>
                                    <Badge variant="outline" className="text-[10px]">
                                        真实资金
                                    </Badge>
                                </div>
                                <p className="text-xs text-muted-foreground leading-relaxed">
                                    支持 OKX / Binance，通过 9 项风控守则与动态止盈止损执行。
                                </p>
                            </button>
                        </div>

                        {/* Live account selector if Live mode */}
                        {selectedMode === "live" && (
                            <div className="p-3 rounded-lg border border-primary/20 bg-primary/5 flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                    <Wallet size={16} className="text-primary" />
                                    <span className="text-xs font-medium">交易所实盘账户：</span>
                                    {liveAccounts.length > 0 ? (
                                        <Select
                                            value={selectedAccountId}
                                            onValueChange={setSelectedAccountId}
                                            disabled={isRunning}
                                        >
                                            <SelectTrigger className="h-8 text-xs w-48">
                                                <SelectValue placeholder="选择实盘账户" />
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
                                            暂无绑定的实盘账户
                                        </span>
                                    )}
                                </div>

                                <ExchangeAccountsDialog strategyId={strategy.id}>
                                    <Button variant="outline" size="sm" className="h-7 text-xs">
                                        管理账户
                                    </Button>
                                </ExchangeAccountsDialog>
                            </div>
                        )}

                        {/* Collapsible Risk & Market Config */}
                        {showConfigDrawer && (
                            <div className="p-4 rounded-xl border border-border bg-muted/20 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">交易标的</Label>
                                    <Input
                                        value={symbol}
                                        onChange={(e) => setSymbol(e.target.value)}
                                        disabled={isRunning}
                                        className="h-8 text-xs font-mono"
                                        placeholder="BTC-USDT-SWAP"
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">K线周期</Label>
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
                                    <Label className="text-xs text-muted-foreground">单笔最大仓位 %</Label>
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
                                    <Label className="text-xs text-muted-foreground">硬止损百分比 %</Label>
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
                            <span>会话统计概览</span>
                        </CardTitle>
                        <CardDescription className="text-xs">
                            当前交易会话的运行指标
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 pt-1">
                        <div className="grid grid-cols-2 gap-2">
                            <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                                <div className="text-[11px] text-muted-foreground">总盈亏 (USD)</div>
                                <div className={cn(
                                    "text-lg font-bold font-mono mt-0.5",
                                    (tradingStatus?.total_pnl || 0) >= 0 ? "text-emerald-500" : "text-red-500"
                                )}>
                                    {(tradingStatus?.total_pnl || 0) >= 0 ? "+" : ""}
                                    {(tradingStatus?.total_pnl || 0).toFixed(2)}
                                </div>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                                <div className="text-[11px] text-muted-foreground">累计成交笔数</div>
                                <div className="text-lg font-bold font-mono mt-0.5 text-foreground">
                                    {tradingStatus?.trade_count || activeOrders.length || 0}
                                </div>
                            </div>
                        </div>

                        <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-xs space-y-1.5">
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">当前持仓标的:</span>
                                <span className="font-mono font-medium">{activePositions.length ? activePositions.map(p => p.symbol).join(", ") : "空仓 (Flat)"}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">会话持续状态:</span>
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
                                <span className="font-semibold text-sm">当前持仓与近期订单</span>
                            </div>
                            <Badge variant="outline" className="text-[11px]">
                                {activePositions.length} 持仓 / {activeOrders.length} 订单
                            </Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0 flex-1 min-h-0">
                        <ScrollArea className="h-full">
                            {activePositions.length === 0 && activeOrders.length === 0 ? (
                                <div className="h-48 flex flex-col items-center justify-center text-muted-foreground gap-2 text-xs">
                                    <Clock size={24} className="opacity-40" />
                                    <span>暂无活动中的持仓或委托订单</span>
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
                                                    入场价: {pos.entry_price} | 标记价: {pos.current_price}
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
                            <span className="font-semibold text-sm">交易引擎实时日志</span>
                        </div>
                        <span className="text-[11px] text-muted-foreground font-mono">
                            {liveLogs.length} 条记录
                        </span>
                    </CardHeader>
                    <CardContent className="p-0 flex-1 min-h-0 bg-muted/10 font-mono text-xs">
                        <ScrollArea className="h-full p-4">
                            {liveLogs.length === 0 ? (
                                <div className="h-48 flex items-center justify-center text-muted-foreground text-xs">
                                    暂无引擎事件日志
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
