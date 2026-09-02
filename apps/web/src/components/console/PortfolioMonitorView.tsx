import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Readout } from "@/components/console/Readout";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    BarChart3,
    Activity,
    Settings,
    RefreshCw,
    AlertCircle
} from "lucide-react";
// 图表相关导入暂时隐藏 - 等待后端数据打点
// import {
//     Area,
//     AreaChart,
//     CartesianGrid,
//     ResponsiveContainer,
//     Tooltip as RechartsTooltip,
//     XAxis,
//     YAxis
// } from "recharts";
import { portfolioApi, PortfolioSummary, OrderData, PositionHistoryData } from "@/lib/api";
import { Strategy, ExchangeAccountResponse } from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";
import AccountSidebar from "./AccountSidebar";
import { useTranslation } from "react-i18next";
import {
    aggregateSummaries,
    aggregateOrders,
    aggregatePositionHistory,
    handlePartialResults,
    calculateTotalBalance,
    calculateTotalUnrealizedPnl,
} from "@/lib/portfolioUtils";

interface PortfolioMonitorViewProps {
    onNavigateToLive?: () => void;
    strategy?: Strategy | null;
}

const PortfolioMonitorView = ({ onNavigateToLive, strategy }: PortfolioMonitorViewProps) => {
    const [summary, setSummary] = useState<PortfolioSummary | null>(null);
    const [pendingOrders, setPendingOrders] = useState<OrderData[]>([]);
    const [orderHistory, setOrderHistory] = useState<OrderData[]>([]);
    const [positionHistory, setPositionHistory] = useState<PositionHistoryData[]>([]);
    const [accounts, setAccounts] = useState<ExchangeAccountResponse[]>([]);
    const [selectedAccountId, setSelectedAccountId] = useState("all");
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const [accountBalances, setAccountBalances] = useState<Map<string, number>>(new Map());
    const [accountSummaries, setAccountSummaries] = useState<Map<string, PortfolioSummary>>(new Map());
    // 暂时隐藏权益曲线 - 等待后端数据打点
    // const [equityCurve, setEquityCurve] = useState<EquityPoint[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const { t, i18n } = useTranslation();

    // WebSocket for real-time updates
    useWebSocket(`/ws/strategies/${strategy?.id}`, {
        enabled: !!strategy?.id,
        onMessage: (message) => {
            if (message.type === 'position_update') {
                // Refresh data when position update received
                fetchData();
            }
        }
    });

    const fetchData = async (showRefresh = false) => {
        if (!strategy?.id) return;

        if (showRefresh) setRefreshing(true);
        setError(null);

        try {
            console.log('[Portfolio] Fetching portfolio data for strategy:', strategy.id);

            // Check if "All Accounts" is selected
            if (selectedAccountId === "all" && accounts.length > 0) {
                // Fetch data for all accounts in parallel
                const accountDataPromises = accounts.map(async (account) => {
                    const [summary, orders, history, posHistory] = await Promise.allSettled([
                        portfolioApi.getSummary(strategy.id, account.id),
                        portfolioApi.getPendingOrders(strategy.id, account.id),
                        portfolioApi.getOrderHistory(strategy.id, 50, account.id),
                        portfolioApi.getPositionsHistory(strategy.id, 50, account.id),
                    ]);

                    return {
                        accountId: account.id,
                        summary,
                        orders,
                        history,
                        posHistory,
                    };
                });

                const allAccountsData = await Promise.all(accountDataPromises);

                // Extract successful results
                const summaries = handlePartialResults(allAccountsData.map((d) => d.summary));
                const pendingOrders = handlePartialResults(allAccountsData.map((d) => d.orders));
                const orderHistories = handlePartialResults(allAccountsData.map((d) => d.history));
                const posHistories = handlePartialResults(allAccountsData.map((d) => d.posHistory));

                // Store individual account summaries for balance display
                const balancesMap = new Map<string, number>();
                const summariesMap = new Map<string, PortfolioSummary>();
                summaries.successful.forEach((summary, idx) => {
                    const accountId = accounts[idx]?.id;
                    if (accountId && summary.balance) {
                        balancesMap.set(accountId, summary.balance.total_equity);
                        summariesMap.set(accountId, summary);
                    }
                });
                setAccountBalances(balancesMap);
                setAccountSummaries(summariesMap);

                // Aggregate all data
                if (summaries.successful.length > 0) {
                    const aggregated = aggregateSummaries(summaries.successful);
                    setSummary(aggregated);
                }

                // Aggregate orders
                const ordersWithAccounts = allAccountsData.map((data, idx) => ({
                    accountId: accounts[idx]?.id || "",
                    orders:
                        data.orders.status === "fulfilled"
                            ? data.orders.value
                            : [],
                }));
                setPendingOrders(aggregateOrders(ordersWithAccounts));

                // Aggregate order history
                const historyWithAccounts = allAccountsData.map((data, idx) => ({
                    accountId: accounts[idx]?.id || "",
                    orders:
                        data.history.status === "fulfilled"
                            ? data.history.value.items
                            : [],
                }));
                setOrderHistory(aggregateOrders(historyWithAccounts));

                // Aggregate position history
                const posHistoryWithAccounts = allAccountsData.map((data, idx) => ({
                    accountId: accounts[idx]?.id || "",
                    positions:
                        data.posHistory.status === "fulfilled"
                            ? data.posHistory.value
                            : [],
                }));
                setPositionHistory(aggregatePositionHistory(posHistoryWithAccounts));

                console.log('[Portfolio] Aggregated data from', summaries.successful.length, 'accounts');
                if (summaries.failed > 0) {
                    console.warn('[Portfolio]', summaries.failed, 'accounts failed to load');
                }
            } else {
                // Single account or default behavior
                const accountId = selectedAccountId === "all" ? undefined : selectedAccountId;
                const [summaryData, ordersData, historyData, posHistoryData] = await Promise.allSettled([
                    portfolioApi.getSummary(strategy.id, accountId || undefined),
                    portfolioApi.getPendingOrders(strategy.id, accountId || undefined),
                    portfolioApi.getOrderHistory(strategy.id, 50, accountId || undefined),
                    portfolioApi.getPositionsHistory(strategy.id, 50, accountId || undefined),
                ]);

                // Process summary
                if (summaryData.status === 'fulfilled') {
                    console.log('[Portfolio] Summary data:', summaryData.value);
                    setSummary(summaryData.value);

                    // Store balance for this account
                    if (accountId && summaryData.value.balance) {
                        const balancesMap = new Map(accountBalances);
                        balancesMap.set(accountId, summaryData.value.balance.total_equity);
                        setAccountBalances(balancesMap);
                    }
                } else {
                    console.error('[Portfolio] Failed to fetch summary:', summaryData.reason);
                }

                // Process pending orders
                if (ordersData.status === 'fulfilled') {
                    console.log('[Portfolio] Pending orders:', ordersData.value);
                    setPendingOrders(ordersData.value);
                } else {
                    console.error('[Portfolio] Failed to fetch pending orders:', ordersData.reason);
                }

                // Process order history
                if (historyData.status === 'fulfilled') {
                    console.log('[Portfolio] Order history:', historyData.value);
                    setOrderHistory(historyData.value.items);
                } else {
                    console.error('[Portfolio] Failed to fetch order history:', historyData.reason);
                }

                // Process position history
                if (posHistoryData.status === 'fulfilled') {
                    console.log('[Portfolio] Position history:', posHistoryData.value);
                    setPositionHistory(posHistoryData.value);
                } else {
                    console.error('[Portfolio] Failed to fetch position history:', posHistoryData.reason);
                }

                // Check if all requests failed
                const allFailed = [summaryData, ordersData, historyData, posHistoryData].every(
                    result => result.status === 'rejected'
                );
                if (allFailed) {
                    setError("Failed to load portfolio data. Please try again.");
                }
            }

            // 暂时隐藏权益曲线 - 等待后端数据打点
            // TODO: 恢复权益曲线功能
            // const equityData = await portfolioApi.getEquityCurve(strategy.id);
        } catch (error) {
            console.error("[Portfolio] Unexpected error:", error);
            setError("Failed to load portfolio data. Please try again.");
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    useEffect(() => {
        if (!strategy?.id) return;
        let canceled = false;
        const loadAccounts = async () => {
            try {
                const list = await portfolioApi.listAccounts(strategy.id);
                if (canceled) return;
                setAccounts(list);

                // Restore saved account selection from localStorage
                const savedAccountId = localStorage.getItem('portfolio_selected_account');
                if (savedAccountId) {
                    // Check if saved account still exists
                    const accountExists = list.find(acc => acc.id === savedAccountId) || savedAccountId === "all";
                    if (accountExists) {
                        setSelectedAccountId(savedAccountId);
                    } else {
                        // Saved account no longer exists, default to "all"
                        setSelectedAccountId(list.length > 0 ? "all" : "");
                    }
                } else if (list.length > 0) {
                    // No saved selection, default to "all" if multiple accounts
                    setSelectedAccountId(list.length > 1 ? "all" : list[0].id);
                }
            } catch (err) {
                console.error("[Portfolio] Failed to load accounts:", err);
            }
        };
        loadAccounts();
        return () => {
            canceled = true;
        };
    }, [strategy?.id]);

    // Save selected account to localStorage
    useEffect(() => {
        if (selectedAccountId) {
            localStorage.setItem('portfolio_selected_account', selectedAccountId);
        }
    }, [selectedAccountId]);

    useEffect(() => {
        fetchData();
        // Fallback polling every 30 seconds (WebSocket provides real-time updates)
        const interval = setInterval(() => fetchData(), 30000);
        return () => clearInterval(interval);
    }, [strategy?.id, selectedAccountId]);

    const formatNumber = (num: number, decimals = 2) => {
        return num.toFixed(decimals);
    };

    const formatCurrency = (num: number) => {
        return `$${formatNumber(num, 2)}`;
    };

    const formatPercent = (num: number) => {
        const sign = num >= 0 ? "+" : "";
        return `${sign}${formatNumber(num, 2)}%`;
    };

    const formatTimestamp = (timestamp: string) => {
        const date = new Date(timestamp);
        const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";
        return date.toLocaleString(locale);
    };

    const formatDuration = (openedAt: string, closedAt: string) => {
        const duration = new Date(closedAt).getTime() - new Date(openedAt).getTime();
        const hours = Math.floor(duration / (1000 * 60 * 60));
        const minutes = Math.floor((duration % (1000 * 60 * 60)) / (1000 * 60));
        if (hours > 24) {
            return t("portfolioView.duration.daysHours", { days: Math.floor(hours / 24), hours: hours % 24 });
        }
        return hours > 0
            ? t("portfolioView.duration.hoursMinutes", { hours, minutes })
            : t("portfolioView.duration.minutes", { minutes });
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-muted-foreground">{t("portfolioView.loading")}</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="h-full flex flex-col items-center justify-center p-8">
                <div className="w-20 h-20 rounded-md bg-destructive/10 flex items-center justify-center mb-6">
                    <AlertCircle className="w-10 h-10 text-destructive" />
                </div>
                <h2 className="text-2xl font-bold text-foreground mb-2">{t("portfolioView.errorTitle")}</h2>
                <p className="text-muted-foreground text-center max-w-md mb-6">
                    {error}
                </p>
                <Button onClick={() => fetchData(true)} className="gap-2">
                    <RefreshCw size={16} />
                    {t("portfolioView.tryAgain")}
                </Button>
            </div>
        );
    }

    // State 1: No trading config - Show setup guide
    if (summary && !summary.has_trading_config) {
        return (
            <div className="h-full flex flex-col items-center justify-center p-8">
                <div className="w-20 h-20 rounded-md bg-primary/10 flex items-center justify-center mb-6">
                    <Settings className="w-10 h-10 text-primary" />
                </div>
                <h2 className="text-2xl font-bold text-foreground mb-2">{t("portfolioView.configureTitle")}</h2>
                <p className="text-muted-foreground text-center max-w-md mb-6">
                    {t("portfolioView.configureSubtitle")}
                </p>
                <Button className="gap-2" onClick={onNavigateToLive}>
                    <Settings size={16} />
                    {t("portfolioView.goToSettings")}
                </Button>
            </div>
        );
    }

    // State 2: Config exists but no active session - Show "Start Session" prompt
    if (summary && !summary.has_active_session) {
        return (
            <div className="h-full flex flex-col items-center justify-center p-8">
                <div className="w-20 h-20 rounded-md bg-primary/10 flex items-center justify-center mb-6">
                    <BarChart3 className="w-10 h-10 text-primary" />
                </div>
                <h2 className="text-2xl font-bold text-foreground mb-2">{t("portfolioView.readyTitle")}</h2>
                <p className="text-muted-foreground text-center max-w-md mb-6">
                    {t("portfolioView.readySubtitle")}
                </p>
                <Button className="gap-2" onClick={onNavigateToLive}>
                    <Activity size={16} />
                    {t("portfolioView.startSession")}
                </Button>
            </div>
        );
    }

    // State 3: Active session - Show Dashboard (only if summary exists)
    if (!summary) return null;

    const { balance, positions, total_pnl, total_trades } = summary;

    // Calculate sidebar metrics
    const allSummaries = Array.from(accountSummaries.values());
    const totalBalance = allSummaries.length > 0
        ? calculateTotalBalance(allSummaries)
        : (balance?.total_equity || 0);
    const unrealizedPnl = allSummaries.length > 0
        ? calculateTotalUnrealizedPnl(allSummaries)
        : (balance?.unrealized_pnl || 0);

    return (
        <div className="h-full flex overflow-hidden">
            {/* Account Sidebar */}
            <AccountSidebar
                accounts={accounts}
                selectedAccountId={selectedAccountId}
                onAccountChange={setSelectedAccountId}
                totalBalance={totalBalance}
                unrealizedPnl={unrealizedPnl}
                collapsed={sidebarCollapsed}
                onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
                accountBalances={accountBalances}
            />

            {/* Main Content */}
            <div className="flex-1 overflow-auto p-6">
                <div className="max-w-6xl mx-auto space-y-6">
                    {/* Header with refresh */}
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <h1 className="text-2xl font-bold">{t("portfolioView.title")}</h1>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => fetchData(true)}
                            disabled={refreshing}
                            className="gap-2"
                        >
                            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
                            {t("portfolioView.refresh")}
                        </Button>
                    </div>

                <Readout
                    items={[
                        {
                            label: t("portfolioView.summary.totalPnl"),
                            value: `${total_pnl >= 0 ? "+" : ""}${formatCurrency(total_pnl)}`,
                            tone: total_pnl > 0 ? "long" : total_pnl < 0 ? "short" : "neutral",
                            note: balance && balance.total_equity > 0
                                ? formatPercent((total_pnl / balance.total_equity) * 100)
                                : undefined,
                        },
                        {
                            label: t("portfolioView.summary.balance"),
                            value: balance ? formatCurrency(balance.total_equity) : "--",
                            note: balance
                                ? `${t("portfolioView.summary.available")}: ${formatCurrency(balance.available)}`
                                : undefined,
                        },
                        { label: t("portfolioView.summary.positions"), value: String(positions.length) },
                        { label: t("portfolioView.summary.tradesToday"), value: String(total_trades) },
                    ]}
                />

                    {/* Tabs */}
                    <Tabs defaultValue="positions" className="w-full">
                        <TabsList className="mb-4">
                        <TabsTrigger value="positions">{t("portfolioView.tabs.positions")}</TabsTrigger>
                        <TabsTrigger value="orders">{t("portfolioView.tabs.orders", { count: pendingOrders.length })}</TabsTrigger>
                        <TabsTrigger value="history">{t("portfolioView.tabs.history")}</TabsTrigger>
                        <TabsTrigger value="pos_history">{t("portfolioView.tabs.positionHistory")}</TabsTrigger>
                        </TabsList>

                    {/* 资产走势 Tab - 暂时隐藏，等待后端数据打点 */}
                    {/* <TabsTrigger value="performance">资产走势</TabsTrigger> */}
                    {/* <TabsContent value="performance" className="mt-0 space-y-4">
                        <Card className="h-[400px]">
                            <CardHeader>
                                <CardTitle className="text-sm font-medium">权益曲线</CardTitle>
                            </CardHeader>
                            <CardContent className="h-[320px]">
                                {equityCurve.length > 0 ? (
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart data={equityCurve}>
                                            <defs>
                                                <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                                            <XAxis
                                                dataKey="timestamp"
                                                tickFormatter={(ts) => new Date(ts).toLocaleTimeString()}
                                                className="text-muted-foreground text-xs"
                                            />
                                            <YAxis
                                                domain={['auto', 'auto']}
                                                className="text-muted-foreground text-xs"
                                                tickFormatter={(val) => `$${val}`}
                                            />
                                            <RechartsTooltip
                                                contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))' }}
                                                labelFormatter={(label) => new Date(label).toLocaleString()}
                                                formatter={(value: number) => [formatCurrency(value), "Equity"]}
                                            />
                                            <Area
                                                type="monotone"
                                                dataKey="equity"
                                                stroke="hsl(var(--primary))"
                                                fillOpacity={1}
                                                fill="url(#colorEquity)"
                                            />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                ) : (
                                    <div className="h-full flex items-center justify-center text-muted-foreground">
                                        暂无数据
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent> */}

                    <TabsContent value="pos_history" className="mt-0">
                        {positionHistory.length === 0 ? (
                            <Card>
                                <CardContent className="py-8">
                                    <div className="text-center text-muted-foreground">
                                        {t("portfolioView.empty.positionHistory")}
                                    </div>
                                </CardContent>
                            </Card>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {positionHistory.map((pos, i) => (
                                    <Card key={i} className="transition-colors hover:border-primary/40">
                                        <CardHeader className="pb-3">
                                            <div className="flex items-center justify-between">
                                                <CardTitle className="text-lg font-bold">{pos.inst_id}</CardTitle>
                                                <span className={`px-3 py-1 rounded-full text-sm font-medium ${pos.pos_side.toLowerCase() === 'long'
                                                    ? "bg-long/10 text-long"
                                                    : "bg-short/10 text-short"
                                                    }`}>
                                                    {pos.pos_side.toUpperCase()}
                                                </span>
                                            </div>
                                            <div className="text-xs text-muted-foreground mt-1">
                                                {formatTimestamp(pos.closed_at)}
                                            </div>
                                        </CardHeader>
                                        <CardContent className="space-y-3">
                                            <div className="grid grid-cols-2 gap-3">
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.size")}</div>
                                                    <div className="font-medium">{formatNumber(pos.pos, 4)}</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.holdTime")}</div>
                                                    <div className="font-medium text-xs">
                                                        {formatDuration(pos.opened_at, pos.closed_at)}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-2 gap-3">
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.entryPrice")}</div>
                                                    <div className="font-medium">{formatCurrency(pos.entry_px)}</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.exitPrice")}</div>
                                                    <div className="font-medium">{formatCurrency(pos.exit_px)}</div>
                                                </div>
                                            </div>
                                            <div className="pt-2 border-t">
                                                <div className="flex items-center justify-between">
                                                    <div>
                                                        <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.realizedPnl")}</div>
                                                        <div className={`text-lg font-bold ${pos.realized_pnl >= 0 ? "text-long" : "text-short"}`}>
                                                            {pos.realized_pnl >= 0 ? "+" : ""}{formatCurrency(pos.realized_pnl)}
                                                        </div>
                                                    </div>
                                                    <div className={`text-2xl font-bold ${pos.realized_pnl >= 0 ? "text-long" : "text-short"}`}>
                                                        {formatPercent(pos.return_pct)}
                                                    </div>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </TabsContent>

                    <TabsContent value="positions" className="mt-0">
                        {positions.length === 0 ? (
                            <Card>
                                <CardContent className="py-8">
                                    <div className="text-center text-muted-foreground">
                                        {t("portfolioView.empty.positions")}
                                    </div>
                                </CardContent>
                            </Card>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {positions.map((pos, idx) => (
                                    <Card key={idx} className="transition-colors hover:border-primary/40">
                                        <CardHeader className="pb-3">
                                            <div className="flex items-center justify-between">
                                                <CardTitle className="text-lg font-bold">{pos.inst_id}</CardTitle>
                                                <span className={`px-3 py-1 rounded-full text-sm font-medium ${pos.pos_side === "long"
                                                    ? "bg-long/10 text-long"
                                                    : "bg-short/10 text-short"
                                                    }`}>
                                                    {pos.pos_side.toUpperCase()}
                                                </span>
                                            </div>
                                        </CardHeader>
                                        <CardContent className="space-y-3">
                                            <div className="grid grid-cols-2 gap-3">
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.size")}</div>
                                                    <div className="font-medium">{formatNumber(pos.pos, 4)}</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.leverage")}</div>
                                                    <div className="font-medium">{pos.lever}x</div>
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-2 gap-3">
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.entryPrice")}</div>
                                                    <div className="font-medium">{formatCurrency(pos.avg_px)}</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.markPrice")}</div>
                                                    <div className="font-medium">{formatCurrency(pos.mark_px)}</div>
                                                </div>
                                            </div>
                                            <div className="pt-2 border-t">
                                                <div className="flex items-center justify-between">
                                                    <div>
                                                        <div className="text-xs text-muted-foreground mb-1">{t("portfolioView.fields.unrealizedPnl")}</div>
                                                        <div className={`text-lg font-bold ${pos.upl >= 0 ? "text-long" : "text-short"}`}>
                                                            {pos.upl >= 0 ? "+" : ""}{formatCurrency(pos.upl)}
                                                        </div>
                                                    </div>
                                                    <div className={`text-2xl font-bold ${pos.upl_ratio >= 0 ? "text-long" : "text-short"}`}>
                                                        {formatPercent(pos.upl_ratio)}
                                                    </div>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </TabsContent>

                    <TabsContent value="orders">
                        <Card>
                            <CardContent className="p-0">
                                {pendingOrders.length === 0 ? (
                                    <div className="text-center text-muted-foreground py-8">
                                        {t("portfolioView.empty.orders")}
                                    </div>
                                ) : (
                                    <div className="overflow-x-auto">
                                        <table className="w-full">
                                            <thead className="border-b border-border">
                                                <tr className="text-xs text-muted-foreground">
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.table.contract")}</th>
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.table.side")}</th>
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.table.type")}</th>
                                                    <th className="px-4 py-3 text-right font-medium">{t("portfolioView.table.price")}</th>
                                                    <th className="px-4 py-3 text-right font-medium">{t("portfolioView.table.size")}</th>
                                                    <th className="px-4 py-3 text-right font-medium">{t("portfolioView.table.filled")}</th>
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.table.status")}</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {pendingOrders.map((order) => (
                                                    <tr key={order.order_id} className="border-b border-border hover:bg-muted/50">
                                                        <td className="px-4 py-3 font-medium">{order.inst_id}</td>
                                                        <td className="px-4 py-3">
                                                            <span className={`px-2 py-1 rounded text-xs ${order.side === "buy"
                                                                ? "bg-long/10 text-long"
                                                                : "bg-short/10 text-short"
                                                                }`}>
                                                                {order.side}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-3">{order.order_type}</td>
                                                        <td className="px-4 py-3 text-right numeric">
                                                            {order.px ? formatCurrency(order.px) : t("portfolioView.market")}
                                                        </td>
                                                        <td className="px-4 py-3 text-right numeric">{formatNumber(order.sz, 4)}</td>
                                                        <td className="px-4 py-3 text-right numeric">{formatNumber(order.filled_size, 4)}</td>
                                                        <td className="px-4 py-3">
                                                            <span className="px-2 py-1 rounded text-xs bg-primary/10 text-primary">
                                                                {order.status}
                                                            </span>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    <TabsContent value="history">
                        <Card>
                            <CardContent className="p-0">
                                {orderHistory.length === 0 ? (
                                    <div className="text-center text-muted-foreground py-8">
                                        {t("portfolioView.empty.orderHistory")}
                                    </div>
                                ) : (
                                    <div className="overflow-x-auto">
                                        <table className="w-full">
                                            <thead className="border-b border-border">
                                                <tr className="text-xs text-muted-foreground">
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.history.time")}</th>
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.history.contract")}</th>
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.history.side")}</th>
                                                    <th className="px-4 py-3 text-right font-medium">{t("portfolioView.history.size")}</th>
                                                    <th className="px-4 py-3 text-right font-medium">{t("portfolioView.history.price")}</th>
                                                    <th className="px-4 py-3 text-left font-medium">{t("portfolioView.history.status")}</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {orderHistory.map((order) => (
                                                    <tr key={order.order_id} className="border-b border-border hover:bg-muted/50">
                                                        <td className="px-4 py-3 text-xs text-muted-foreground">
                                                            {formatTimestamp(order.created_at)}
                                                        </td>
                                                        <td className="px-4 py-3 font-medium">{order.symbol}</td>
                                                        <td className="px-4 py-3">
                                                            <span className={`px-2 py-1 rounded text-xs ${order.side === "buy"
                                                                ? "bg-long/10 text-long"
                                                                : "bg-short/10 text-short"
                                                                }`}>
                                                                {order.side}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-3 text-right numeric">{formatNumber(order.size, 4)}</td>
                                                        <td className="px-4 py-3 text-right numeric">
                                                            {order.avg_fill_price ? formatCurrency(order.avg_fill_price) : "-"}
                                                        </td>
                                                        <td className="px-4 py-3">
                                                            <span className={`px-2 py-1 rounded text-xs ${order.status === "filled"
                                                                ? "bg-long/10 text-long"
                                                                : order.status === "cancelled"
                                                                    ? "bg-muted-foreground/10 text-muted-foreground"
                                                                    : "bg-primary/10 text-primary"
                                                                }`}>
                                                                {order.status}
                                                            </span>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>
                </div>
            </div>
        </div>
    );
};

export default PortfolioMonitorView;
