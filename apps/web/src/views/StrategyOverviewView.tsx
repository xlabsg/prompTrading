import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Activity, GitBranch, Loader2, Pause, Play, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { backtestsApi, strategiesApi } from "@/lib/api";
import type { BacktestCandle, BacktestSignalEvent, BacktestTrade, BacktestSignalsPayload, Strategy } from "@/lib/types";
import TradingViewChart from "@/components/charts/TradingViewChart";
import StrategyWorkflowGraph, { type WorkflowGraphData } from "@/components/strategy/StrategyWorkflowGraph";

interface StrategyOverviewViewProps {
  strategy: Strategy | null;
  onNavigateToChat?: (message: string) => void;
}

type CandlePoint = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

type TimeframeOption = "auto" | "1d" | "7d" | "30d" | "90d" | "180d" | "365d" | "all";

const CODE_BLOCK_RE = /```([a-zA-Z0-9_+-]+)?\n([\s\S]*?)```/g;

const TIMEFRAME_LABELS: Record<Exclude<TimeframeOption, "auto">, string> = {
  "1d": "1D",
  "7d": "7D",
  "30d": "30D",
  "90d": "90D",
  "180d": "180D",
  "365d": "1Y",
  all: "ALL",
};

const MermaidBlock: React.FC<{ chart: string }> = ({ chart }) => {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "default",
        });
        const id = `overview-mermaid-${Math.random().toString(36).slice(2)}`;
        const result = await mermaid.render(id, chart);
        if (!active) return;
        setSvg(result.svg);
        setError(null);
      } catch (err) {
        if (!active) return;
        setSvg("");
        setError(err instanceof Error ? err.message : "Mermaid render failed");
      }
    })();

    return () => {
      active = false;
    };
  }, [chart]);

  if (error) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive whitespace-pre-wrap">
        Mermaid render error: {error}
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-3 text-xs text-muted-foreground">
        Rendering workflow diagram...
      </div>
    );
  }

  return (
    <div
      className="rounded-md border border-border bg-card p-3 overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};

function toUnixMs(raw: unknown, fallbackIndex: number): number {
  const numeric = Number(raw);
  if (Number.isFinite(numeric) && numeric > 0) {
    if (numeric >= 1_000_000_000_000) return Math.floor(numeric);
    if (numeric >= 1_000_000_000) return Math.floor(numeric * 1000);
    return Math.floor(numeric);
  }
  return fallbackIndex * 60_000;
}

function parseTimeMs(raw: unknown, fallbackIndex: number): number {
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Date.parse(raw);
    if (Number.isFinite(parsed) && parsed > 0) return Math.floor(parsed);
  }
  return toUnixMs(raw, fallbackIndex);
}

function inferMedianBarIntervalMs(points: Array<{ time: number }>): number | null {
  if (!points || points.length < 3) return null;
  const diffs: number[] = [];
  for (let i = 1; i < points.length; i += 1) {
    const diff = Number(points[i].time) - Number(points[i - 1].time);
    if (Number.isFinite(diff) && diff > 0) diffs.push(diff);
  }
  if (!diffs.length) return null;
  diffs.sort((a, b) => a - b);
  return diffs[Math.floor(diffs.length / 2)];
}

function defaultTimeframeByBarInterval(barMs: number | null): Exclude<TimeframeOption, "auto"> {
  if (!barMs || !Number.isFinite(barMs)) return "all";
  if (barMs <= 5 * 60 * 1000) return "1d";
  if (barMs <= 15 * 60 * 1000) return "7d";
  if (barMs <= 60 * 60 * 1000) return "30d";
  if (barMs <= 4 * 60 * 60 * 1000) return "90d";
  if (barMs <= 24 * 60 * 60 * 1000) return "180d";
  return "all";
}

function formatBarTimeframe(barMs: number | null): string {
  if (!barMs || !Number.isFinite(barMs) || barMs <= 0) return "N/A";
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;

  const roundedMinutes = Math.round(barMs / minute);
  const roundedHours = Math.round(barMs / hour);
  const roundedDays = Math.round(barMs / day);
  const roundedWeeks = Math.round(barMs / week);

  if (barMs < hour) return `${Math.max(1, roundedMinutes)}m`;
  if (barMs < day) return `${Math.max(1, roundedHours)}h`;
  if (barMs < week) return `${Math.max(1, roundedDays)}d`;
  return `${Math.max(1, roundedWeeks)}w`;
}

