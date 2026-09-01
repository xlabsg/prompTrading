import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    FileText,
    Search,
    Filter,
    AlertCircle,
    Info,
    AlertTriangle,
    Bug,
    ArrowDown,
    RefreshCw,
    Wifi,
    WifiOff
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuCheckboxItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";


import { tradingLogsApi, LogEntry } from "@/lib/api";
import { Strategy } from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useTranslation } from "react-i18next";

interface LogsViewProps {
    strategy: Strategy;
}

const LogLevelIcon = ({ level }: { level: string }) => {
    switch (level) {
        case "error":
            return <AlertCircle className="w-4 h-4 text-red-500" />;
        case "warning":
            return <AlertTriangle className="w-4 h-4 text-yellow-500" />;
        case "debug":
            return <Bug className="w-4 h-4 text-gray-500" />;
        default:
            return <Info className="w-4 h-4 text-blue-500" />;
    }
};

const LogLevelBadge = ({ level }: { level: string }) => {
    const variants = {
        error: "bg-red-500/10 text-red-600 border-red-500/20",
        warning: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
        info: "bg-blue-500/10 text-blue-600 border-blue-500/20",
        debug: "bg-gray-500/10 text-gray-600 border-gray-500/20",
    };

    return (
        <Badge
            variant="outline"
            className={cn("px-2 py-0.5 text-xs font-medium uppercase", variants[level as keyof typeof variants])}
        >
            {level}
        </Badge>
    );
};

