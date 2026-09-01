import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Strategy } from "@/pages/Console";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { SymbolMultiSelect } from "@/components/trading/SymbolMultiSelect";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Play, Pause, Settings, AlertCircle, CheckCircle, Activity,
    ArrowRight, Wallet, Shield, Radio, Sparkles, Code
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { tradingApi, type TradingStatus } from "@/lib/api/trading";
import ExchangeAccountsDialog from "@/components/console/ExchangeAccountsDialog";
import SignalsView from "@/components/console/SignalsView";
import { exchangeAccountsApi, strategiesApi } from "@/lib/api";
import { useTranslation } from "react-i18next";

interface LiveTradingViewProps {
    strategy: Strategy | null;
    onNavigateToPortfolio: () => void;
    onNavigateToChat?: (message?: string) => void;
}

type ConfigStep = "exchange" | "account" | "risk" | "confirm" | "ready";

const intervalOptions = ["1m", "5m", "15m", "1h", "4h", "1d"];

const LiveTradingView = ({ strategy, onNavigateToPortfolio, onNavigateToChat }: LiveTradingViewProps) => {
    const [configStep, setConfigStep] = useState<ConfigStep>("exchange");
    const [isConfigured, setIsConfigured] = useState(false);
    const [isRunning, setIsRunning] = useState(false);
    const [showApiDialog, setShowApiDialog] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [tradingStatus, setTradingStatus] = useState<TradingStatus | null>(null);
    const { t } = useTranslation();

    // Check if strategy has LiveStrategy class
    const { data: liveReadyData, isLoading: isCheckingLiveReady } = useQuery({
        queryKey: ["live-ready", strategy?.id],
        queryFn: () => strategy?.id ? strategiesApi.checkLiveReady(strategy.id) : Promise.resolve(null),
        enabled: !!strategy?.id,
    });

    const liveGeneratePrompt = t("liveTradingView.generatePrompt");

    const [config, setConfig] = useState({
        exchange: "OKX",
        accountId: "",
        symbols: ["BTC-USDT-SWAP"],
        intervals: ["1m"],
        maxPosition: "10",
        stopLossPercent: "2",

        // Risk control
        leverage: "1",
        maxLeverage: "10",
        maxDailyLoss: "",
        maxDrawdown: "",
        requireStopLoss: true,

        // Trailing stop
        trailingStopEnabled: false,
        trailingActivationPct: "0.5",
        trailingDistancePct: "0.8",

        // Dynamic TP/SL
        dynamicTpslEnabled: false,
        useSupportResistance: true,
        minRiskReward: "1.0",
        fallbackSlPct: "1.0",
        fallbackTpPct: "2.0",
    });

    const { data: accounts = [] } = useQuery({
        queryKey: ["exchange-accounts", strategy?.id],
        queryFn: () => strategy?.id ? exchangeAccountsApi.list(strategy.id) : Promise.resolve([]),
        enabled: !!strategy?.id,
    });

    const selectedAccount = accounts.find((account) => account.id === config.accountId) || null;
    const filteredAccounts = accounts.filter((account) => account.exchange === config.exchange.toLowerCase());

    useEffect(() => {
        if (!config.accountId && accounts.length > 0) {
            setConfig(prev => ({ ...prev, accountId: accounts[0].id }));
        }
    }, [accounts, config.accountId]);

    // Load existing config on mount
    useEffect(() => {
        if (strategy?.id) {
            loadTradingConfig();
        }
    }, [strategy?.id]);

    // Poll trading status when running
    useEffect(() => {
        if (!isRunning || !strategy?.id) return;

        const pollStatus = async () => {
            try {
                const status = await tradingApi.getStatus(strategy.id);
                setTradingStatus(status);
                setIsRunning(status.is_trading);
            } catch (err) {
                console.error("Failed to poll trading status:", err);
            }
        };

        pollStatus();
        const interval = setInterval(pollStatus, 5000); // Poll every 5 seconds

        return () => clearInterval(interval);
    }, [isRunning, strategy?.id]);

    const loadTradingConfig = async () => {
        if (!strategy?.id) return;

        try {
            const existingConfig = await tradingApi.getConfig(strategy.id);
            if (existingConfig) {
                setConfig(prev => ({
                    ...prev,
                    exchange: existingConfig.exchange.toUpperCase(),
                    symbols: existingConfig.symbols?.length ? existingConfig.symbols : [existingConfig.symbol],
                    intervals: existingConfig.intervals?.length ? existingConfig.intervals : ["1m"],
                    accountId: existingConfig.account_id || prev.accountId,
                    maxPosition: existingConfig.max_position_pct.toString(),
                    stopLossPercent: existingConfig.stop_loss_pct.toString(),

                    // Risk control
                    leverage: (existingConfig.leverage || 1).toString(),
                    maxLeverage: (existingConfig.max_leverage || 10).toString(),
                    maxDailyLoss: existingConfig.max_daily_loss_pct ? existingConfig.max_daily_loss_pct.toString() : "",
                    maxDrawdown: existingConfig.max_drawdown_pct ? existingConfig.max_drawdown_pct.toString() : "",
                    requireStopLoss: existingConfig.require_stop_loss ?? true,

                    // Trailing stop
                    trailingStopEnabled: existingConfig.trailing_stop_enabled || false,
                    trailingActivationPct: ((existingConfig.trailing_activation_pct || 0.005) * 100).toString(),
                    trailingDistancePct: ((existingConfig.trailing_distance_pct || 0.008) * 100).toString(),

                    // Dynamic TP/SL
                    dynamicTpslEnabled: existingConfig.dynamic_tpsl_enabled || false,
                    useSupportResistance: existingConfig.use_support_resistance ?? true,
                    minRiskReward: (existingConfig.min_risk_reward || 1.0).toString(),
                    fallbackSlPct: ((existingConfig.fallback_sl_pct || 0.01) * 100).toString(),
                    fallbackTpPct: ((existingConfig.fallback_tp_pct || 0.02) * 100).toString(),
                }));
                setIsConfigured(true);
                setConfigStep("ready");

                // Load trading status
                const status = await tradingApi.getStatus(strategy.id);
                setTradingStatus(status);
                setIsRunning(status.is_trading);
            }
        } catch (err) {
            // Config doesn't exist yet, that's ok
            console.log("No existing trading config");
        }
    };

    const handleStartTrading = async () => {
        if (!strategy?.id) return;
        if (!config.accountId) {
            setError(t("liveTradingView.errors.selectAccount"));
            return;
        }
        if (!config.symbols.length || !config.intervals.length) {
            setError(t("liveTradingView.errors.selectSymbolInterval"));
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            await tradingApi.startTrading(strategy.id, config.accountId);
            setIsRunning(true);
        } catch (err) {
            setError(err instanceof Error ? err.message : t("liveTradingView.errors.startFailed"));
        } finally {
            setIsLoading(false);
        }
    };

    const handleStopTrading = async () => {
        if (!strategy?.id) return;

        setIsLoading(true);
        setError(null);

        try {
            await tradingApi.stopTrading(strategy.id);
            setIsRunning(false);
        } catch (err) {
            setError(err instanceof Error ? err.message : t("liveTradingView.errors.stopFailed"));
        } finally {
            setIsLoading(false);
        }
    };

    const handleCompleteConfig = async () => {
        if (!strategy?.id) return;
        if (!config.accountId) {
            setError(t("liveTradingView.errors.selectAccount"));
            return;
        }
        if (!config.symbols.length || !config.intervals.length) {
            setError(t("liveTradingView.errors.selectSymbolInterval"));
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            // Save config to backend
            await tradingApi.createConfig(strategy.id, {
                exchange: config.exchange.toLowerCase(),
                symbol: config.symbols[0],
                symbols: config.symbols,
                intervals: config.intervals,
                account_id: config.accountId,
                max_position_pct: parseFloat(config.maxPosition),
                stop_loss_pct: parseFloat(config.stopLossPercent),

                // Risk control
                leverage: parseInt(config.leverage),
                max_leverage: parseInt(config.maxLeverage),
                max_daily_loss_pct: config.maxDailyLoss ? parseFloat(config.maxDailyLoss) : undefined,
                max_drawdown_pct: config.maxDrawdown ? parseFloat(config.maxDrawdown) : undefined,
                require_stop_loss: config.requireStopLoss,

                // Trailing stop
                trailing_stop_enabled: config.trailingStopEnabled,
                trailing_activation_pct: parseFloat(config.trailingActivationPct) / 100,
                trailing_distance_pct: parseFloat(config.trailingDistancePct) / 100,

                // Dynamic TP/SL
                dynamic_tpsl_enabled: config.dynamicTpslEnabled,
                use_support_resistance: config.useSupportResistance,
                min_risk_reward: parseFloat(config.minRiskReward),
                fallback_sl_pct: parseFloat(config.fallbackSlPct) / 100,
                fallback_tp_pct: parseFloat(config.fallbackTpPct) / 100,
            });

            setIsConfigured(true);
            setConfigStep("ready");

            setConfig(prev => ({ ...prev }));
        } catch (err) {
            setError(err instanceof Error ? err.message : t("liveTradingView.errors.saveFailed"));
        } finally {
            setIsLoading(false);
        }
    };

    const toggleInterval = (interval: string, checked: boolean) => {
        setConfig(prev => {
            const next = checked
                ? Array.from(new Set([...prev.intervals, interval]))
                : prev.intervals.filter(item => item !== interval);
            return { ...prev, intervals: next };
        });
    };

    // Show upgrade prompt if strategy doesn't have LiveStrategy class
    if (!isCheckingLiveReady && liveReadyData && !liveReadyData.is_live_ready && liveReadyData.strategy_exists) {
        return (
            <div className="h-full overflow-auto p-6">
                <div className="max-w-2xl mx-auto">
                    <Card className="border-amber-500/30 bg-amber-500/5">
                        <CardHeader className="text-center pb-4">
                            <div className="w-16 h-16 rounded-2xl bg-amber-500/10 flex items-center justify-center mx-auto mb-4">
                                <Code className="w-8 h-8 text-amber-500" />
                            </div>
                            <CardTitle className="text-xl">{t("liveTradingView.upgrade.title")}</CardTitle>
                            <CardDescription className="text-base">
                                {t("liveTradingView.upgrade.subtitle")}
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="p-4 bg-muted/30 rounded-lg space-y-2">
                                <div className="flex items-center gap-2 text-sm">
                                    <CheckCircle className="w-4 h-4 text-green-500" />
                                    <span>
                                        {t("liveTradingView.upgrade.hasSignals")}
                                        <code className="text-xs bg-muted px-1 py-0.5 rounded">generate_signals()</code>
                                    </span>
                                </div>
                                <div className="flex items-center gap-2 text-sm">
                                    <AlertCircle className="w-4 h-4 text-amber-500" />
                                    <span>
                                        {t("liveTradingView.upgrade.missingLive")}
                                        <code className="text-xs bg-muted px-1 py-0.5 rounded">LiveStrategy</code>
                                    </span>
                                </div>
                            </div>
                            <Button
                                className="w-full gap-2"
                                onClick={() => {
                                    if (onNavigateToChat) {
                                        onNavigateToChat(JSON.stringify({ type: "live_generate", prompt: liveGeneratePrompt }));
                                    }
                                }}
                            >
                                <Sparkles className="w-4 h-4" />
                                {t("liveTradingView.upgrade.enable")}
                            </Button>
                            <div className="text-xs text-center text-muted-foreground space-y-1">
                                <p>{t("liveTradingView.upgrade.note")}</p>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        );
    }

    // Configuration wizard view
    if (!isConfigured) {
        return (
            <div className="h-full overflow-auto p-6">
                <div className="max-w-2xl mx-auto space-y-6">
                    {/* Header */}
                    <div className="text-center mb-8">
                        <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                            <Radio className="w-8 h-8 text-primary" />
                        </div>
                        <h2 className="text-2xl font-bold text-foreground">{t("liveTradingView.config.title")}</h2>
                        <p className="text-muted-foreground mt-2">{t("liveTradingView.config.subtitle")}</p>
                    </div>

                    {/* Step Indicator */}
                    <div className="flex items-center justify-center gap-2 mb-8">
                        {["exchange", "account", "risk", "confirm"].map((step, idx) => (
                            <div key={step} className="flex items-center">
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${configStep === step ? "bg-primary text-primary-foreground" :
                                    ["exchange", "account", "risk", "confirm"].indexOf(configStep) > idx ? "bg-green-500 text-white" :
                                        "bg-muted text-muted-foreground"
                                    }`}>
                                    {["exchange", "account", "risk", "confirm"].indexOf(configStep) > idx ? "✓" : idx + 1}
                                </div>
                                {idx < 3 && <div className="w-12 h-0.5 bg-muted mx-1" />}
                            </div>
                        ))}
                    </div>

                    {/* Step 1: Exchange Selection */}
                    {configStep === "exchange" && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Wallet className="w-5 h-5 text-primary" />
                                    {t("liveTradingView.steps.exchangeTitle")}
                                </CardTitle>
                                <CardDescription>{t("liveTradingView.steps.exchangeDesc")}</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid gap-3">
                                    <button
                                        onClick={() => setConfig({ ...config, exchange: "OKX", accountId: "" })}
                                        className={`p-4 rounded-lg border-2 text-left transition-all ${
                                            config.exchange === "OKX"
                                                ? "border-primary bg-primary/5"
                                                : "border-border hover:border-primary/50"
                                        }`}
                                    >
                                        <div className="font-medium">OKX</div>
                                        <div className="text-sm text-muted-foreground">
                                            {t("liveTradingView.exchange.okxSupport")}
                                        </div>
                                    </button>
                                </div>
                                <Button onClick={() => setConfigStep("account")} className="w-full gap-2">
                                    {t("common.next")} <ArrowRight size={16} />
                                </Button>
                            </CardContent>
                        </Card>
                    )}

                    {/* Step 2: Exchange Account */}
                    {configStep === "account" && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Wallet className="w-5 h-5 text-primary" />
                                    {t("liveTradingView.steps.accountTitle")}
                                </CardTitle>
                                <CardDescription>{t("liveTradingView.steps.accountDesc")}</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="space-y-2">
                                    <Label>{t("liveTradingView.labels.account")}</Label>
                                    <Select
                                        value={config.accountId}
                                        onValueChange={(v) => setConfig({ ...config, accountId: v })}
                                    >
                                        <SelectTrigger>
                                            <SelectValue placeholder={t("liveTradingView.labels.selectAccount")} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {filteredAccounts.map((account) => (
                                                <SelectItem key={account.id} value={account.id}>
                                                    {account.name} · {account.exchange.toUpperCase()}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <ExchangeAccountsDialog strategyId={strategy?.id || ""}>
                                    <Button variant="outline" className="w-full gap-2">
                                        {t("liveTradingView.actions.manageAccounts")}
                                    </Button>
                                </ExchangeAccountsDialog>
                                <div className="p-3 bg-yellow-500/10 rounded-lg text-sm text-yellow-600 flex items-start gap-2">
                                    <AlertCircle size={16} className="mt-0.5 shrink-0" />
                                    <span>{t("liveTradingView.warnings.apiPermissions")}</span>
                                </div>
                                <div className="flex gap-2">
                                    <Button
                                        variant="outline"
                                        onClick={() => setConfigStep("exchange")}
                                        className="flex-1"
                                        disabled={isLoading}
                                    >
                                        {t("common.back")}
                                    </Button>
                                    <Button
                                        onClick={() => setConfigStep("risk")}
                                        className="flex-1 gap-2"
                                        disabled={isLoading || !config.accountId}
                                    >
                                        {t("common.next")} <ArrowRight size={16} />
                                    </Button>
                                </div>
                                {error && (
                                    <div className="p-3 bg-red-500/10 rounded-lg text-sm text-red-600">
                                        {error}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {/* Step 3: Risk Management */}
                    {configStep === "risk" && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Shield className="w-5 h-5 text-primary" />
                                    {t("liveTradingView.risk.title")}
                                </CardTitle>
                                <CardDescription>{t("liveTradingView.risk.subtitle")}</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                {/* Basic Settings */}
                                <div className="space-y-4">
                                    <h3 className="font-medium text-sm">{t("liveTradingView.risk.basic")}</h3>
                                    <SymbolMultiSelect
                                        value={config.symbols}
                                        onChange={(symbols) => setConfig({ ...config, symbols })}
                                        disabled={isLoading}
                                        maxSelections={10}
                                    />
                                    <div className="space-y-2">
                                        <Label>{t("liveTradingView.risk.intervals")}</Label>
                                        <div className="grid grid-cols-3 gap-2">
                                            {intervalOptions.map((interval) => (
                                                <label key={interval} className="flex items-center gap-2 text-sm">
                                                    <Checkbox
                                                        checked={config.intervals.includes(interval)}
                                                        onCheckedChange={(value) => toggleInterval(interval, Boolean(value))}
                                                    />
                                                    {interval}
                                                </label>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="space-y-2">
                                            <Label>{t("liveTradingView.risk.leverage")}</Label>
                                            <Input
                                                type="number"
                                                min="1"
                                                max="125"
                                                value={config.leverage}
                                                onChange={(e) => setConfig({ ...config, leverage: e.target.value })}
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>{t("liveTradingView.risk.maxLeverage")}</Label>
                                            <Input
                                                type="number"
                                                min="1"
                                                max="125"
                                                value={config.maxLeverage}
                                                onChange={(e) => setConfig({ ...config, maxLeverage: e.target.value })}
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Position & Risk Limits */}
                                <div className="space-y-4">
                                    <h3 className="font-medium text-sm">{t("liveTradingView.risk.positionLimits")}</h3>
                                    <div className="space-y-2">
                                        <Label>{t("liveTradingView.risk.maxPosition")}</Label>
                                        <Input
                                            type="number"
                                            min="1"
                                            max="100"
                                            value={config.maxPosition}
                                            onChange={(e) => setConfig({ ...config, maxPosition: e.target.value })}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>{t("liveTradingView.risk.stopLoss")}</Label>
                                        <Input
                                            type="number"
                                            min="0.5"
                                            max="50"
                                            value={config.stopLossPercent}
                                            onChange={(e) => setConfig({ ...config, stopLossPercent: e.target.value })}
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="space-y-2">
                                            <Label>
                                                {t("liveTradingView.risk.maxDailyLoss")}
                                                <span className="text-xs text-muted-foreground"> {t("common.optional")}</span>
                                            </Label>
                                            <Input
                                                type="number"
                                                placeholder={t("liveTradingView.risk.unlimitedPlaceholder")}
                                                value={config.maxDailyLoss}
                                                onChange={(e) => setConfig({ ...config, maxDailyLoss: e.target.value })}
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>
                                                {t("liveTradingView.risk.maxDrawdown")}
                                                <span className="text-xs text-muted-foreground"> {t("common.optional")}</span>
                                            </Label>
                                            <Input
                                                type="number"
                                                placeholder={t("liveTradingView.risk.unlimitedPlaceholder")}
                                                value={config.maxDrawdown}
                                                onChange={(e) => setConfig({ ...config, maxDrawdown: e.target.value })}
                                            />
                                        </div>
                                    </div>
                                    <div className="flex items-center space-x-2">
                                        <Checkbox
                                            id="requireStopLoss"
                                            checked={config.requireStopLoss}
                                            onCheckedChange={(checked) => setConfig({ ...config, requireStopLoss: checked as boolean })}
                                        />
                                        <label htmlFor="requireStopLoss" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                                            {t("liveTradingView.risk.requireStopLoss")}
                                        </label>
                                    </div>
                                </div>

                                {/* Trailing Stop */}
                                <div className="space-y-4 p-4 bg-muted/30 rounded-lg">
                                    <div className="flex items-center justify-between">
                                        <h3 className="font-medium text-sm">{t("liveTradingView.risk.trailingStop")}</h3>
                                        <Checkbox
                                            id="trailingStop"
                                            checked={config.trailingStopEnabled}
                                            onCheckedChange={(checked) => setConfig({ ...config, trailingStopEnabled: checked as boolean })}
                                        />
                                    </div>
                                    {config.trailingStopEnabled && (
                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="space-y-2">
                                                <Label>{t("liveTradingView.risk.trailingActivation")}</Label>
                                                <Input
                                                    type="number"
                                                    step="0.1"
                                                    value={config.trailingActivationPct}
                                                    onChange={(e) => setConfig({ ...config, trailingActivationPct: e.target.value })}
                                                />
                                                <p className="text-xs text-muted-foreground">{t("liveTradingView.risk.trailingActivationHint")}</p>
                                            </div>
                                            <div className="space-y-2">
                                                <Label>{t("liveTradingView.risk.trailingDistance")}</Label>
                                                <Input
                                                    type="number"
                                                    step="0.1"
                                                    value={config.trailingDistancePct}
                                                    onChange={(e) => setConfig({ ...config, trailingDistancePct: e.target.value })}
                                                />
                                                <p className="text-xs text-muted-foreground">{t("liveTradingView.risk.trailingDistanceHint")}</p>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Dynamic TP/SL */}
                                <div className="space-y-4 p-4 bg-muted/30 rounded-lg">
                                    <div className="flex items-center justify-between">
                                        <h3 className="font-medium text-sm">{t("liveTradingView.risk.dynamicTpSl")}</h3>
                                        <Checkbox
                                            id="dynamicTpsl"
                                            checked={config.dynamicTpslEnabled}
                                            onCheckedChange={(checked) => setConfig({ ...config, dynamicTpslEnabled: checked as boolean })}
                                        />
                                    </div>
                                    {config.dynamicTpslEnabled && (
                                        <div className="space-y-3">
                                            <div className="flex items-center space-x-2">
                                                <Checkbox
                                                    id="useSupportResistance"
                                                    checked={config.useSupportResistance}
                                                    onCheckedChange={(checked) => setConfig({ ...config, useSupportResistance: checked as boolean })}
                                                />
                                                <label htmlFor="useSupportResistance" className="text-sm leading-none">
                                                    {t("liveTradingView.risk.useSupportResistance")}
                                                </label>
                                            </div>
                                            <div className="space-y-2">
                                                <Label>{t("liveTradingView.risk.minRiskReward")}</Label>
                                                <Input
                                                    type="number"
                                                    step="0.1"
                                                    min="0.1"
                                                    value={config.minRiskReward}
                                                    onChange={(e) => setConfig({ ...config, minRiskReward: e.target.value })}
                                                />
                                            </div>
                                            <div className="grid grid-cols-2 gap-3">
                                                <div className="space-y-2">
                                                    <Label>{t("liveTradingView.risk.fallbackStop")}</Label>
                                                    <Input
                                                        type="number"
                                                        step="0.1"
                                                        value={config.fallbackSlPct}
                                                        onChange={(e) => setConfig({ ...config, fallbackSlPct: e.target.value })}
                                                    />
                                                </div>
                                                <div className="space-y-2">
                                                    <Label>{t("liveTradingView.risk.fallbackTakeProfit")}</Label>
                                                    <Input
                                                        type="number"
                                                        step="0.1"
                                                        value={config.fallbackTpPct}
                                                        onChange={(e) => setConfig({ ...config, fallbackTpPct: e.target.value })}
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="flex gap-2">
                                    <Button variant="outline" onClick={() => setConfigStep("account")} className="flex-1">
                                        {t("common.back")}
                                    </Button>
                                    <Button onClick={() => setConfigStep("confirm")} className="flex-1 gap-2">
                                        {t("common.next")} <ArrowRight size={16} />
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Step 4: Confirm */}
                    {configStep === "confirm" && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <CheckCircle className="w-5 h-5 text-primary" />
                                    {t("liveTradingView.confirm.title")}
                                </CardTitle>
                                <CardDescription>{t("liveTradingView.confirm.subtitle")}</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="space-y-3 p-4 bg-muted/30 rounded-lg">
                                    <div className="flex justify-between"><span className="text-muted-foreground">{t("liveTradingView.confirm.exchange")}</span><span className="font-medium">{config.exchange}</span></div>
                                    <div className="flex justify-between"><span className="text-muted-foreground">{t("liveTradingView.confirm.symbols")}</span><span className="font-medium">{config.symbols.join(", ")}</span></div>
                                    <div className="flex justify-between"><span className="text-muted-foreground">{t("liveTradingView.confirm.intervals")}</span><span className="font-medium">{config.intervals.join(", ")}</span></div>
                                    <div className="flex justify-between"><span className="text-muted-foreground">{t("liveTradingView.confirm.maxPosition")}</span><span className="font-medium">{config.maxPosition}%</span></div>
                                    <div className="flex justify-between"><span className="text-muted-foreground">{t("liveTradingView.confirm.stopLoss")}</span><span className="font-medium">{config.stopLossPercent}%</span></div>
                                    <div className="flex justify-between"><span className="text-muted-foreground">{t("liveTradingView.confirm.apiStatus")}</span><span className="font-medium text-green-500">{t("liveTradingView.confirm.apiConfigured")}</span></div>
                                </div>
                                <div className="flex gap-2">
                                    <Button variant="outline" onClick={() => setConfigStep("risk")} className="flex-1" disabled={isLoading}>
                                        {t("common.back")}
                                    </Button>
                                    <Button onClick={handleCompleteConfig} className="flex-1 bg-green-500 hover:bg-green-600 gap-2" disabled={isLoading}>
                                        {isLoading ? t("liveTradingView.confirm.saving") : <><CheckCircle size={16} /> {t("liveTradingView.confirm.complete")}</>}
                                    </Button>
                                </div>
                                {error && (
                                    <div className="p-3 bg-red-500/10 rounded-lg text-sm text-red-600">
                                        {error}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}
                </div>
            </div>
        );
    }

    // Trading dashboard view (after configuration)
    return (
        <div className="h-full overflow-hidden flex flex-col">
            <Tabs defaultValue="dashboard" className="flex-1 flex flex-col min-h-0">
                <div className="shrink-0 p-6 pb-0">
                    <div className="max-w-4xl mx-auto space-y-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-2xl font-bold text-foreground">{t("liveTradingView.dashboard.title")}</h2>
                                <p className="text-muted-foreground">
                                    {strategy?.name || t("console.defaultUser")} · {config.symbols.join(", ")}
                                </p>
                            </div>
                            <div className="flex items-center gap-3">
                                <Select value={config.accountId} onValueChange={(value) => setConfig({ ...config, accountId: value })}>
                                    <SelectTrigger className="w-52">
                                        <SelectValue placeholder={t("liveTradingView.labels.selectAccount")} />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {filteredAccounts.map((account) => (
                                            <SelectItem key={account.id} value={account.id}>
                                                {account.name} · {account.exchange.toUpperCase()}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <ExchangeAccountsDialog strategyId={strategy?.id || ""}>
                                    <Button variant="outline" size="sm">{t("liveTradingView.actions.manageAccounts")}</Button>
                                </ExchangeAccountsDialog>
                                <div className="flex gap-2">
                                    <Button variant="outline" size="sm" onClick={() => setShowApiDialog(true)} disabled={isLoading}>
                                        <Settings className="w-4 h-4 mr-2" />
                                        {t("common.settings")}
                                    </Button>
                                    {isRunning ? (
                                        <Button size="sm" variant="destructive" onClick={handleStopTrading} disabled={isLoading}>
                                            <Pause className="w-4 h-4 mr-2" />
                                            {isLoading ? t("liveTradingView.dashboard.stopping") : t("liveTradingView.dashboard.stop")}
                                        </Button>
                                    ) : (
                                        <Button size="sm" className="bg-green-500 hover:bg-green-600" onClick={handleStartTrading} disabled={isLoading || !config.accountId}>
                                            <Play className="w-4 h-4 mr-2" />
                                            {isLoading ? t("liveTradingView.dashboard.starting") : t("liveTradingView.dashboard.start")}
                                        </Button>
                                    )}
                                </div>
                            </div>
                        </div>

                        {error && (
                            <div className="p-3 bg-red-500/10 rounded-lg text-sm text-red-600 flex items-start gap-2">
                                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                                <span>{error}</span>
                            </div>
                        )}

                        <div className="flex items-center justify-between border-b border-border">
                            <TabsList className="bg-transparent h-auto p-0 gap-6">
                                <TabsTrigger
                                    value="dashboard"
                                    className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 py-2"
                                >
                                    {t("liveTradingView.tabs.dashboard", { defaultValue: "Dashboard" })}
                                </TabsTrigger>
                                <TabsTrigger
                                    value="signals"
                                    className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 py-2"
                                >
                                    {t("liveTradingView.tabs.signals", { defaultValue: "Signals" })}
                                </TabsTrigger>
                            </TabsList>
                        </div>
                    </div>
                </div>

                <div className="flex-1 overflow-auto min-h-0 bg-muted/10">
                    <TabsContent value="dashboard" className="h-full p-6 mt-0">
                        <div className="max-w-4xl mx-auto space-y-6">
                            <div className="grid md:grid-cols-3 gap-4">
                                <Card>
                                    <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Activity className="w-4 h-4" />{t("liveTradingView.dashboard.status")}</CardTitle></CardHeader>
                                    <CardContent>
                                        <div className="flex items-center gap-2">
                                            <div className={`w-2 h-2 rounded-full ${isRunning ? "bg-green-500 animate-pulse" : "bg-yellow-500"}`} />
                                            <span className="font-medium">{isRunning ? t("liveTradingView.dashboard.running") : t("liveTradingView.dashboard.stopped")}</span>
                                        </div>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="pb-2"><CardTitle className="text-sm">{t("liveTradingView.dashboard.todayPnl")}</CardTitle></CardHeader>
                                    <CardContent>
                                        <span className={`text-2xl font-bold ${(tradingStatus?.active_session?.total_pnl || 0) >= 0 ? "text-green-500" : "text-red-500"
                                            }`}>
                                            {(tradingStatus?.active_session?.total_pnl || 0) >= 0 ? "+" : ""}
                                            ${(tradingStatus?.active_session?.total_pnl || 0).toFixed(2)}
                                        </span>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="pb-2"><CardTitle className="text-sm">{t("liveTradingView.dashboard.tradeCount")}</CardTitle></CardHeader>
                                    <CardContent><span className="text-2xl font-bold">{tradingStatus?.active_session?.total_trades || 0}</span></CardContent>
                                </Card>
                            </div>

                            <Card>
                                <CardHeader><CardTitle>{t("liveTradingView.dashboard.connectionStatus")}</CardTitle></CardHeader>
                                <CardContent className="space-y-3">
                                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                                        <div className="flex items-center gap-3">
                                            <CheckCircle className="w-5 h-5 text-green-500" />
                                            <span>{selectedAccount?.name || t("liveTradingView.labels.account")} · {config.exchange} {t("liveTradingView.dashboard.exchangeLabel")}</span>
                                        </div>
                                        <span className="text-sm text-green-500">{t("liveTradingView.dashboard.connected")}</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                                        <div className="flex items-center gap-3">
                                            <CheckCircle className="w-5 h-5 text-green-500" />
                                            <span>{t("liveTradingView.dashboard.engine")}</span>
                                        </div>
                                        <span className="text-sm text-green-500">{t("liveTradingView.dashboard.ready")}</span>
                                    </div>
                                </CardContent>
                            </Card>

                            <Button onClick={onNavigateToPortfolio} variant="outline" className="w-full">
                                {t("liveTradingView.dashboard.viewPortfolio")}
                            </Button>
                        </div>
                    </TabsContent>

                    <TabsContent value="signals" className="h-full mt-0">
                        <div className="max-w-4xl mx-auto h-full">
                            <SignalsView strategy={strategy} />
                        </div>
                    </TabsContent>
                </div>
            </Tabs>

            {/* Settings Dialog */}
            <Dialog open={showApiDialog} onOpenChange={setShowApiDialog}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{t("liveTradingView.settings.title")}</DialogTitle>
                        <DialogDescription>{t("liveTradingView.settings.subtitle")}</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="flex justify-between"><span>{t("liveTradingView.confirm.exchange")}</span><span className="font-medium">{config.exchange}</span></div>
                        <div className="flex justify-between"><span>{t("liveTradingView.confirm.symbols")}</span><span className="font-medium">{config.symbols.join(", ")}</span></div>
                        <div className="flex justify-between"><span>{t("liveTradingView.confirm.intervals")}</span><span className="font-medium">{config.intervals.join(", ")}</span></div>
                        <div className="flex justify-between"><span>{t("liveTradingView.confirm.maxPosition")}</span><span className="font-medium">{config.maxPosition}%</span></div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => { setIsConfigured(false); setConfigStep("exchange"); setShowApiDialog(false); }}>
                            {t("liveTradingView.settings.reconfigure")}
                        </Button>
                        <Button onClick={() => setShowApiDialog(false)}>{t("common.close")}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};

export default LiveTradingView;