function timeframeDurationMs(timeframe: Exclude<TimeframeOption, "auto" | "all">): number {
  const map: Record<Exclude<TimeframeOption, "auto" | "all">, number> = {
    "1d": 1 * 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
    "90d": 90 * 24 * 60 * 60 * 1000,
    "180d": 180 * 24 * 60 * 60 * 1000,
    "365d": 365 * 24 * 60 * 60 * 1000,
  };
  return map[timeframe];
}

function toFiniteNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function extractCodeBlocksByLanguage(markdown: string, lang: string): string[] {
  const found: string[] = [];
  CODE_BLOCK_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CODE_BLOCK_RE.exec(markdown)) !== null) {
    const language = (match[1] || "").trim().toLowerCase();
    if (language === lang.toLowerCase()) {
      found.push((match[2] || "").trim());
    }
  }
  return found;
}

function parseWorkflowGraphData(raw: unknown): WorkflowGraphData | null {
  if (!raw || typeof raw !== "object") return null;
  const graph = raw as { nodes?: unknown[]; edges?: unknown[] };
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return null;

  const nodes = graph.nodes
    .map((node) => {
      if (!node || typeof node !== "object") return null;
      const n = node as Record<string, unknown>;
      const id = String(n.id || "");
      if (!id) return null;
      return {
        id,
        label: String(n.label || id),
        type: String(n.type || "process"),
      };
    })
    .filter((node): node is NonNullable<typeof node> => Boolean(node));

  const edges = graph.edges
    .map((edge) => {
      if (!edge || typeof edge !== "object") return null;
      const e = edge as Record<string, unknown>;
      const source = String(e.source || "");
      const target = String(e.target || "");
      if (!source || !target) return null;
      return {
        id: String(e.id || `${source}->${target}`),
        source,
        target,
        label: e.label != null ? String(e.label) : "",
        weight: Number(e.weight || 0),
      };
    })
    .filter((edge): edge is NonNullable<typeof edge> => Boolean(edge));

  if (!nodes.length || !edges.length) return null;
  return { nodes, edges };
}

function parseG6Graphs(markdown: string): WorkflowGraphData[] {
  const blocks = extractCodeBlocksByLanguage(markdown, "g6");
  const results: WorkflowGraphData[] = [];
  for (const block of blocks) {
    try {
      const parsed = JSON.parse(block);
      const graph = parseWorkflowGraphData(parsed);
      if (graph) results.push(graph);
    } catch {
      continue;
    }
  }
  return results;
}

function pickSeries(payload: BacktestSignalsPayload | undefined, candidates: string[]): unknown[] {
  const series = payload?.series || {};
  for (const key of candidates) {
    const values = series[key];
    if (Array.isArray(values) && values.length > 0) return values;
  }
  return [];
}

function buildCandles(payload: BacktestSignalsPayload | undefined, equity: Array<{ timestamp: number; equity: number }>): CandlePoint[] {
  const timestampsRaw = pickSeries(payload, ["timestamp", "time", "ts", "t"]);
  const opensRaw = pickSeries(payload, ["open", "o", "price_open"]);
  const highsRaw = pickSeries(payload, ["high", "h", "price_high"]);
  const lowsRaw = pickSeries(payload, ["low", "l", "price_low"]);
  const closesRaw = pickSeries(payload, ["close", "c", "price_close", "price"]);

  const hasAlignedPriceSeries =
    timestampsRaw.length > 0 &&
    timestampsRaw.length === opensRaw.length &&
    timestampsRaw.length === highsRaw.length &&
    timestampsRaw.length === lowsRaw.length &&
    timestampsRaw.length === closesRaw.length;

  if (hasAlignedPriceSeries) {
    const candles: CandlePoint[] = [];
    const n = timestampsRaw.length;
    for (let i = 0; i < n; i += 1) {
      const open = toFiniteNumber(opensRaw[i]);
      const high = toFiniteNumber(highsRaw[i]);
      const low = toFiniteNumber(lowsRaw[i]);
      const close = toFiniteNumber(closesRaw[i]);
      if (open == null || high == null || low == null || close == null) continue;
      candles.push({
        time: toUnixMs(timestampsRaw[i], i),
        open,
        high,
        low,
        close,
      });
    }

    const coverage = n > 0 ? candles.length / n : 0;
    // Sparse OHLC (often signal-only debug points) should not hide the full period board.
    if (candles.length > 10 && coverage >= 0.8) {
      return candles;
    }
  }

  if (equity.length > 1) {
    return equity.map((point, index) => {
      const prev = index > 0 ? equity[index - 1].equity : point.equity;
      const open = Number(prev);
      const close = Number(point.equity);
      return {
        time: point.timestamp,
        open,
        high: Math.max(open, close),
        low: Math.min(open, close),
        close,
      };
    });
  }

  return [];
}