const LogsView = ({ strategy }: LogsViewProps) => {
    const { t, i18n } = useTranslation();
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [filteredLogs, setFilteredLogs] = useState<LogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [selectedLevels, setSelectedLevels] = useState<Set<string>>(new Set(["info", "warning", "error"]));
    const [autoScroll, setAutoScroll] = useState(true);
    const [isConnected, setIsConnected] = useState(false);

    const logsContainerRef = useRef<HTMLDivElement>(null);

    // WebSocket integration
    useWebSocket(`/ws/strategies/${strategy.id}`, {
        enabled: true,
        onConnect: () => setIsConnected(true),
        onDisconnect: () => setIsConnected(false),
        onMessage: (message) => {
            if (message.type === 'log_new' && message.data) {
                const newLog = message.data as LogEntry;
                setLogs(prev => [newLog, ...prev]);
            }
        }
    });

    const fetchLogs = useCallback(async () => {
        try {
            const params = new URLSearchParams();
            if (selectedLevels.size > 0 && selectedLevels.size < 4) {
                Array.from(selectedLevels).forEach(level => {
                    params.append("levels", level);
                });
            }
            params.append("limit", "100");

            const logs = await tradingLogsApi.list(strategy.id, params);
            setLogs(logs);
        } catch (error) {
            console.error("Failed to fetch logs:", error);
        } finally {
            setLoading(false);
        }
    }, [strategy.id, selectedLevels]);

    useEffect(() => {
        fetchLogs();
        const interval = setInterval(fetchLogs, 30000); // Poll every 30 seconds as fallback
        return () => clearInterval(interval);
    }, [fetchLogs]);

    // Filter logs based on search and level
    useEffect(() => {
        let filtered = logs;

        // Filter by selected levels
        if (selectedLevels.size > 0 && selectedLevels.size < 4) {
            filtered = filtered.filter(log => selectedLevels.has(log.level));
        }

        // Filter by search query
        if (searchQuery) {
            const query = searchQuery.toLowerCase();
            filtered = filtered.filter(log =>
                log.message.toLowerCase().includes(query) ||
                JSON.stringify(log.log_metadata || {}).toLowerCase().includes(query)
            );
        }

        setFilteredLogs(filtered);
    }, [logs, searchQuery, selectedLevels]);

    // Auto-scroll: newest logs are at the TOP, so scroll container to top
    useEffect(() => {
        if (!autoScroll) return;
        const el = logsContainerRef.current;
        if (!el) return;
        // Smoothly scroll to top to reveal newest entry first
        el.scrollTo({ top: 0, behavior: "smooth" });
    }, [filteredLogs, autoScroll]);

    const toggleLevel = (level: string) => {
        const newLevels = new Set(selectedLevels);
        if (newLevels.has(level)) {
            newLevels.delete(level);
        } else {
            newLevels.add(level);
        }
        setSelectedLevels(newLevels);
    };

    const formatTimestamp = (timestamp: string) => {
        const date = new Date(timestamp);
        const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";
        const timeStr = date.toLocaleTimeString(locale, {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
        const ms = date.getMilliseconds().toString().padStart(3, "0");
        return `${timeStr}.${ms}`;
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-muted-foreground">{t("logsView.loading")}</div>
            </div>
        );
    }

    if (logs.length === 0) {
        return (
            <div className="h-full flex flex-col items-center justify-center p-8">
                <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mb-6">
                    <FileText className="w-10 h-10 text-primary" />
                </div>
                <h2 className="text-2xl font-bold text-foreground mb-2">{t("logsView.emptyTitle")}</h2>
                <p className="text-muted-foreground text-center max-w-md">
                    {t("logsView.emptySubtitle")}
                </p>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header Controls */}
            <div className="flex items-center gap-3 p-4 border-b border-border bg-card/50">
                {/* Search */}
                <div className="relative flex-1 max-w-md">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                        type="text"
                        placeholder={t("logsView.searchPlaceholder")}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-9"
                    />
                </div>

                {/* Level Filter */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="outline" size="sm" className="gap-2">
                            <Filter className="w-4 h-4" />
                            {t("logsView.levelFilter", { count: selectedLevels.size })}
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                        {["debug", "info", "warning", "error"].map((level) => (
                            <DropdownMenuCheckboxItem
                                key={level}
                                checked={selectedLevels.has(level)}
                                onCheckedChange={() => toggleLevel(level)}
                            >
                                <LogLevelBadge level={level} />
                            </DropdownMenuCheckboxItem>
                        ))}
                    </DropdownMenuContent>
                </DropdownMenu>

                {/* Auto-scroll toggle */}
                <Button
                    variant={autoScroll ? "default" : "outline"}
                    size="sm"
                    onClick={() => setAutoScroll(!autoScroll)}
                    className="gap-2"
                >
                    <ArrowDown className="w-4 h-4" />
                    {t("logsView.autoScroll")}
                </Button>

                {/* Refresh */}
                <Button variant="outline" size="sm" onClick={fetchLogs}>
                    <RefreshCw className="w-4 h-4" />
                </Button>
            </div>

            {/* Logs List */}
            <div
                ref={logsContainerRef}
                className="flex-1 overflow-auto p-4 space-y-1 bg-muted/20 font-mono text-sm"
            >
                {filteredLogs.length === 0 ? (
                    <div className="text-center text-muted-foreground py-8">
                        No logs match your filters
                    </div>
                ) : (
                    filteredLogs.map((log) => (
                        <div
                            key={log.id}
                            className={cn(
                                "flex items-start gap-3 p-2 rounded hover:bg-card/50 transition-colors",
                                log.level === "error" && "bg-red-500/5",
                                log.level === "warning" && "bg-yellow-500/5"
                            )}
                        >
                            <span className="text-muted-foreground text-xs shrink-0 w-20">
                                {formatTimestamp(log.created_at)}
                            </span>
                            <div className="shrink-0">
                                <LogLevelIcon level={log.level} />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="text-foreground break-words">
                                    {log.message}
                                </div>
                                {log.log_metadata && Object.keys(log.log_metadata).length > 0 && (
                                    <details className="mt-1 text-xs text-muted-foreground">
                                        <summary className="cursor-pointer hover:text-foreground">
                                            Metadata
                                        </summary>
                                        <pre className="mt-1 p-2 bg-card/50 rounded overflow-x-auto">
                                            {JSON.stringify(log.log_metadata, null, 2)}
                                        </pre>
                                    </details>
                                )}
                            </div>
                        </div>
                    ))
                )}
            </div>

            {/* Footer Stats */}
            <div className="px-4 py-2 border-t border-border bg-card/50 flex items-center justify-between text-xs text-muted-foreground">
                <div>
                    Showing {filteredLogs.length} of {logs.length} logs
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center space-x-2 border-r border-border pr-4 mr-2">
                        {isConnected ? (
                            <Wifi className="w-3 h-3 text-green-500" />
                        ) : (
                            <WifiOff className="w-3 h-3 text-red-500" />
                        )}
                        <span>{isConnected ? "Real-time" : "Connecting..."}</span>
                    </div>

                    {["error", "warning", "info", "debug"].map((level) => {
                        const count = logs.filter((log) => log.level === level).length;
                        if (count === 0) return null;
                        return (
                            <div key={level} className="flex items-center gap-1">
                                <LogLevelIcon level={level} />
                                <span>{count}</span>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};

export default LogsView;
