import { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { TrendingDown, Play, Loader2, History, Sparkles } from "lucide-react";
import { XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, AreaChart, ReferenceLine } from "recharts";
import { backtestsApi, jobsApi, strategiesApi, templateBacktestsApi } from "@/lib/api";
import type { Strategy, BacktestRun, BacktestCreateRequest, BacktestOrder, BacktestPosition, BacktestTrade, BacktestSignalEvent, BacktestCandle } from "@/lib/types";
import { cn } from "@/lib/utils";
import UsStockPickerDialog from "@/components/market/UsStockPickerDialog";
import { useTranslation } from "react-i18next";
import TradingViewChart from "@/components/charts/TradingViewChart";
import { Readout, ReadoutList } from "@/components/console/Readout";

interface BacktestViewProps {
    strategy: Strategy | null;
    onAnalyzeWithAI?: (backtestId: string) => void;
    mode?: "strategy" | "template";
    templateId?: string;
    readOnly?: boolean;
    hideActions?: boolean;
    hideSettings?: boolean;
}

type ParamSchemaItem = {
    name: string;
    type?: "int" | "float" | "bool" | "str";
    default?: unknown;
    min?: number;
    max?: number;
    description?: string;
};

type ParamsSchema = {
    version?: number;
    params?: ParamSchemaItem[];
};

type StrategyMeta = {
    version?: number;
    params_schema?: ParamsSchema;
};

const intervals = [
    { value: "15m", label: "15m" },
    { value: "1h", label: "1h" },
    { value: "4h", label: "4h" },
    { value: "1d", label: "1d" },
];

type BacktestApiAdapter = {
    list: (resourceId: string) => Promise<BacktestRun[]>;
    get: (resourceId: string, runId: string) => Promise<BacktestRun>;
    getEquityCurve: (resourceId: string, runId: string) => Promise<{ data: Array<{ timestamp: number; equity: number; drawdown: number }> }>;
    getCandles?: (resourceId: string, runId: string) => Promise<{ data: BacktestCandle[] }>;
    getTrades: (resourceId: string, runId: string) => Promise<{ trades: BacktestTrade[] }>;
    getOrders: (resourceId: string, runId: string) => Promise<{ orders: BacktestOrder[] }>;
    getPositions: (resourceId: string, runId: string) => Promise<{ positions: BacktestPosition[] }>;
    getSignalEvents: (resourceId: string, runId: string) => Promise<{ events: BacktestSignalEvent[] }>;
    create?: (resourceId: string, req: BacktestCreateRequest) => Promise<{ job: { id: string }; backtest_run?: BacktestRun }>;
};

const BacktestView = ({
    strategy,
    onAnalyzeWithAI,
    mode = "strategy",
    templateId,
    readOnly = false,
    hideActions = false,
    hideSettings = false,
}: BacktestViewProps) => {
    const queryClient = useQueryClient();
    const { t, i18n } = useTranslation();
    const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null);
    const [dateRange, setDateRange] = useState<string>("30d");
    const [customStartDate, setCustomStartDate] = useState("");
    const [customEndDate, setCustomEndDate] = useState("");
    const [showCustomDialog, setShowCustomDialog] = useState(false);
    const [runPickerOpen, setRunPickerOpen] = useState(false);
    const [newBacktestOpen, setNewBacktestOpen] = useState(false);
    const [showUsStockPicker, setShowUsStockPicker] = useState(false);
    const [detailTab, setDetailTab] = useState<"trades" | "positions" | "orders" | "signals">("trades");
    const [settings, setSettings] = useState({
        exchange: "okx",
        symbol: "BTC-USDT",
        interval: "1h",
    });
    const [paramValues, setParamValues] = useState<Record<string, string | boolean>>({});
    const exchangeSymbols = useMemo(() => ({
        okx: [
            { value: "BTC-USDT", label: "BTC-USDT" },
            { value: "ETH-USDT", label: "ETH-USDT" },
            { value: "SOL-USDT", label: "SOL-USDT" },
            { value: "BTC-USDT-SWAP", label: t("backtest.symbols.btcUsdtSwap") },
            { value: "ETH-USDT-SWAP", label: t("backtest.symbols.ethUsdtSwap") },
        ],
        binance: [
            { value: "BTCUSDT", label: "BTCUSDT" },
            { value: "ETHUSDT", label: "ETHUSDT" },
            { value: "SOLUSDT", label: "SOLUSDT" },
            { value: "BNBUSDT", label: "BNBUSDT" },
        ],
        us_stock: [],
    }), [t]);
    const baseRanges = [
        { value: "30d", label: "30D" },
        { value: "90d", label: "90D" },
        { value: "180d", label: "180D" },
        { value: "1y", label: "1Y" },
    ];
    const usStockRanges = [
        { value: "2y", label: "2Y" },
        { value: "3y", label: "3Y" },
        { value: "5y", label: "5Y" },
    ];
    const rangeOptions = settings.exchange === "us_stock" ? [...baseRanges, ...usStockRanges] : baseRanges;

    const dataSourceId = mode === "template" ? templateId : strategy?.id;
    const canCreate = mode === "strategy" && !readOnly && !!strategy;
    const showSettingsPanel = canCreate && !hideSettings;
    const showActionButtons = !hideActions;

    const api = useMemo<BacktestApiAdapter>(() => {
        if (mode === "template") {
            return {
                list: (id) => templateBacktestsApi.list(id),
                get: (id, runId) => templateBacktestsApi.get(id, runId),
                getEquityCurve: (id, runId) => templateBacktestsApi.getEquityCurve(id, runId),
                getTrades: (id, runId) => templateBacktestsApi.getTrades(id, runId),
                getOrders: (id, runId) => templateBacktestsApi.getOrders(id, runId),
                getPositions: (id, runId) => templateBacktestsApi.getPositions(id, runId),
                getSignalEvents: (id, runId) => templateBacktestsApi.getSignalEvents(id, runId),
            };
        }
        return {
            list: (id) => backtestsApi.list(id),
            get: (_id, runId) => backtestsApi.get(runId),
            getEquityCurve: (_id, runId) => backtestsApi.getEquityCurve(runId),
            getCandles: (_id, runId) => backtestsApi.getCandles(runId),
            getTrades: (_id, runId) => backtestsApi.getTrades(runId),
            getOrders: (_id, runId) => backtestsApi.getOrders(runId),
            getPositions: (_id, runId) => backtestsApi.getPositions(runId),
            getSignalEvents: (_id, runId) => backtestsApi.getSignalEvents(runId),
            create: (id, req) => backtestsApi.create(id, req),
        };
    }, [mode]);

    const { data: strategyFiles } = useQuery({
        queryKey: ["strategy-files", strategy?.id],
        queryFn: () => (strategy ? strategiesApi.getFiles(strategy.id) : Promise.resolve({ files: [] })),
        enabled: mode === "strategy" && !!strategy,
    });

    const { paramsSchema } = (() => {
        const files = strategyFiles?.files || [];
        const metaFile = files.find((f) => f.name === "strategy_meta.json") || null;
        const schemaFile = files.find((f) => f.name === "params_schema.json") || null;
        let meta: StrategyMeta | null = null;
        let schema: ParamsSchema | null = null;
        if (metaFile?.content) {
            try {
                meta = JSON.parse(metaFile.content) as StrategyMeta;
            } catch {
                meta = null;
            }
        }
        if (meta?.params_schema) {
            schema = meta.params_schema;
        } else if (schemaFile?.content) {
            try {
                schema = JSON.parse(schemaFile.content) as ParamsSchema;
            } catch {
                schema = null;
            }
        }
        return {
            paramsSchema: schema?.params || [],
        };
    })();

    useEffect(() => {
        if (!paramsSchema.length) return;
        setParamValues((prev) => {
            const next = { ...prev };
            for (const param of paramsSchema) {
                if (!param?.name) continue;
                if (next[param.name] === undefined) {
                    const def = param.default;
                    if (typeof def === "boolean") next[param.name] = def;
                    else if (def !== undefined && def !== null) next[param.name] = String(def);
                    else if (param.type === "bool") next[param.name] = false;
                    else next[param.name] = "";
                }
            }
            return next;
        });
    }, [paramsSchema]);

    useEffect(() => {
        if (settings.exchange === "us_stock") {
            setSettings(prev => ({
                ...prev,
                symbol: prev.symbol || "AAPL",
                interval: "1d",
            }));
            setDateRange("1y");
            return;
        }
        const symbols = exchangeSymbols[settings.exchange as keyof typeof exchangeSymbols];
        if (symbols && symbols.length > 0) {
            setSettings(prev => ({ ...prev, symbol: symbols[0].value }));
        }
        if (["2y", "3y", "5y"].includes(dateRange)) {
            setDateRange("1y");
        }
    }, [settings.exchange]);

    const { data: backtests = [], isLoading: isLoadingBacktests } = useQuery({
        queryKey: ["backtests", mode, dataSourceId],
        queryFn: () => (dataSourceId ? api.list(dataSourceId) : Promise.resolve([])),
        enabled: !!dataSourceId,
        refetchInterval: (query) => {
            const rows = (query.state.data as BacktestRun[] | undefined) ?? [];
            return rows.some((run) => run.status === "queued" || run.status === "running") ? 3000 : false;
        },
    });

    useEffect(() => {
        if (backtests.length === 0) return;

        if (!selectedRun) {
            const completedRuns = backtests.filter(r => r.status === "succeeded");
            setSelectedRun(completedRuns[0] ?? backtests[0]);
            return;
        }

        // Keep the currently selected run fresh so status changes (queued -> running -> succeeded/failed)
        // are reflected without needing a manual re-select.
        const updated = backtests.find((r) => r.id === selectedRun.id);
        if (!updated) return;
        if (
            updated.status !== selectedRun.status ||
            updated.started_at !== selectedRun.started_at ||
            updated.finished_at !== selectedRun.finished_at
        ) {
            setSelectedRun(updated);
        }
    }, [backtests, selectedRun]);

    const createBacktestMutation = useMutation({
        mutationFn: (req: BacktestCreateRequest) => {
            if (!canCreate || !dataSourceId || !api.create) {
                return Promise.reject(new Error("backtest_create_disabled"));
            }
            return api.create(dataSourceId, req);
        },
        onSuccess: async (response) => {
            queryClient.invalidateQueries({ queryKey: ["backtests", mode, dataSourceId] });
            if (response.backtest_run) {
                setSelectedRun(response.backtest_run);
                setDetailTab("trades");
            }
            try {
                const job = await jobsApi.waitForCompletion(response.job.id, undefined, 2000, 420000);
                queryClient.invalidateQueries({ queryKey: ["backtests", mode, dataSourceId] });
                if (response.backtest_run) {
                    const updatedRun = await api.get(dataSourceId!, response.backtest_run.id);
                    setSelectedRun(updatedRun);
                    setDetailTab("trades");
                } else if (job.status !== "succeeded") {
                    console.error("Job failed:", job);
                }
            } catch (e) {
                console.error("Job failed:", e);
            }
        },
    });

    const { data: equityCurveData } = useQuery({
        queryKey: ["backtest-equity-curve", mode, dataSourceId, selectedRun?.id],
        queryFn: () => (selectedRun && dataSourceId ? api.getEquityCurve(dataSourceId, selectedRun.id) : Promise.resolve({ data: [] })),
        enabled: !!selectedRun && selectedRun.status === "succeeded" && !!dataSourceId,
    });

    const { data: candlesData } = useQuery({
        queryKey: ["backtest-candles", mode, dataSourceId, selectedRun?.id],
        queryFn: () => {
            if (!(selectedRun && dataSourceId && api.getCandles)) return Promise.resolve({ data: [] as BacktestCandle[] });
            return api.getCandles(dataSourceId, selectedRun.id);
        },
        enabled: !!selectedRun && selectedRun.status === "succeeded" && !!dataSourceId && !!api.getCandles,
    });

    const normalizeTimestampMs = (raw: unknown, fallbackIndex: number): number => {
        const numeric = Number(raw);
        if (Number.isFinite(numeric) && numeric > 0) {
            if (numeric >= 1_000_000_000_000) return Math.floor(numeric);
            if (numeric >= 1_000_000_000) return Math.floor(numeric * 1000);
        }
        return fallbackIndex * 60_000;
    };

    const alignedEquitySeries = useMemo(() => {
        const rawEquity = equityCurveData?.data ?? [];
        if (!rawEquity.length) return [];

        const candles = (candlesData?.data ?? [])
            .map((c, idx) => normalizeTimestampMs(c.timestamp, idx))
            .filter((ts) => Number.isFinite(ts) && ts > 0);

        const equity = rawEquity.map((p, i) => ({
            timestamp: normalizeTimestampMs(p.timestamp, i),
            equity: Number(p.equity ?? 0),
            drawdown: Number(p.drawdown ?? 0),
        }));

        if (!candles.length) {
            return equity;
        }

        if (candles.length === equity.length) {
            return equity.map((p, i) => ({ ...p, timestamp: candles[i] }));
        }

        if (candles.length > equity.length) {
            const offset = candles.length - equity.length;
            return equity.map((p, i) => ({ ...p, timestamp: candles[i + offset] }));
        }

        const offset = equity.length - candles.length;
        return equity.slice(offset).map((p, i) => ({ ...p, timestamp: candles[i] }));
    }, [equityCurveData, candlesData]);

    const drawdownSeries = useMemo(() => {
        const series = alignedEquitySeries.map((point) => ({
            ...point,
            drawdown_neg: -Math.abs(Number(point.drawdown ?? 0)),
        }));
        let maxDrawdown = 0;
        for (const point of series) {
            if (point.drawdown_neg < maxDrawdown) {
                maxDrawdown = point.drawdown_neg;
            }
        }
        return { series, maxDrawdown };
    }, [alignedEquitySeries]);
    const latestDrawdownPct = drawdownSeries.series.length > 0
        ? Math.abs(drawdownSeries.series[drawdownSeries.series.length - 1].drawdown_neg)
        : 0;
    const maxDrawdownPct = Math.abs(drawdownSeries.maxDrawdown);
    const equityBaseline = alignedEquitySeries[0]?.equity ?? 0;
    const candleBarCount = candlesData?.data?.length ?? 0;
    const candleAligned = candleBarCount > 0 && alignedEquitySeries.length > 0;
    const backtestWindowStartMs = useMemo(() => {
        const firstCandle = candlesData?.data?.[0];
        if (!firstCandle) return undefined;
        return normalizeTimestampMs(firstCandle.timestamp, 0);
    }, [candlesData]);
    const backtestWindowEndMs = useMemo(() => {
        const candleList = candlesData?.data ?? [];
        if (candleList.length === 0) return undefined;
        const lastIndex = candleList.length - 1;
        return normalizeTimestampMs(candleList[lastIndex]?.timestamp, lastIndex);
    }, [candlesData]);
    const equityChartData = useMemo(
        () => alignedEquitySeries.map((d) => ({ time: d.timestamp, value: d.equity })),
        [alignedEquitySeries]
    );
    const drawdownChartData = useMemo(
        () => drawdownSeries.series.map((d) => ({ time: d.timestamp, value: d.drawdown_neg })),
        [drawdownSeries.series]
    );
    const equityChartColors = useMemo(() => ({ up: "#16a34a", down: "#dc2626" }), []);
    const drawdownChartColors = useMemo(
        () => ({ line: "#ef4444", areaTop: "rgba(239, 68, 68, 0.25)", areaBottom: "rgba(239, 68, 68, 0)" }),
        []
    );

    const tradesEnabled = !!selectedRun && selectedRun.status === "succeeded" && detailTab === "trades";
    const positionsEnabled = !!selectedRun && selectedRun.status === "succeeded" && detailTab === "positions";
    const ordersEnabled = !!selectedRun && selectedRun.status === "succeeded" && detailTab === "orders";
    const signalsEnabled = !!selectedRun && selectedRun.status === "succeeded" && detailTab === "signals";

    const { data: tradesData, isLoading: isLoadingTrades, isFetching: isFetchingTrades } = useQuery({
        queryKey: ["backtest-trades", mode, dataSourceId, selectedRun?.id],
        queryFn: () => (selectedRun && dataSourceId ? api.getTrades(dataSourceId, selectedRun.id) : Promise.resolve({ trades: [] as BacktestTrade[] })),
        enabled: tradesEnabled,
    });

    const { data: positionsData, isLoading: isLoadingPositions, isFetching: isFetchingPositions } = useQuery({
        queryKey: ["backtest-positions", mode, dataSourceId, selectedRun?.id],
        queryFn: () => (selectedRun && dataSourceId ? api.getPositions(dataSourceId, selectedRun.id) : Promise.resolve({ positions: [] as BacktestPosition[] })),
        enabled: positionsEnabled,
    });

    const { data: ordersData, isLoading: isLoadingOrders, isFetching: isFetchingOrders } = useQuery({
        queryKey: ["backtest-orders", mode, dataSourceId, selectedRun?.id],
        queryFn: () => (selectedRun && dataSourceId ? api.getOrders(dataSourceId, selectedRun.id) : Promise.resolve({ orders: [] as BacktestOrder[] })),
        enabled: ordersEnabled,
    });

    const { data: signalEventsData, isLoading: isLoadingSignalEvents, isFetching: isFetchingSignalEvents } = useQuery({
        queryKey: ["backtest-signal-events", mode, dataSourceId, selectedRun?.id],
        queryFn: () => (selectedRun && dataSourceId ? api.getSignalEvents(dataSourceId, selectedRun.id) : Promise.resolve({ events: [] as BacktestSignalEvent[] })),
        enabled: signalsEnabled,
    });

    const buildParamsPayload = () => {
        if (!paramsSchema.length) return {};
        const payload: Record<string, unknown> = {};
        for (const param of paramsSchema) {
            if (!param?.name) continue;
            const raw = paramValues[param.name];
            if (raw === undefined || raw === "") continue;
            if (param.type === "bool") {
                payload[param.name] = Boolean(raw);
                continue;
            }
            if (param.type === "int") {
                const val = parseInt(String(raw), 10);
                if (Number.isFinite(val)) payload[param.name] = val;
                continue;
            }
            if (param.type === "float") {
                const val = parseFloat(String(raw));
                if (Number.isFinite(val)) payload[param.name] = val;
                continue;
            }
            payload[param.name] = String(raw);
        }
        return payload;
    };

    const handleRunBacktest = () => {
        if (!strategy || !canCreate) return;
        let start_ms: number | undefined;
        let end_ms: number | undefined;
        const now = Date.now();
        if (dateRange === "30d") start_ms = now - 30 * 24 * 60 * 60 * 1000;
        else if (dateRange === "60d") start_ms = now - 60 * 24 * 60 * 60 * 1000;
        else if (dateRange === "90d") start_ms = now - 90 * 24 * 60 * 60 * 1000;
        else if (dateRange === "180d") start_ms = now - 180 * 24 * 60 * 60 * 1000;
        else if (dateRange === "1y") start_ms = now - 365 * 24 * 60 * 60 * 1000;
        else if (dateRange === "2y") start_ms = now - 2 * 365 * 24 * 60 * 60 * 1000;
        else if (dateRange === "3y") start_ms = now - 3 * 365 * 24 * 60 * 60 * 1000;
        else if (dateRange === "5y") start_ms = now - 5 * 365 * 24 * 60 * 60 * 1000;
        else if (dateRange === "custom") {
            start_ms = customStartDate ? new Date(customStartDate).getTime() : undefined;
            end_ms = customEndDate ? new Date(customEndDate).getTime() : undefined;
        }
        // Preset ranges should be deterministic bounded windows.
        if (start_ms !== undefined && end_ms === undefined) {
            end_ms = now;
        }
        createBacktestMutation.mutate({
            dataset: { exchange: settings.exchange, symbol: settings.symbol, interval: settings.interval, start_ms, end_ms },
            params: buildParamsPayload(),
        });
    };

    const formatDurationMs = (ms?: number) => {
        if (!ms || ms <= 0) return t("backtest.duration.na");
        const totalSeconds = Math.floor(ms / 1000);
        const days = Math.floor(totalSeconds / 86400);
        const hours = Math.floor((totalSeconds % 86400) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        if (days > 0) return t("backtest.duration.daysHours", { days, hours });
        if (hours > 0) return t("backtest.duration.hoursMinutes", { hours, minutes });
        return t("backtest.duration.minutes", { minutes });
    };

    const formatFeatureValue = (v: unknown) => {
        if (v === null || v === undefined) return "null";
        if (typeof v === "number") {
            if (!Number.isFinite(v)) return "null";
            return Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
        }
        if (typeof v === "boolean") return v ? "true" : "false";
        if (typeof v === "string") return v.length > 24 ? `${v.slice(0, 24)}…` : v;
        return String(v);
    };

    const formatFeaturesLine = (features?: Record<string, unknown> | null) => {
        if (!features) return "";
        const preferred = ["entry_reason", "exit_reason", "weight_reason", "close", "ret_1", "rsi14", "sma10", "sma30", "fast", "slow", "ema_fast", "ema_slow"];
        const keys = [
            ...preferred.filter((k) => k in features),
            ...Object.keys(features).filter((k) => !preferred.includes(k)).sort(),
        ];
        const pairs: string[] = [];
        for (const k of keys) {
            const v = features[k];
            if (v === null || v === undefined) continue;
            pairs.push(`${k}=${formatFeatureValue(v)}`);
            if (pairs.length >= 5) break;
        }
        return pairs.join(" · ");
    };

    const formatDate = (dateStr: string) =>
        new Date(dateStr).toLocaleString(i18n.language.startsWith("zh") ? "zh-CN" : "en-US", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    const formatShortDate = (dateStr: string) =>
        new Date(dateStr).toLocaleString(i18n.language.startsWith("zh") ? "zh-CN" : "en-US", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    const formatTimestampMs = (timestamp: number) => {
        if (!Number.isFinite(timestamp)) return "";
        const ms = timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp;
        return new Date(ms).toLocaleString(i18n.language.startsWith("zh") ? "zh-CN" : "en-US", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    };
    const formatTimestampLong = (timestamp: number) => {
        if (!Number.isFinite(timestamp)) return "";
        const ms = timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp;
        return new Date(ms).toLocaleString(i18n.language.startsWith("zh") ? "zh-CN" : "en-US", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    };
    const getStatusBadge = (status: string) => {
        const variants: Record<string, "default" | "secondary" | "destructive"> = { succeeded: "default", running: "secondary", failed: "destructive" };
        const labelMap: Record<string, string> = {
            succeeded: t("backtest.succeeded"),
            running: t("backtest.running"),
            failed: t("backtest.failed"),
            queued: t("backtest.queued"),
        };
        return <Badge variant={variants[status] || "secondary"}>{labelMap[status] ?? status}</Badge>;
    };

    const currentSymbols = exchangeSymbols[settings.exchange as keyof typeof exchangeSymbols] || [];
    const intervalOptions = settings.exchange === "us_stock" ? [{ value: "1d", label: t("backtest.intervals.daily") }] : intervals;

    if (mode === "strategy") {
        if (!strategy) {
            return (
                <div className="h-full flex items-center justify-center text-muted-foreground">
                    {t("backtest.selectStrategyFirst")}
                </div>
            );
        }
        if (strategy.chat_status !== "done") {
            return (
                <div className="h-full flex items-center justify-center text-muted-foreground">
                    <div className="text-center">
                        <p className="mb-2">{t("backtest.strategyNotReady")}</p>
                        <p className="text-sm">{t("backtest.strategyNotReadyHint")}</p>
                    </div>
                </div>
            );
        }
    }

    const selectRun = (run: BacktestRun) => {
        setSelectedRun(run);
        setDetailTab("trades");
    };
    return (
        <>
            {showSettingsPanel && (
                <UsStockPickerDialog
                    open={showUsStockPicker}
                    onOpenChange={setShowUsStockPicker}
                    selectedSymbol={settings.symbol}
                    onSelect={(item) => setSettings({ ...settings, symbol: item.symbol })}
                />
            )}
            {showSettingsPanel && (
                <Dialog open={showCustomDialog} onOpenChange={setShowCustomDialog}>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>{t("backtest.customDateTitle")}</DialogTitle>
                            <DialogDescription>{t("backtest.customDateSubtitle")}</DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-4">
                            <div className="space-y-2"><Label>{t("backtest.startDateOptional")}</Label><Input type="datetime-local" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)} /></div>
                            <div className="space-y-2"><Label>{t("backtest.endDateOptional")}</Label><Input type="datetime-local" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)} /></div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setShowCustomDialog(false)}>{t("common.cancel")}</Button>
                            <Button onClick={() => setShowCustomDialog(false)}>{t("backtest.apply")}</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {showActionButtons && (
                <Dialog open={runPickerOpen} onOpenChange={setRunPickerOpen}>
                    <DialogContent className="sm:max-w-xl">
                        <DialogHeader>
                            <DialogTitle>{t("backtest.backtests")}</DialogTitle>
                            <DialogDescription>{t("backtest.selectRun")}</DialogDescription>
                        </DialogHeader>
                        <ScrollArea className="h-[60vh] pr-3">
                            <div className="space-y-2">
                                {isLoadingBacktests ? (
                                    <div className="flex items-center justify-center py-10">
                                        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                                    </div>
                                ) : backtests.length === 0 ? (
                                    <div className="text-center py-10 text-muted-foreground text-sm">{t("backtest.noBacktests")}</div>
                                ) : (
                                    backtests.map((run) => (
                                        <motion.button
                                            key={run.id}
                                            onClick={() => {
                                                selectRun(run);
                                                setRunPickerOpen(false);
                                            }}
                                            whileHover={{ x: 2 }}
                                            className={cn(
                                                "w-full text-left p-3 rounded-lg border transition-all",
                                                selectedRun?.id === run.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted",
                                            )}
                                        >
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="font-medium text-sm text-foreground">
                                                    {t("backtest.runLabel", { id: run.id.slice(0, 8) })}
                                                </span>
                                                {getStatusBadge(run.status)}
                                            </div>
                                            <div className="text-xs text-muted-foreground">{formatShortDate(run.created_at)}</div>
                                            {run.status === "succeeded" && run.metrics && (
                                                <div className="mt-2 flex items-center gap-3 text-xs">
                                                    <span className={cn("font-medium", (run.metrics.total_return || 0) >= 0 ? "text-long" : "text-short")}>
                                                        {(run.metrics.total_return || 0) >= 0 ? "+" : ""}
                                                        {(run.metrics.total_return || 0).toFixed(2)}%
                                                    </span>
                                                    <span className="text-muted-foreground">{t("backtest.tradesCount", { count: run.metrics.total_trades || 0 })}</span>
                                                </div>
                                            )}
                                        </motion.button>
                                    ))
                                )}
                            </div>
                        </ScrollArea>
                    </DialogContent>
                </Dialog>
            )}

            {showSettingsPanel && (
                <Dialog open={newBacktestOpen} onOpenChange={setNewBacktestOpen}>
                    <DialogContent className="sm:max-w-xl">
                        <DialogHeader>
                            <DialogTitle>{t("backtest.newBacktest")}</DialogTitle>
                            <DialogDescription>{t("backtest.newBacktestSubtitle")}</DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4">
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                <Select value={settings.exchange} onValueChange={(v) => setSettings({ ...settings, exchange: v })}>
                                <SelectTrigger className="text-xs h-9"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="okx">OKX</SelectItem>
                                    <SelectItem value="binance">Binance</SelectItem>
                                    <SelectItem value="us_stock">{t("backtest.usStockNasdaq")}</SelectItem>
                                </SelectContent>
                            </Select>
                            {settings.exchange === "us_stock" ? (
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="text-xs h-9 justify-start"
                                    onClick={() => setShowUsStockPicker(true)}
                                >
                                    {settings.symbol || t("backtest.selectUsStocks")}
                                </Button>
                            ) : (
                                <Select value={settings.symbol} onValueChange={(v) => setSettings({ ...settings, symbol: v })}>
                                    <SelectTrigger className="text-xs h-9"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {currentSymbols.map((s) => (
                                            <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            )}
                            <Select value={settings.interval} onValueChange={(v) => setSettings({ ...settings, interval: v })}>
                                <SelectTrigger className="text-xs h-9"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {intervalOptions.map((i) => (
                                        <SelectItem key={i.value} value={i.value}>{i.label}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div>
                            <div className="text-xs text-muted-foreground mb-2">{t("backtest.timeRange")}</div>
                            <div className="flex flex-wrap gap-1">
                                {rangeOptions.map((range) => (
                                    <Button
                                        key={range.value}
                                        type="button"
                                        variant={dateRange === range.value ? "default" : "outline"}
                                        size="sm"
                                        onClick={() => setDateRange(range.value)}
                                        className="text-xs h-8 px-2"
                                    >
                                        {range.label}
                                    </Button>
                                ))}
                                <Button
                                    type="button"
                                    variant={dateRange === "custom" ? "default" : "outline"}
                                    size="sm"
                                    onClick={() => { setDateRange("custom"); setShowCustomDialog(true); }}
                                    className="text-xs h-8 px-2"
                                >
                                    {t("backtest.customRange")}
                                </Button>
                            </div>
                        </div>

                        {paramsSchema.length > 0 && (
                            <div>
                                <div className="text-xs text-muted-foreground mb-2">{t("backtest.strategyParameters")}</div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    {paramsSchema.map((param) => {
                                        const value = paramValues[param.name];
                                        if (param.type === "bool") {
                                            return (
                                                <div key={param.name} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2">
                                                    <Checkbox
                                                        checked={Boolean(value)}
                                                        onCheckedChange={(checked) => {
                                                            setParamValues((prev) => ({ ...prev, [param.name]: Boolean(checked) }));
                                                        }}
                                                    />
                                                    <div className="flex flex-col">
                                                        <span className="text-sm text-foreground">{param.name}</span>
                                                        {param.description && (
                                                            <span className="text-xs text-muted-foreground">{param.description}</span>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        }
                                        const isNumber = param.type === "int" || param.type === "float";
                                        return (
                                            <div key={param.name} className="space-y-1.5">
                                                <Label className="text-xs text-muted-foreground">{param.name}</Label>
                                                <Input
                                                    type={isNumber ? "number" : "text"}
                                                    value={typeof value === "boolean" ? "" : value ?? ""}
                                                    min={typeof param.min === "number" ? param.min : undefined}
                                                    max={typeof param.max === "number" ? param.max : undefined}
                                                    step={param.type === "float" ? "0.01" : isNumber ? "1" : undefined}
                                                    onChange={(e) => {
                                                        setParamValues((prev) => ({ ...prev, [param.name]: e.target.value }));
                                                    }}
                                                    className="h-9 text-xs"
                                                />
                                                {param.description && (
                                                    <div className="text-xs text-muted-foreground">{param.description}</div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => setNewBacktestOpen(false)}>{t("common.cancel")}</Button>
                        <Button
                            type="button"
                            onClick={() => {
                                handleRunBacktest();
                                setNewBacktestOpen(false);
                            }}
                            disabled={createBacktestMutation.isPending}
                            className="gap-2"
                        >
                            {createBacktestMutation.isPending ? (<><Loader2 size={16} className="animate-spin" />{t("backtest.runningEllipsis")}</>) : (<><Play size={16} />{t("backtest.runBacktest")}</>)}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            )}

            <div className="h-full flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden">
                {/* Left Sidebar - Backtest List */}
                <div className="w-full border-b border-border bg-card p-4 flex flex-col lg:hidden">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-semibold text-foreground flex items-center gap-2"><History size={16} />{t("backtest.recentBacktests")}</h3>
                        <span className="text-xs text-muted-foreground">{t("backtest.totalCount", { count: backtests.length })}</span>
                    </div>

                    <div className="space-y-2 flex-1 overflow-y-auto mb-4">
                        {isLoadingBacktests ? (<div className="flex items-center justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>)
                            : backtests.length === 0 ? (<div className="text-center py-8 text-muted-foreground text-sm">{t("backtest.noBacktests")}</div>)
                                : (backtests.map((run) => (
                                    <motion.button
                                        key={run.id}
                                        onClick={() => {
                                            selectRun(run);
                                        }}
                                        whileHover={{ x: 2 }}
                                        className={cn("w-full text-left p-3 rounded-lg border transition-all", selectedRun?.id === run.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted")}>
                                        <div className="flex items-center justify-between mb-1">
                                            <span className="font-medium text-sm text-foreground">{t("backtest.runLabel", { id: run.id.slice(0, 8) })}</span>
                                            {getStatusBadge(run.status)}
                                        </div>
                                        <div className="text-xs text-muted-foreground">{formatShortDate(run.created_at)}</div>
                                        {run.status === "succeeded" && run.metrics && (
                                            <div className="mt-2 flex items-center gap-3 text-xs">
                                                <span className={cn("font-medium", (run.metrics.total_return || 0) >= 0 ? "text-long" : "text-short")}>
                                                    {(run.metrics.total_return || 0) >= 0 ? "+" : ""}{(run.metrics.total_return || 0).toFixed(2)}%
                                                </span>
                                                <span className="text-muted-foreground">
                                                    {t("backtest.tradesCount", { count: run.metrics.total_trades || 0 })}
                                                </span>
                                            </div>
                                        )}
                                    </motion.button>
                                )))}
                    </div>

                    {showSettingsPanel && (
                        <div className="border-t border-border pt-4 space-y-3">
                            <h4 className="text-sm font-medium text-foreground">{t("backtest.newBacktest")}</h4>
                            <div className="grid grid-cols-3 gap-2">
                                <Select value={settings.exchange} onValueChange={(v) => setSettings({ ...settings, exchange: v })}>
                                    <SelectTrigger className="text-xs h-8"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="okx">OKX</SelectItem>
                                        <SelectItem value="binance">Binance</SelectItem>
                                        <SelectItem value="us_stock">{t("backtest.usStockNasdaq")}</SelectItem>
                                    </SelectContent>
                                </Select>
                                {settings.exchange === "us_stock" ? (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="text-xs h-8 justify-start"
                                        onClick={() => setShowUsStockPicker(true)}
                                    >
                                        {settings.symbol || t("backtest.selectUsStocks")}
                                    </Button>
                                ) : (
                                    <Select value={settings.symbol} onValueChange={(v) => setSettings({ ...settings, symbol: v })}>
                                        <SelectTrigger className="text-xs h-8"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {currentSymbols.map((s) => (
                                                <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                )}
                                <Select value={settings.interval} onValueChange={(v) => setSettings({ ...settings, interval: v })}>
                                    <SelectTrigger className="text-xs h-8"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {intervalOptions.map((i) => (
                                            <SelectItem key={i.value} value={i.value}>{i.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="flex flex-wrap gap-1">
                                {rangeOptions.map((range) => (
                                    <Button key={range.value} type="button" variant={dateRange === range.value ? "default" : "outline"} size="sm" onClick={() => setDateRange(range.value)} className="text-xs h-7 px-2">{range.label}</Button>
                                ))}
                                <Button type="button" variant={dateRange === "custom" ? "default" : "outline"} size="sm" onClick={() => { setDateRange("custom"); setShowCustomDialog(true); }} className="text-xs h-7 px-2">{t("backtest.customRange")}</Button>
                            </div>
                            <Button onClick={handleRunBacktest} disabled={createBacktestMutation.isPending} className="w-full gap-2">
                                {createBacktestMutation.isPending ? (<><Loader2 size={16} className="animate-spin" />{t("backtest.running")}</>) : (<><Play size={16} />{t("backtest.newBacktest")}</>)}
                            </Button>
                        </div>
                    )}
                </div>

                {/* Right Panel - Backtest Details */}
                <div className="flex-1 flex flex-col min-h-0">
                    {selectedRun ? (
                        <div className="flex-1 p-4 sm:p-6 lg:overflow-y-auto">
                            <div className="max-w-5xl xl:max-w-6xl mx-auto space-y-6">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                    <div>
                                        <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
                                            {t("backtest.runLabel", { id: selectedRun.id.slice(0, 8) })}
                                            {getStatusBadge(selectedRun.status)}
                                        </h2>
                                        <p className="text-sm text-muted-foreground mt-1">{selectedRun.id}</p>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        {showActionButtons && (
                                            <div className="hidden lg:flex items-center gap-2">
                                                <Button variant="outline" size="sm" className="gap-2" onClick={() => setRunPickerOpen(true)}>
                                                    <History size={14} />{t("backtest.backtests")}
                                                </Button>
                                                {showSettingsPanel && (
                                                    <Button size="sm" className="gap-2" onClick={() => setNewBacktestOpen(true)}>
                                                        <Play size={14} />{t("backtest.newBacktest")}
                                                    </Button>
                                                )}
                                            </div>
                                        )}
                                        {showActionButtons && (selectedRun.status === "succeeded" || selectedRun.status === "failed") && onAnalyzeWithAI && (
                                            <Button variant="outline" size="sm" className="gap-2" onClick={() => onAnalyzeWithAI(selectedRun.id)}>
                                                <Sparkles size={14} />{t("backtest.analyzeWithAi")}
                                            </Button>
                                        )}
                                    </div>
                                </div>

                                {selectedRun.status === "succeeded" && selectedRun.metrics ? (
                                    <>
                                        <Readout
                                            items={[
                                                {
                                                    label: t("backtest.metricCards.finalEquity"),
                                                    value: `$${alignedEquitySeries.length > 0 ? alignedEquitySeries[alignedEquitySeries.length - 1].equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "10,000.00"}`,
                                                },
                                                {
                                                    label: t("backtest.metricCards.totalReturn"),
                                                    value: `${(selectedRun.metrics.total_return || 0) >= 0 ? "+" : ""}${(selectedRun.metrics.total_return || 0).toFixed(2)}%`,
                                                    tone: (selectedRun.metrics.total_return || 0) >= 0 ? "long" : "short",
                                                },
                                                {
                                                    label: t("backtest.metricCards.maxDrawdown"),
                                                    value: `${(selectedRun.metrics.max_drawdown || 0).toFixed(2)}%`,
                                                    tone: "short",
                                                },
                                                {
                                                    label: t("backtest.metricCards.sharpeRatio"),
                                                    value: selectedRun.metrics.sharpe_ratio?.toFixed(2) ?? "-",
                                                },
                                            ]}
                                        />
                                        <Card>
                                            <CardHeader className="pb-2"><CardTitle>{t("backtest.summary.title")}</CardTitle></CardHeader>
                                            <CardContent>
                                                <ReadoutList
                                                    items={[
                                                        { label: t("backtest.summary.created"), value: formatDate(selectedRun.created_at) },
                                                        { label: t("backtest.summary.started"), value: backtestWindowStartMs ? formatTimestampLong(backtestWindowStartMs) : "-" },
                                                        { label: t("backtest.summary.finished"), value: backtestWindowEndMs ? formatTimestampLong(backtestWindowEndMs) : "-" },
                                                        { label: t("backtest.summary.trades"), value: String(selectedRun.metrics.total_trades ?? "-") },
                                                        { label: t("backtest.summary.winRate"), value: `${selectedRun.metrics.win_rate?.toFixed(1) ?? "-"}%` },
                                                    ]}
                                                />
                                            </CardContent>
                                        </Card>
                                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                            <Card><CardHeader className="pb-2"><CardTitle className="text-base flex items-center justify-between gap-2"><span>{t("backtest.charts.equityCurve")}</span><span className="text-[11px] font-normal text-muted-foreground">{candleAligned ? `timeline: candles (${candleBarCount} bars)` : "timeline: equity"}</span></CardTitle></CardHeader><CardContent>
                                                {alignedEquitySeries.length > 0 ? (
                                                    <div className="h-64">
                                                        <TradingViewChart
                                                            data={equityChartData}
                                                            chartType="baseline"
                                                            baselineValue={equityBaseline}
                                                            colors={equityChartColors}
                                                            pricePrecision={2}
                                                            height={256}
                                                        />
                                                    </div>
                                                ) : (<div className="h-64 bg-muted rounded-lg flex items-center justify-center text-muted-foreground"><p className="text-sm">{t("backtest.charts.noEquity")}</p></div>)}
                                            </CardContent></Card>
                                            <Card><CardHeader className="pb-2"><CardTitle className="text-base flex items-center justify-between gap-2"><span>{t("backtest.charts.drawdown")}</span><span className="flex items-center gap-2"><span className="text-[11px] font-normal text-short">DD {latestDrawdownPct.toFixed(2)}% | Max {maxDrawdownPct.toFixed(2)}%</span><span className="text-[11px] font-normal text-muted-foreground">{candleAligned ? `timeline: candles (${candleBarCount} bars)` : "timeline: equity"}</span></span></CardTitle></CardHeader><CardContent>
                                                {drawdownSeries.series.length > 0 ? (
                                                    <div className="h-64">
                                                        <TradingViewChart
                                                            data={drawdownChartData}
                                                            chartType="area"
                                                            colors={drawdownChartColors}
                                                            pricePrecision={2}
                                                            height={256}
                                                        />
                                                    </div>
                                                ) : (<div className="h-64 bg-muted rounded-lg flex items-center justify-center text-muted-foreground"><p className="text-sm">{t("backtest.charts.noDrawdown")}</p></div>)}
                                            </CardContent></Card>
                                        </div>
                                        <Card>
                                            <CardHeader className="pb-2">
                                                <CardTitle className="text-base flex items-center justify-between gap-3">
                                                    <span>{t("backtest.execution.title")}</span>
                                                    <span className="text-xs text-muted-foreground font-normal">
                                                        {t("backtest.execution.subtitle")}
                                                    </span>
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <Tabs value={detailTab} onValueChange={(v) => setDetailTab(v as "trades" | "positions" | "orders" | "signals")}>
                                                    <div className="overflow-x-auto pb-1">
                                                        <TabsList className="w-max min-w-full justify-start">
                                                            <TabsTrigger value="trades" className="gap-1 whitespace-nowrap text-xs sm:text-sm">
                                                            {t("backtest.tabs.trades")}
                                                            <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px] sm:h-5 sm:px-1.5 sm:text-xs">
                                                                {selectedRun.metrics?.total_trades ?? (tradesData?.trades.length ?? 0)}
                                                            </Badge>
                                                        </TabsTrigger>
                                                        <TabsTrigger value="signals" className="gap-1 whitespace-nowrap text-xs sm:text-sm">
                                                            {t("backtest.tabs.signals")}
                                                            <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px] sm:h-5 sm:px-1.5 sm:text-xs">
                                                                {signalEventsData?.events.length ?? "…"}
                                                            </Badge>
                                                        </TabsTrigger>
                                                        <TabsTrigger value="positions" className="gap-1 whitespace-nowrap text-xs sm:text-sm">
                                                            {t("backtest.tabs.positions")}
                                                            <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px] sm:h-5 sm:px-1.5 sm:text-xs">
                                                                {positionsData?.positions.length ?? "…"}
                                                            </Badge>
                                                        </TabsTrigger>
                                                        <TabsTrigger value="orders" className="gap-1 whitespace-nowrap text-xs sm:text-sm">
                                                            {t("backtest.tabs.orders")}
                                                            <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px] sm:h-5 sm:px-1.5 sm:text-xs">
                                                                {ordersData?.orders.length ?? "…"}
                                                            </Badge>
                                                        </TabsTrigger>
                                                        </TabsList>
                                                    </div>

                                                    <TabsContent value="trades" className="mt-4">
                                                        {(isLoadingTrades || isFetchingTrades) ? (
                                                            <div className="flex items-center justify-center py-10 text-muted-foreground">
                                                                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                                                                {t("backtest.loadingTrades")}
                                                            </div>
                                                        ) : (tradesData && tradesData.trades.length > 0) ? (
                                                            <div className="max-h-[420px] overflow-auto">
                                                                <table className="w-full text-sm">
                                                                    <thead className="sticky top-0 bg-card">
                                                                        <tr className="border-b border-border">
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.trades.side")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.trades.entry")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.trades.exit")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.trades.return")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.trades.pnl")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.trades.hold")}</th>
                                                                        </tr>
                                                                    </thead>
                                                                    <tbody>
                                                                        {tradesData.trades.map((trade, idx) => (
                                                                            <tr key={idx} className="border-b border-border/50">
                                                                                <td className="py-2 px-2">
                                                                                    <span className={cn("inline-flex px-2 py-0.5 rounded text-xs font-medium", trade.side === "long" ? "bg-long/20 text-long" : "bg-short/20 text-short")}>
                                                                                        {trade.side}
                                                                                    </span>
                                                                                </td>
                                                                                <td className="py-2 px-2 text-muted-foreground">{trade.entry_time}</td>
                                                                                <td className="py-2 px-2 text-muted-foreground">{trade.exit_time}</td>
                                                                                <td className={cn("py-2 px-2 text-right font-medium", trade.return_pct >= 0 ? "text-long" : "text-short")}>
                                                                                    {trade.return_pct >= 0 ? "+" : ""}{trade.return_pct.toFixed(2)}%
                                                                                </td>
                                                                                <td className={cn("py-2 px-2 text-right font-medium", trade.pnl >= 0 ? "text-long" : "text-short")}>
                                                                                    {trade.pnl >= 0 ? "+" : ""}{trade.pnl.toFixed(2)}
                                                                                </td>
                                                                                <td className="py-2 px-2 text-right numeric text-muted-foreground">
                                                                                    {trade.holding_time_ms ? formatDurationMs(trade.holding_time_ms) : trade.duration}
                                                                                </td>
                                                                            </tr>
                                                                        ))}
                                                                    </tbody>
                                                                </table>
                                                            </div>
                                                        ) : (
                                                            <div className="text-center py-10 text-muted-foreground text-sm">{t("backtest.empty.trades")}</div>
                                                        )}
                                                    </TabsContent>

                                                    <TabsContent value="signals" className="mt-4">
                                                        {(isLoadingSignalEvents || isFetchingSignalEvents) ? (
                                                            <div className="flex items-center justify-center py-10 text-muted-foreground">
                                                                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                                                                {t("backtest.loadingSignals")}
                                                            </div>
                                                        ) : (signalEventsData && signalEventsData.events.length > 0) ? (
                                                            <div className="max-h-[420px] overflow-auto">
                                                                <table className="w-full text-sm">
                                                                    <thead className="sticky top-0 bg-card">
                                                                        <tr className="border-b border-border">
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.signals.time")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.signals.type")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.signals.side")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.signals.reason")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.signals.price")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.signals.weight")}</th>
                                                                        </tr>
                                                                    </thead>
                                                                    <tbody>
                                                                        {signalEventsData.events.slice(0, 300).map((ev, idx) => (
                                                                            <tr key={idx} className="border-b border-border/50">
                                                                                <td className="py-2 px-2 text-muted-foreground">{ev.time}</td>
                                                                                <td className="py-2 px-2">
                                                                                    <span className={cn(
                                                                                        "inline-flex px-2 py-0.5 rounded text-xs font-medium",
                                                                                        ev.type === "entry" && "bg-long/20 text-long",
                                                                                        ev.type === "exit" && "bg-short/20 text-short",
                                                                                        ev.type === "flip" && "bg-warn/20 text-warn",
                                                                                        ev.type === "rebalance" && "bg-primary/20 text-primary",
                                                                                    )}>
                                                                                        {ev.type}
                                                                                    </span>
                                                                                </td>
                                                                                <td className="py-2 px-2 text-muted-foreground">{ev.side}</td>
                                                                                <td className="py-2 px-2 text-muted-foreground">
                                                                                    <div className="text-xs">{ev.signal_detail || ev.signal_reason || "-"}</div>
                                                                                    <div className="text-[11px] opacity-70">
                                                                                        {ev.signal_source ? ev.signal_source : ""}{ev.entries_raw !== undefined && ev.entries_raw !== null ? ` · entries=${String(ev.entries_raw)}` : ""}{ev.exits_raw !== undefined && ev.exits_raw !== null ? ` · exits=${String(ev.exits_raw)}` : ""}{ev.target_weight !== undefined && ev.target_weight !== null ? ` · target=${String(ev.target_weight)}` : ""}
                                                                                    </div>
                                                                                    {ev.features && (
                                                                                        <div className="text-[11px] opacity-70 mt-0.5">
                                                                                            {formatFeaturesLine(ev.features)}
                                                                                        </div>
                                                                                    )}
                                                                                </td>
                                                                                <td className="py-2 px-2 text-right numeric text-muted-foreground">{ev.price.toFixed(2)}</td>
                                                                                <td className="py-2 px-2 text-right numeric font-mono text-xs text-muted-foreground">
                                                                                    {ev.weight_from.toFixed(3)}→{ev.weight_to.toFixed(3)}
                                                                                </td>
                                                                            </tr>
                                                                        ))}
                                                                    </tbody>
                                                                </table>
                                                                {signalEventsData.events.length > 300 && (
                                                                    <div className="pt-3 text-xs text-muted-foreground">
                                                                        {t("backtest.showingSignalEvents", { total: signalEventsData.events.length })}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        ) : (
                                                            <div className="text-center py-10 text-muted-foreground text-sm">{t("backtest.empty.signals")}</div>
                                                        )}
                                                    </TabsContent>

                                                    <TabsContent value="positions" className="mt-4">
                                                        {(isLoadingPositions || isFetchingPositions) ? (
                                                            <div className="flex items-center justify-center py-10 text-muted-foreground">
                                                                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                                                                {t("backtest.loadingPositions")}
                                                            </div>
                                                        ) : (positionsData && positionsData.positions.length > 0) ? (
                                                            <div className="max-h-[420px] overflow-auto">
                                                                <table className="w-full text-sm">
                                                                    <thead className="sticky top-0 bg-card">
                                                                        <tr className="border-b border-border">
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.positions.side")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.positions.entry")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.positions.exit")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs" title={t("backtest.tables.positions.qtyHint")}>
                                                                                {t("backtest.tables.positions.qty")}
                                                                            </th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.positions.avgEntry")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.positions.avgExit")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.positions.hold")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.positions.pnl")}</th>
                                                                        </tr>
                                                                    </thead>
                                                                    <tbody>
                                                                        {positionsData.positions.map((pos, idx) => (
                                                                            <tr key={idx} className="border-b border-border/50">
                                                                                <td className="py-2 px-2">
                                                                                    <span className={cn("inline-flex px-2 py-0.5 rounded text-xs font-medium", pos.side === "long" ? "bg-long/20 text-long" : "bg-short/20 text-short")}>
                                                                                        {pos.side}
                                                                                    </span>
                                                                                </td>
                                                                                <td className="py-2 px-2 text-muted-foreground">{pos.entry_time}</td>
                                                                                <td className="py-2 px-2 text-muted-foreground">{pos.exit_time}</td>
                                                                                <td className="py-2 px-2 text-right numeric font-mono text-xs">{(pos.avg_qty ?? pos.max_qty ?? pos.entry_qty).toFixed(6)}</td>
                                                                                <td className="py-2 px-2 text-right numeric text-muted-foreground">{pos.entry_price.toFixed(2)}</td>
                                                                                <td className="py-2 px-2 text-right numeric text-muted-foreground">{pos.exit_price.toFixed(2)}</td>
                                                                                <td className="py-2 px-2 text-right numeric text-muted-foreground">{formatDurationMs(pos.holding_time_ms)}</td>
                                                                                <td className={cn("py-2 px-2 text-right font-medium", pos.pnl >= 0 ? "text-long" : "text-short")}>
                                                                                    {pos.pnl >= 0 ? "+" : ""}{pos.pnl.toFixed(2)}
                                                                                </td>
                                                                            </tr>
                                                                        ))}
                                                                    </tbody>
                                                                </table>
                                                            </div>
                                                        ) : (
                                                            <div className="text-center py-10 text-muted-foreground text-sm">{t("backtest.empty.positions")}</div>
                                                        )}
                                                    </TabsContent>

                                                    <TabsContent value="orders" className="mt-4">
                                                        {(isLoadingOrders || isFetchingOrders) ? (
                                                            <div className="flex items-center justify-center py-10 text-muted-foreground">
                                                                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                                                                {t("backtest.loadingOrders")}
                                                            </div>
                                                        ) : (ordersData && ordersData.orders.length > 0) ? (
                                                            <div className="max-h-[420px] overflow-auto">
                                                                <table className="w-full text-sm">
                                                                    <thead className="sticky top-0 bg-card">
                                                                        <tr className="border-b border-border">
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.orders.time")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.orders.side")}</th>
                                                                            <th className="text-left py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.orders.reason")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.orders.qty")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.orders.price")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.orders.fee")}</th>
                                                                            <th className="text-right py-2 px-2 font-medium text-muted-foreground text-xs">{t("backtest.tables.orders.weight")}</th>
                                                                        </tr>
                                                                    </thead>
                                                                    <tbody>
                                                                        {ordersData.orders.slice(0, 200).map((o, idx) => (
                                                                            <tr key={idx} className="border-b border-border/50">
                                                                                <td className="py-2 px-2 text-muted-foreground">{o.time}</td>
                                                                                <td className="py-2 px-2">
                                                                                    <span className={cn("inline-flex px-2 py-0.5 rounded text-xs font-medium", o.side === "buy" ? "bg-long/20 text-long" : "bg-short/20 text-short")}>
                                                                                        {o.side}
                                                                                    </span>
                                                                                </td>
                                                                                <td className="py-2 px-2 text-muted-foreground">
                                                                                    <div className="text-xs">{o.signal_detail || o.signal_reason || "-"}</div>
                                                                                    <div className="text-[11px] opacity-70">
                                                                                        {o.signal_type ? o.signal_type : ""}{o.signal_source ? ` · ${o.signal_source}` : ""}{o.entries_raw !== undefined && o.entries_raw !== null ? ` · entries=${String(o.entries_raw)}` : ""}{o.exits_raw !== undefined && o.exits_raw !== null ? ` · exits=${String(o.exits_raw)}` : ""}{o.target_weight !== undefined && o.target_weight !== null ? ` · target=${String(o.target_weight)}` : ""}
                                                                                    </div>
                                                                                    {o.features && (
                                                                                        <div className="text-[11px] opacity-70 mt-0.5">
                                                                                            {formatFeaturesLine(o.features)}
                                                                                        </div>
                                                                                    )}
                                                                                </td>
                                                                                <td className="py-2 px-2 text-right numeric font-mono text-xs">{o.qty.toFixed(6)}</td>
                                                                                <td className="py-2 px-2 text-right numeric text-muted-foreground">{o.price.toFixed(2)}</td>
                                                                                <td className="py-2 px-2 text-right numeric text-muted-foreground">{o.fee.toFixed(6)}</td>
                                                                                <td className="py-2 px-2 text-right numeric font-mono text-xs text-muted-foreground">
                                                                                    {o.weight_from.toFixed(3)}→{o.weight_to.toFixed(3)}
                                                                                </td>
                                                                            </tr>
                                                                        ))}
                                                                    </tbody>
                                                                </table>
                                                                {ordersData.orders.length > 200 && (
                                                                    <div className="pt-3 text-xs text-muted-foreground">
                                                                        {t("backtest.showingOrders", { total: ordersData.orders.length })}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        ) : (
                                                            <div className="text-center py-10 text-muted-foreground text-sm">{t("backtest.empty.orders")}</div>
                                                        )}
                                                    </TabsContent>
                                                </Tabs>
                                            </CardContent>
                                        </Card>
                                    </>
                                ) : selectedRun.status === "running" ? (
                                    <Card><CardContent className="py-16"><div className="flex flex-col items-center justify-center gap-4"><Loader2 className="w-12 h-12 animate-spin text-primary" /><div className="text-center"><p className="font-medium text-lg">{t("backtest.state.runningTitle")}</p><p className="text-sm text-muted-foreground mt-1">{t("backtest.state.runningSubtitle")}</p></div></div></CardContent></Card>
                                ) : selectedRun.status === "queued" ? (
                                    <Card><CardContent className="py-16"><div className="flex flex-col items-center justify-center gap-4"><Loader2 className="w-12 h-12 animate-spin text-primary" /><div className="text-center"><p className="font-medium text-lg">{t("backtest.state.queuedTitle")}</p><p className="text-sm text-muted-foreground mt-1">{t("backtest.state.queuedSubtitle")}</p></div></div></CardContent></Card>
                                ) : selectedRun.status === "failed" ? (
                                    <Card><CardContent className="py-12"><div className="text-center"><div className="w-12 h-12 rounded-full bg-short-soft dark:bg-short/20 flex items-center justify-center mx-auto mb-4"><TrendingDown className="w-6 h-6 text-short" /></div><p className="font-medium text-lg text-short">{t("backtest.state.failedTitle")}</p><p className="text-sm text-muted-foreground mt-2">{selectedRun.error_message || t("backtest.state.unknownError")}</p></div></CardContent></Card>
                                ) : null}
                            </div>
                        </div>
                    ) : (
                        <div className="h-full flex items-center justify-center text-muted-foreground">
                            <div className="text-center space-y-3">
                                <p>{t("backtest.empty.selectPrompt")}</p>
                                {showActionButtons && (
                                    <div className="flex items-center justify-center gap-2">
                                        <Button variant="outline" size="sm" className="gap-2" onClick={() => setRunPickerOpen(true)}>
                                            <History size={14} />{t("backtest.backtests")}
                                        </Button>
                                        {showSettingsPanel && (
                                            <Button size="sm" className="gap-2" onClick={() => setNewBacktestOpen(true)}>
                                                <Play size={14} />{t("backtest.newBacktest")}
                                            </Button>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </>
    );
};

export default BacktestView;