function buildStateFlowGraph(events: BacktestSignalEvent[]): WorkflowGraphData {
  const countByType = events.reduce<Record<string, number>>((acc, event) => {
    const key = String(event.type || "unknown").toLowerCase();
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const entryCount = (countByType.entry || 0) + (countByType.flip || 0);
  const rebalanceCount = countByType.rebalance || 0;
  const exitCount = countByType.exit || 0;

  return {
    nodes: [
      { id: "idle", label: "Idle", type: "start" },
      { id: "scan", label: "Scan Signals", type: "process" },
      { id: "entry", label: "Enter Position", type: "action" },
      { id: "hold", label: "Manage Position", type: "decision" },
      { id: "exit", label: "Exit", type: "end" },
    ],
    edges: [
      { id: "idle-scan", source: "idle", target: "scan", label: "market tick", weight: 1 },
      { id: "scan-entry", source: "scan", target: "entry", label: `entry ${entryCount}`, weight: entryCount },
      { id: "entry-hold", source: "entry", target: "hold", label: "open position", weight: Math.max(entryCount, 1) },
      { id: "hold-hold", source: "hold", target: "hold", label: `rebalance ${rebalanceCount}`, weight: rebalanceCount },
      { id: "hold-exit", source: "hold", target: "exit", label: `exit ${exitCount}`, weight: exitCount },
      { id: "exit-scan", source: "exit", target: "scan", label: "next opportunity", weight: Math.max(exitCount, 1) },
    ],
  };
}

function buildAttributionGraph(events: BacktestSignalEvent[], trades: BacktestTrade[]): WorkflowGraphData {
  const reasonToType = new Map<string, Map<string, number>>();
  for (const event of events) {
    const reason = String(event.signal_reason || event.signal_detail || "unclassified").trim() || "unclassified";
    const action = String(event.type || "unknown").toLowerCase();
    if (!reasonToType.has(reason)) reasonToType.set(reason, new Map<string, number>());
    const typeMap = reasonToType.get(reason)!;
    typeMap.set(action, (typeMap.get(action) || 0) + 1);
  }

  if (!reasonToType.size && trades.length > 0) {
    const sideCounts = trades.reduce<Record<string, number>>((acc, trade) => {
      const side = String(trade.side || "unknown").toLowerCase();
      acc[side] = (acc[side] || 0) + 1;
      return acc;
    }, {});
    reasonToType.set("long setup", new Map([["entry", sideCounts.long || 0], ["exit", sideCounts.long || 0]]));
    reasonToType.set("short setup", new Map([["entry", sideCounts.short || 0], ["exit", sideCounts.short || 0]]));
  }

  const topReasons = [...reasonToType.entries()]
    .map(([reason, typeMap]) => ({
      reason,
      total: [...typeMap.values()].reduce((sum, value) => sum + value, 0),
      typeMap,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 6);

  const actionNodes = ["entry", "rebalance", "exit", "flip"];
  const nodes = [
    ...topReasons.map((item, index) => ({
      id: `reason-${index}`,
      label: item.reason.length > 26 ? `${item.reason.slice(0, 26)}...` : item.reason,
      type: "reason",
    })),
    ...actionNodes.map((action) => ({
      id: `action-${action}`,
      label: action.toUpperCase(),
      type: "action",
    })),
  ];

  const edges: WorkflowGraphData["edges"] = [];
  topReasons.forEach((item, reasonIndex) => {
    for (const action of actionNodes) {
      const value = item.typeMap.get(action) || 0;
      if (value <= 0) continue;
      edges.push({
        id: `reason-${reasonIndex}-${action}`,
        source: `reason-${reasonIndex}`,
        target: `action-${action}`,
        label: `${value}`,
        weight: value,
      });
    }
  });

  if (!edges.length) {
    edges.push({
      id: "fallback-reason-entry",
      source: "reason-0",
      target: "action-entry",
      label: "N/A",
      weight: 1,
    });
    if (!nodes.find((node) => node.id === "reason-0")) {
      nodes.unshift({ id: "reason-0", label: "No attribution data", type: "reason" });
    }
  }

  return { nodes, edges };
}

const StrategyOverviewView: React.FC<StrategyOverviewViewProps> = ({ strategy }) => {
  const queryClient = useQueryClient();
  const [animateFlow, setAnimateFlow] = useState(true);
  const [timeframe, setTimeframe] = useState<TimeframeOption>("auto");
  const [overviewGenerateStatus, setOverviewGenerateStatus] = useState<"idle" | "generating" | "failed">("idle");
  const [overviewGenerateError, setOverviewGenerateError] = useState<string | null>(null);
  const autoGenerateTriggeredRef = useRef<Record<string, boolean>>({});

  if (!strategy) {
    return <div>Loading...</div>;
  }

  const filesQuery = useQuery({
    queryKey: ["strategy-files", strategy.id],
    queryFn: () => strategiesApi.getFiles(strategy.id),
    enabled: Boolean(strategy.id),
  });

  const backtestsQuery = useQuery({
    queryKey: ["backtests", strategy.id],
    queryFn: () => backtestsApi.list(strategy.id),
    enabled: Boolean(strategy.id),
    refetchInterval: 5000,
  });

  const latestSucceededRun = useMemo(
    () => (backtestsQuery.data || []).find((run) => run.status === "succeeded") || null,
    [backtestsQuery.data],
  );

  const latestRunId = latestSucceededRun?.id || null;

  useEffect(() => {
    setTimeframe("auto");
  }, [latestRunId]);

  const equityQuery = useQuery({
    queryKey: ["overview-equity-curve", latestRunId],
    queryFn: () => backtestsApi.getEquityCurve(latestRunId as string),
    enabled: Boolean(latestRunId),
  });

  const signalEventsQuery = useQuery({
    queryKey: ["overview-signal-events", latestRunId],
    queryFn: () => backtestsApi.getSignalEvents(latestRunId as string),
    enabled: Boolean(latestRunId),
  });

  const tradesQuery = useQuery({
    queryKey: ["overview-trades", latestRunId],
    queryFn: () => backtestsApi.getTrades(latestRunId as string),
    enabled: Boolean(latestRunId),
  });

  const signalsQuery = useQuery({
    queryKey: ["overview-signals", latestRunId],
    queryFn: () => backtestsApi.getSignals(latestRunId as string),
    enabled: Boolean(latestRunId),
  });

  const candlesQuery = useQuery({
    queryKey: ["overview-candles", latestRunId],
    queryFn: async () => {
      try {
        return await backtestsApi.getCandles(latestRunId as string);
      } catch {
        return { data: [] as BacktestCandle[] };
      }
    },
    enabled: Boolean(latestRunId),
  });

  const overviewContent = useMemo(() => {
    const overviewFile = filesQuery.data?.files.find((file) => file.name === "overview.md");
    return overviewFile?.content?.trim() || "";
  }, [filesQuery.data]);

  const hasOverview = overviewContent.length > 0;

  const triggerOverviewGeneration = useCallback(
    async (manual = false) => {
      if (!strategy?.id || strategy.chat_status !== "done") return;
      if (overviewGenerateStatus === "generating") return;
      if (!manual && autoGenerateTriggeredRef.current[strategy.id]) return;
      if (!manual) {
        autoGenerateTriggeredRef.current[strategy.id] = true;
      }

      setOverviewGenerateStatus("generating");
      setOverviewGenerateError(null);

      try {
        const response = await strategiesApi.chatStream(strategy.id, "/generate_overview");
        if (!response.ok) {
          throw new Error(`overview_generate_http_${response.status}`);
        }
        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("overview_generate_reader_missing");
        }

        const decoder = new TextDecoder();
        let buffer = "";
        let gotDone = false;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = JSON.parse(line.slice(6));
            if (payload.type === "error") {
              throw new Error(String(payload.content || "overview_generate_failed"));
            }
            if (payload.type === "done") {
              gotDone = true;
            }
          }
        }

        if (!gotDone) {
          throw new Error("overview_generate_incomplete");
        }

        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["strategy-files", strategy.id] }),
          queryClient.invalidateQueries({ queryKey: ["strategy", strategy.id] }),
          queryClient.invalidateQueries({ queryKey: ["strategies"] }),
        ]);
        setOverviewGenerateStatus("idle");
        setOverviewGenerateError(null);
      } catch (error) {
        setOverviewGenerateStatus("failed");
        setOverviewGenerateError(error instanceof Error ? error.message : "overview_generate_failed");
      }
    },
    [overviewGenerateStatus, queryClient, strategy?.chat_status, strategy?.id],
  );

  useEffect(() => {
    if (!strategy?.id || strategy.chat_status !== "done" || hasOverview) return;
    if (overviewGenerateStatus === "generating") return;
    if (autoGenerateTriggeredRef.current[strategy.id]) return;
    void triggerOverviewGeneration(false);
  }, [hasOverview, overviewGenerateStatus, strategy?.chat_status, strategy?.id, triggerOverviewGeneration]);

  const equitySeries = useMemo(() => {
    const points = equityQuery.data?.data || [];
    return points
      .map((point, index) => ({
        timestamp: toUnixMs(point.timestamp, index),
        equity: Number(point.equity || 0),
        drawdown: Number(point.drawdown || 0),
      }))
      .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.equity))
      .sort((a, b) => a.timestamp - b.timestamp);
  }, [equityQuery.data]);

  const signalEvents = useMemo(() => signalEventsQuery.data?.events || [], [signalEventsQuery.data]);
  const trades = useMemo(() => tradesQuery.data?.trades || [], [tradesQuery.data]);

  const candlesFromArtifact = useMemo(() => {
    const points = candlesQuery.data?.data || [];
    return points
      .map((point, index) => {
        const open = Number(point.open);
        const high = Number(point.high);
        const low = Number(point.low);
        const close = Number(point.close);
        if (!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) {
          return null;
        }
        return {
          time: toUnixMs(point.timestamp, index),
          open,
          high,
          low,
          close,
        };
      })
      .filter((point): point is CandlePoint => Boolean(point))
      .sort((a, b) => a.time - b.time);
  }, [candlesQuery.data]);

  const candles = useMemo(() => {
    if (candlesFromArtifact.length > 10) return candlesFromArtifact;
    return buildCandles(signalsQuery.data, equitySeries);
  }, [candlesFromArtifact, signalsQuery.data, equitySeries]);

  const normalizedSignalEvents = useMemo(
    () =>
      signalEvents.map((event, index) => ({
        ...event,
        timeMs: parseTimeMs((event as unknown as { time_ms?: unknown; time?: unknown }).time_ms ?? event.time, index),
      })),
    [signalEvents],
  );

  const inferredBarIntervalMs = useMemo(() => inferMedianBarIntervalMs(candles), [candles]);
  const inferredBarTimeframeLabel = useMemo(() => formatBarTimeframe(inferredBarIntervalMs), [inferredBarIntervalMs]);
  const defaultTimeframe = useMemo(() => defaultTimeframeByBarInterval(inferredBarIntervalMs), [inferredBarIntervalMs]);
  const resolvedTimeframe: Exclude<TimeframeOption, "auto"> = timeframe === "auto" ? defaultTimeframe : timeframe;

  const latestBoardTimestamp = useMemo(() => {
    const lastCandle = candles[candles.length - 1]?.time || 0;
    const lastEquity = equitySeries[equitySeries.length - 1]?.timestamp || 0;
    const lastEvent = normalizedSignalEvents[normalizedSignalEvents.length - 1]?.timeMs || 0;
    return Math.max(lastCandle, lastEquity, lastEvent);
  }, [candles, equitySeries, normalizedSignalEvents]);

  const rangeStartMs = useMemo(() => {
    if (resolvedTimeframe === "all" || !latestBoardTimestamp) return null;
    return latestBoardTimestamp - timeframeDurationMs(resolvedTimeframe);
  }, [resolvedTimeframe, latestBoardTimestamp]);

  const filteredCandles = useMemo(
    () => (rangeStartMs == null ? candles : candles.filter((point) => point.time >= rangeStartMs)),
    [candles, rangeStartMs],
  );

  const filteredEquitySeries = useMemo(
    () => (rangeStartMs == null ? equitySeries : equitySeries.filter((point) => point.timestamp >= rangeStartMs)),
    [equitySeries, rangeStartMs],
  );

  const filteredSignalEvents = useMemo(
    () => (rangeStartMs == null ? normalizedSignalEvents : normalizedSignalEvents.filter((event) => event.timeMs >= rangeStartMs)),
    [normalizedSignalEvents, rangeStartMs],
  );

  const filteredTrades = useMemo(
    () =>
      trades.filter((trade, index) => {
        if (rangeStartMs == null) return true;
        const exitTime = parseTimeMs(
          (trade as unknown as { exit_time_ms?: unknown }).exit_time_ms ?? trade.exit_time,
          index,
        );
        const entryTime = parseTimeMs(
          (trade as unknown as { entry_time_ms?: unknown }).entry_time_ms ?? trade.entry_time,
          index,
        );
        return Math.max(exitTime, entryTime) >= rangeStartMs;
      }),
    [trades, rangeStartMs],
  );

  const boardSignals = useMemo(() => {
    return filteredSignalEvents.slice(-300).map((event, index) => {
      const eventType = String(event.type || "").toLowerCase();
      const side = String(event.side || "").toLowerCase();
      const markerType = eventType === "entry" || eventType === "flip" ? "buy" : "sell";
      const reasonRaw = String(event.signal_reason || event.signal_detail || "").trim();
      const sideLabel = side === "long" ? "LONG" : side === "short" ? "SHORT" : "";
      let markerText = reasonRaw || eventType || "signal";
      if ((eventType === "entry" || reasonRaw.toLowerCase() === "entry_signal") && sideLabel) {
        markerText = `ENTRY ${sideLabel}`;
      }
      return {
        time: event.timeMs || index,
        type: markerType as "buy" | "sell",
        price: Number(event.price || 0),
        text: markerText,
      };
    });
  }, [filteredSignalEvents]);

  const boardStats = useMemo(() => {
    const first = filteredEquitySeries[0];
    const last = filteredEquitySeries[filteredEquitySeries.length - 1];
    const startEquity = first?.equity || 0;
    const finalEquity = last?.equity || 0;
    const netPnl = finalEquity - startEquity;
    const netPnlPct = startEquity > 0 ? (netPnl / startEquity) * 100 : 0;
    const maxDrawdownPct = filteredEquitySeries.reduce((worst, point) => {
      const value = Math.abs(Number(point.drawdown || 0));
      return Math.max(worst, value);
    }, 0);

    let longPnl = 0;
    let shortPnl = 0;
    for (const trade of filteredTrades) {
      const pnl = Number(trade.pnl || 0);
      const side = String(trade.side || "").toLowerCase();
      if (side === "short") shortPnl += pnl;
      else longPnl += pnl;
    }

    return {
      finalEquity,
      netPnl,
      netPnlPct,
      maxDrawdownPct,
      signalCount: filteredSignalEvents.length,
      longPnl,
      shortPnl,
    };
  }, [filteredEquitySeries, filteredSignalEvents.length, filteredTrades]);

  const markdownG6Graphs = useMemo(() => parseG6Graphs(overviewContent), [overviewContent]);

  const workflowFromChatConfig = useMemo(() => {
    const config = strategy.chat_config as Record<string, unknown> | undefined;
    return parseWorkflowGraphData(config?.workflow_graph);
  }, [strategy.chat_config]);

  const stateFlowGraph = useMemo(
    () => markdownG6Graphs[0] || workflowFromChatConfig || buildStateFlowGraph(signalEvents),
    [markdownG6Graphs, workflowFromChatConfig, signalEvents],
  );

  const attributionFlowGraph = useMemo(
    () => markdownG6Graphs[1] || buildAttributionGraph(signalEvents, trades),
    [markdownG6Graphs, signalEvents, trades],
  );

  const handleGenerate = () => {
    void triggerOverviewGeneration(true);
  };

  const formatCurrency = (value: number) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    }).format(Number(value || 0));

  const formatPercent = (value: number) => `${Number(value || 0).toFixed(2)}%`;

  const renderMarkdownBlock = (language: string | undefined, content: string) => {
    if (language?.includes("mermaid")) {
      return <MermaidBlock chart={content} />;
    }

    if (language?.includes("g6")) {
      try {
        const parsed = JSON.parse(content);
        const graph = parseWorkflowGraphData(parsed);
        if (!graph) throw new Error("invalid_graph_data");
        return <StrategyWorkflowGraph data={graph} height={380} animate={animateFlow} />;
      } catch {
        return (
          <pre className="overflow-x-auto rounded-md border border-border bg-card p-3 text-xs">
            {content}
          </pre>
        );
      }
    }

    return (
      <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
        {content}
      </code>
    );
  };

  return (
    <div className="h-full p-6 overflow-hidden">
      <Card className="h-full flex flex-col min-h-0">
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate">{strategy.name || "Untitled Strategy"} - Overview</CardTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="gap-1">
                <Activity size={12} />
                Dual View: Board + Flow
              </Badge>
              {latestSucceededRun ? (
                <Badge variant="outline" className="gap-1">
                  <GitBranch size={12} />
                  Run {latestSucceededRun.id.slice(0, 8)}
                </Badge>
              ) : (
                <Badge variant="outline">No succeeded backtest yet</Badge>
              )}
            </div>
          </div>
          {!hasOverview ? (
            <Button onClick={handleGenerate} className="gap-2 shrink-0" disabled={overviewGenerateStatus === "generating"}>
              {overviewGenerateStatus === "generating" ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              {overviewGenerateStatus === "failed" ? "Retry Workflow & Description" : "Generate Workflow & Description"}
            </Button>
          ) : null}
        </CardHeader>

        <CardContent className="flex-1 min-h-0 px-4 pb-4">
          <Tabs defaultValue="narrative" className="h-full flex flex-col gap-4">
            <TabsList className="w-fit">
              <TabsTrigger value="narrative">Narrative</TabsTrigger>
              <TabsTrigger value="visual">Visual</TabsTrigger>
            </TabsList>

            <TabsContent value="narrative" className="flex-1 min-h-0 mt-0">
              <ScrollArea className="h-full rounded-md border p-4 bg-muted/10">
                {hasOverview ? (
                  <div className="prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown
                      components={{
                        code({ className, children }) {
                          const content = String(children).replace(/\n$/, "");
                          return renderMarkdownBlock(className, content);
                        },
                        pre({ children }) {
                          return <pre className="overflow-x-auto rounded-md border border-border bg-card p-3">{children}</pre>;
                        },
                      }}
                    >
                      {overviewContent}
                    </ReactMarkdown>
                  </div>
                ) : filesQuery.isLoading ? (
                  <div className="text-sm text-muted-foreground">Loading overview...</div>
                ) : overviewGenerateStatus === "generating" ? (
                  <div className="flex items-center justify-center h-full text-muted-foreground gap-2">
                    <Loader2 size={16} className="animate-spin" />
                    <span>Generating overview automatically...</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-muted-foreground border-2 border-dashed rounded-lg gap-4 bg-muted/10">
                    <p>No overview markdown available. Auto-generation will run by default.</p>
                    {overviewGenerateError ? (
                      <p className="text-xs text-destructive max-w-xl text-center px-4">{overviewGenerateError}</p>
                    ) : null}
                    <Button onClick={handleGenerate} className="gap-2">
                      <Sparkles size={16} />
                      {overviewGenerateStatus === "failed" ? "Retry Workflow & Description" : "Generate Workflow & Description"}
                    </Button>
                  </div>
                )}
              </ScrollArea>
            </TabsContent>

            <TabsContent value="visual" className="flex-1 min-h-0 mt-0">
              <Tabs defaultValue="board" className="h-full flex flex-col gap-4">
                <TabsList className="w-fit">
                  <TabsTrigger value="board">Trading Board</TabsTrigger>
                  <TabsTrigger value="flow">Flow Animation</TabsTrigger>
                </TabsList>

                <TabsContent value="board" className="flex-1 min-h-0 mt-0">
                  <ScrollArea className="h-full rounded-md border p-4 bg-muted/10">
                    <div className="space-y-4">
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                        <Card>
                          <CardContent className="pt-4">
                            <div className="text-xs text-muted-foreground">Final Equity</div>
                            <div className="text-lg font-semibold">{formatCurrency(boardStats.finalEquity)}</div>
                          </CardContent>
                        </Card>
                        <Card>
                          <CardContent className="pt-4">
                            <div className="text-xs text-muted-foreground">Net PnL</div>
                            <div className={`text-lg font-semibold ${boardStats.netPnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                              {boardStats.netPnl >= 0 ? <TrendingUp className="inline mr-1 h-4 w-4" /> : <TrendingDown className="inline mr-1 h-4 w-4" />}
                              {formatCurrency(boardStats.netPnl)} ({formatPercent(boardStats.netPnlPct)})
                            </div>
                          </CardContent>
                        </Card>
                        <Card>
                          <CardContent className="pt-4">
                            <div className="text-xs text-muted-foreground">Max Drawdown</div>
                            <div className="text-lg font-semibold text-red-600">{formatPercent(boardStats.maxDrawdownPct)}</div>
                          </CardContent>
                        </Card>
                        <Card>
                          <CardContent className="pt-4">
                            <div className="text-xs text-muted-foreground">Signal Events</div>
                            <div className="text-lg font-semibold">{boardStats.signalCount}</div>
                          </CardContent>
                        </Card>
                      </div>

                      <Card>
                        <CardHeader className="pb-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <CardTitle className="text-base">Price / Equity K-line with Signal Markers</CardTitle>
                            <div className="flex flex-wrap items-center gap-1">
                              <Badge variant="outline" className="mr-1">
                                Bar TF: {inferredBarTimeframeLabel}
                              </Badge>
                              <Badge variant="outline" className="mr-1">
                                Range: {TIMEFRAME_LABELS[resolvedTimeframe]}{timeframe === "auto" ? " (auto)" : ""}
                              </Badge>
                              {(["auto", "1d", "7d", "30d", "90d", "180d", "365d", "all"] as TimeframeOption[]).map((option) => {
                                const active = timeframe === option;
                                const label =
                                  option === "auto"
                                    ? "Auto"
                                    : TIMEFRAME_LABELS[option as Exclude<TimeframeOption, "auto">];
                                return (
                                  <Button
                                    key={option}
                                    size="sm"
                                    variant={active ? "default" : "outline"}
                                    className="h-7 px-2 text-xs"
                                    onClick={() => setTimeframe(option)}
                                  >
                                    {label}
                                  </Button>
                                );
                              })}
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent>
                          {filteredCandles.length > 0 ? (
                            <TradingViewChart data={filteredCandles} chartType="candlestick" signals={boardSignals} height={360} />
                          ) : (
                            <div className="h-[260px] flex items-center justify-center text-sm text-muted-foreground border border-dashed rounded-lg">
                              No candle/equity data available in selected timeframe.
                            </div>
                          )}
                        </CardContent>
                      </Card>

                      <div className="grid gap-3 md:grid-cols-2">
                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">Long Side PnL</CardTitle>
                          </CardHeader>
                          <CardContent className={`text-lg font-semibold ${boardStats.longPnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                            {formatCurrency(boardStats.longPnl)}
                          </CardContent>
                        </Card>
                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">Short Side PnL</CardTitle>
                          </CardHeader>
                          <CardContent className={`text-lg font-semibold ${boardStats.shortPnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                            {formatCurrency(boardStats.shortPnl)}
                          </CardContent>
                        </Card>
                      </div>

                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">Recent Signal Events</CardTitle>
                        </CardHeader>
                        <CardContent>
                          {filteredSignalEvents.length === 0 ? (
                            <div className="text-sm text-muted-foreground">No signal event artifacts yet.</div>
                          ) : (
                            <div className="space-y-2">
                              {filteredSignalEvents.slice(-8).reverse().map((event, index) => (
                                <div key={`${event.i}-${index}`} className="flex items-center justify-between rounded border border-border p-2 text-sm">
                                  <div className="truncate">
                                    <span className="font-medium mr-2">{String(event.type || "").toUpperCase()}</span>
                                    <span className="text-muted-foreground">{String(event.signal_reason || event.signal_detail || "no reason")}</span>
                                  </div>
                                  <div className="text-xs text-muted-foreground">{Number(event.price || 0).toFixed(2)}</div>
                                </div>
                              ))}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="flow" className="flex-1 min-h-0 mt-0">
                  <ScrollArea className="h-full rounded-md border p-4 bg-muted/10">
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="text-sm text-muted-foreground">
                          State-machine playback + weighted transition graph + execution attribution graph.
                        </div>
                        <Button size="sm" variant="outline" onClick={() => setAnimateFlow((prev) => !prev)} className="gap-2">
                          {animateFlow ? <Pause size={14} /> : <Play size={14} />}
                          {animateFlow ? "Pause Animation" : "Play Animation"}
                        </Button>
                      </div>

                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">Strategy State Machine</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <StrategyWorkflowGraph data={stateFlowGraph} height={360} animate={animateFlow} />
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">Execution Attribution (Reason → Action)</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <StrategyWorkflowGraph data={attributionFlowGraph} height={360} animate={animateFlow} />
                        </CardContent>
                      </Card>
                    </div>
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
};

export default StrategyOverviewView;
