import { useState, useRef, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Send, MessageSquare, Loader2, Settings, MoreHorizontal, ArrowLeft, X, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { jobsApi, strategiesApi } from "@/lib/api";
import { buildGenerationPrompt } from "@/lib/strategyPrompt";
import type { Strategy, ChatMessage } from "@/lib/types";
import { useTranslation } from "react-i18next";
import { actionRegistry, parseActionFromMessage, ActionPayload } from "@/lib/actions";
import { ActionCard } from "@/components/console/actions/ActionCard";

interface ConsoleSidebarProps {
    strategy: Strategy | null;
    onBackToDashboard: () => void;
    collapsed: boolean;
    onToggleCollapse: () => void;
    onStrategyGenerated?: () => void;
    onNavigateView?: (view: "overview" | "code" | "backtest" | "live" | "portfolio" | "logs" | "signals", targetId?: string) => void;
    variant?: "default" | "dialog";
    onClose?: () => void;
}

const cleanSummaryText = (text: string): string => {
    const raw = String(text || "");
    // Strip action blocks (they are rendered as ActionCard UI components)
    const withoutActionBlocks = raw.replace(/```action:[a-zA-Z0-9_-]+[\s\S]*?```/g, "\n");
    // Strip machine JSON payload blocks (e.g. operations/instructions)
    const withoutJsonBlocks = withoutActionBlocks.replace(/```json[\s\S]*?"(?:operations|instructions)"[\s\S]*?```/gi, "\n");
    const withoutJsonLead = withoutJsonBlocks
        .replace(/\bhere(?:'s| is)\s+the\s+json[^:\n]*[:：]?/gi, "")
        .replace(/\bbelow\s+is\s+the\s+json[^:\n]*[:：]?/gi, "")
        .replace(/以下是(?:你要的|请求的)?\s*json[^:\n]*[:：]?/gi, "");
    return withoutJsonLead
        .replace(/[ \t]+/g, " ")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
};

const ConsoleSidebar = ({
    strategy,
    onBackToDashboard,
    collapsed,
    onToggleCollapse,
    onStrategyGenerated,
    variant = "default",
    onClose,
    onNavigateView,
}: ConsoleSidebarProps) => {
    const queryClient = useQueryClient();
    const { t } = useTranslation();
    const isDialog = variant === "dialog";
    const [message, setMessage] = useState("");
    const [expandedMessages, setExpandedMessages] = useState<Record<number, boolean>>({});
    const scrollRef = useRef<HTMLDivElement>(null);

    // Active Action Widgets state
    const [activeActions, setActiveActions] = useState<ActionPayload[]>([]);

    // Streaming state
    const [streamingMessage, setStreamingMessage] = useState("");
    const [isStreaming, setIsStreaming] = useState(false);
    const [streamingProgressPath, setStreamingProgressPath] = useState<string | null>(null);
    const [streamingProgressMessage, setStreamingProgressMessage] = useState<string | null>(null);
    const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(null);
    const [refineError, setRefineError] = useState<string | null>(null);
    const [liveDraft, setLiveDraft] = useState<{ summary: string; code: string } | null>(null);
    const [liveDraftStatus, setLiveDraftStatus] = useState<"idle" | "generating" | "ready" | "confirming" | "error">("idle");
    const [liveDraftError, setLiveDraftError] = useState<string | null>(null);
    const [isGeneratingStrategyCode, setIsGeneratingStrategyCode] = useState(false);
    const [generationProgressMessage, setGenerationProgressMessage] = useState<string | null>(null);
    const [generateStrategyError, setGenerateStrategyError] = useState<string | null>(null);
    const [isRollingBack, setIsRollingBack] = useState(false);
    const [rollbackError, setRollbackError] = useState<string | null>(null);
    const [showDialogRollback, setShowDialogRollback] = useState(false);
    const readyAutoTriggerRef = useRef(false);

    const executeAction = useCallback(async (actionPayload: ActionPayload) => {
        const handler = actionRegistry.get(actionPayload.type);
        if (!handler) {
            console.warn(`No action handler registered for type: ${actionPayload.type}`);
            return;
        }

        const actionContext = {
            strategy,
            queryClient,
            onNavigateView,
            onSendMessage: (msg: string) => {
                setMessage(msg);
            },
        };

        // Add to activeActions as running
        setActiveActions((prev) => [
            ...prev.filter((a) => a.id !== actionPayload.id),
            { ...actionPayload, status: "running" },
        ]);

        try {
            const { jobId, result } = await handler.execute(actionContext, actionPayload.params);

            if (jobId && handler.pollCompletion) {
                // Poll for background job completion
                const finalResult = await handler.pollCompletion(actionContext, jobId, actionPayload.params);
                setActiveActions((prev) =>
                    prev.map((a) =>
                        a.id === actionPayload.id
                            ? { ...a, status: "succeeded", result: finalResult, completedAt: Date.now() }
                            : a
                    )
                );
            } else {
                setActiveActions((prev) =>
                    prev.map((a) =>
                        a.id === actionPayload.id
                            ? { ...a, status: "succeeded", result, completedAt: Date.now() }
                            : a
                    )
                );
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : String(err);
            setActiveActions((prev) =>
                prev.map((a) =>
                    a.id === actionPayload.id
                        ? { ...a, status: "failed", error: errorMessage, completedAt: Date.now() }
                        : a
                )
            );
        }
    }, [strategy, queryClient, onNavigateView]);

    const refreshStrategyData = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: ["strategies"] });
        if (strategy?.id) {
            queryClient.invalidateQueries({ queryKey: ["strategy", strategy.id] });
            queryClient.invalidateQueries({ queryKey: ["strategy-files", strategy.id] });
            queryClient.invalidateQueries({ queryKey: ["strategy-changes-compare", "repo", strategy.id] });
            queryClient.invalidateQueries({ queryKey: ["strategy-changes-compare", "workspace", strategy.id] });
            queryClient.invalidateQueries({ queryKey: ["strategy-changes-compare-diff", "repo", strategy.id] });
            queryClient.invalidateQueries({ queryKey: ["strategy-changes-compare-diff", "workspace", strategy.id] });
        }
    }, [queryClient, strategy?.id]);

    const getProgressMessage = useCallback(
        (data: {
            type?: string;
            step?: string;
            tool?: string;
            path?: string;
            message?: string;
            detail?: string;
            stage?: string;
        }): string | null => {
            const stepLabels: Record<string, string> = {
                initializing_agent: t("console.sidebar.agentSteps.initializing_agent"),
                running_backtest: t("console.sidebar.agentSteps.running_backtest"),
                auditing_code: t("console.sidebar.agentSteps.auditing_code"),
                finalizing_strategy: t("console.sidebar.agentSteps.finalizing_strategy"),
                evaluating_metrics: t("console.sidebar.agentSteps.evaluating_metrics"),
            };

            if (data.step && stepLabels[data.step]) {
                return stepLabels[data.step];
            }
            if (data.path) {
                const isRead = data.tool && ["read_file", "read"].includes(data.tool);
                return isRead
                    ? t("console.sidebar.readingFile", { path: data.path })
                    : t("console.sidebar.editingFile", { path: data.path });
            }
            if (data.tool) {
                return t("console.sidebar.executingTool", { tool: data.tool });
            }
            if (
                data.stage === "thinking" ||
                (data.message && (data.message.includes("思考") || data.message.toLowerCase().includes("thinking")))
            ) {
                return t("console.sidebar.aiThinking");
            }
            return data.message || data.detail || (data.step ? stepLabels[data.step] || data.step : null);
        },
        [t]
    );

    // Get chat history from strategy
    const chatHistory: ChatMessage[] = strategy?.chat_history || [];

    // Check for pending chat message from LiveTradingView upgrade prompt
    // Use interval to check since strategy?.id doesn't change when switching tabs
    useEffect(() => {
        if (!strategy || isStreaming) return;

        const checkPendingMessage = () => {
            const pendingMessage = sessionStorage.getItem("pending_chat_message");
            if (!pendingMessage) return;
            sessionStorage.removeItem("pending_chat_message");

            let payload: { type?: string; prompt?: string } | null = null;
            if (pendingMessage.trim().startsWith("{")) {
                try {
                    payload = JSON.parse(pendingMessage);
                } catch {
                    payload = null;
                }
            }

            if (payload?.type === "live_generate") {
                (async () => {
                    const prompt = payload?.prompt || t("liveTrading.generatePrompt");
                    setIsStreaming(true);
                    setStreamingMessage("");
                    setStreamingProgressPath(null);
                    setPendingUserMessage(prompt);
                    setRefineError(null);
                    setLiveDraft(null);
                    setLiveDraftStatus("generating");
                    setLiveDraftError(null);
                    setMessage("");
                    try {
                        const res = await strategiesApi.generateLive(strategy.id, { prompt });
                        setLiveDraft({ summary: res.summary, code: res.code });
                        setLiveDraftStatus("ready");
                    } catch (err) {
                        setLiveDraftStatus("error");
                        setLiveDraftError(err instanceof Error ? err.message : t("liveTrading.generateFailed"));
                    } finally {
                        setIsStreaming(false);
                        setStreamingMessage("");
                        setStreamingProgressPath(null);
                        setPendingUserMessage(null);
                    }
                })();
                return;
            }

            // Call the API directly instead of using sendStreamingMessage
            (async () => {
                setIsStreaming(true);
                setStreamingMessage("");
                setStreamingProgressPath(null);
                setPendingUserMessage(pendingMessage);
                setRefineError(null);
                setMessage("");

                try {
                    const response = await strategiesApi.chatStream(strategy.id, pendingMessage);
                    if (!response.ok) {
                        throw new Error("Stream request failed");
                    }
                    const reader = response.body?.getReader();
                    if (!reader) {
                        throw new Error("No reader available");
                    }
                    const decoder = new TextDecoder();
                    let buffer = "";
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split("\n");
                        buffer = lines.pop() || "";
                        for (const line of lines) {
                            if (line.startsWith("data: ")) {
                                try {
                                    const data = JSON.parse(line.slice(6));
                                    if (data.type === "token") {
                                        setStreamingMessage(prev => prev + data.content);
                                    } else if (data.type === "progress") {
                                        const msg = getProgressMessage(data);
                                        if (msg) setStreamingProgressMessage(msg);
                                        const path = typeof data.path === "string" ? data.path : "";
                                        if (path) {
                                            setStreamingProgressPath(path);
                                        }
                                    } else if (data.type === "done") {
                                        refreshStrategyData();
                                    } else if (data.type === "error") {
                                        const content = String(data.content || "");
                                        setRefineError(content);
                                        console.error("SSE error:", data.content);
                                    }
                                } catch { }
                            }
                        }
                    }
                } catch (err) {
                    console.error("Streaming error:", err);
                } finally {
                    setIsStreaming(false);
                    setStreamingMessage("");
                    setStreamingProgressPath(null);
                    setStreamingProgressMessage(null);
                    setPendingUserMessage(null);
                }
            })();
        };

        // Check immediately
        checkPendingMessage();

        // Also check periodically in case we missed it
        const interval = setInterval(checkPendingMessage, 500);
        return () => clearInterval(interval);
    }, [strategy?.id, isStreaming, t, refreshStrategyData, getProgressMessage]);

    // Streaming chat function
    const sendStreamingMessage = async (userMessage: string) => {
        if (!strategy || isStreaming) return;

        setIsStreaming(true);
        setStreamingMessage("");
        setStreamingProgressPath(null);
        setPendingUserMessage(userMessage);
        setRefineError(null);
        setMessage("");

        try {
            const response = await strategiesApi.chatStream(strategy.id, userMessage);
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }

            const reader = response.body?.getReader();
            if (!reader) throw new Error("No reader available");

            const decoder = new TextDecoder();
            let buffer = "";
            let fullResponse = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE events
                const lines = buffer.split("\n");
                buffer = lines.pop() || ""; // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === "token") {
                                fullResponse += data.content;
                                setStreamingMessage(prev => prev + data.content);
                            } else if (data.type === "progress") {
                                const msg = getProgressMessage(data);
                                if (msg) setStreamingProgressMessage(msg);
                                const path = typeof data.path === "string" ? data.path : "";
                                if (path) {
                                    setStreamingProgressPath(path);
                                }
                            } else if (data.type === "done") {
                                refreshStrategyData();
                            } else if (data.type === "error") {
                                const content = String(data.content || "");
                                setRefineError(content);
                                console.error("SSE error:", data.content);
                            }
                        } catch {
                            // Skip malformed JSON
                        }
                    }
                }
            }

            // Check if LLM emitted an action block in its response
            const actionPayload = parseActionFromMessage(fullResponse);
            if (actionPayload) {
                void executeAction(actionPayload);
            }
        } catch (error) {
            console.error("Streaming chat error:", error);
        } finally {
            setIsStreaming(false);
            setStreamingMessage("");
            setStreamingProgressPath(null);
            setStreamingProgressMessage(null);
            setPendingUserMessage(null);
        }
    };

    const scrollToBottom = useCallback(() => {
        const viewport = scrollRef.current?.querySelector("[data-radix-scroll-area-viewport]") as HTMLDivElement | null;
        if (!viewport) return;
        viewport.scrollTop = viewport.scrollHeight;
    }, []);

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        const rafId = window.requestAnimationFrame(scrollToBottom);
        return () => window.cancelAnimationFrame(rafId);
    }, [chatHistory, streamingMessage, pendingUserMessage, liveDraft, liveDraftStatus, scrollToBottom]);

    useEffect(() => {
        setLiveDraft(null);
        setLiveDraftStatus("idle");
        setLiveDraftError(null);
        setIsGeneratingStrategyCode(false);
        setGenerateStrategyError(null);
        setStreamingProgressPath(null);
        setIsRollingBack(false);
        setRollbackError(null);
        setShowDialogRollback(false);
        readyAutoTriggerRef.current = false;
    }, [strategy?.id]);

    useEffect(() => {
        if (!isDialog || !strategy || strategy.chat_status !== "done") {
            setShowDialogRollback(false);
            return;
        }

        let active = true;
        (async () => {
            try {
                const versions = await strategiesApi.listVersions(strategy.id);
                if (!active) return;
                if (versions.length < 2) {
                    setShowDialogRollback(false);
                    return;
                }
                const latestMode = String(versions[0]?.llm_meta?.mode || "");
                setShowDialogRollback(latestMode === "autonomous_refine");
            } catch {
                if (!active) return;
                setShowDialogRollback(false);
            }
        })();

        return () => {
            active = false;
        };
    }, [isDialog, strategy?.id, strategy?.chat_status, strategy?.updated_at]);

    const getGenerateErrorMessage = useCallback((error: unknown) => {
        if (!(error instanceof Error)) return t("dashboard.generateErrorGeneric");
        const message = error.message;
        const runningMatch = message.match(/job_already_running:([a-f0-9-]+):([a-z_]+)/);
        if (runningMatch) {
            const [, jobId, jobType] = runningMatch;
            return t("dashboard.generateErrorRunning")
                .replace("{jobType}", jobType)
                .replace("{jobId}", jobId);
        }
        if (message.includes("strategy_not_ready_for_generation") || message.includes("strategy_not_ready_for_confirmation")) {
            return t("dashboard.generateErrorNotReady");
        }
        const failedMatch = message.match(/job_failed:(.+)$/);
        if (failedMatch) {
            return t("dashboard.generateErrorFailed").replace("{reason}", failedMatch[1]);
        }
        return t("dashboard.generateErrorGeneric");
    }, [t]);

    const handleConfirmAndGenerateStrategy = useCallback(async () => {
        if (!strategy || strategy.chat_status !== "ready" || isStreaming || isGeneratingStrategyCode) return;
        setGenerateStrategyError(null);
        setIsGeneratingStrategyCode(true);
        setGenerationProgressMessage(t("console.sidebar.confirmGenerating"));
        try {
            await strategiesApi.confirmChat(strategy.id);
            const prompt = buildGenerationPrompt(strategy);
            const result = await strategiesApi.generate(strategy.id, { prompt });
            refreshStrategyData();
            const job = await jobsApi.waitForCompletionWithStream(
                result.job.id,
                (evt) => {
                    const msg = getProgressMessage(evt);
                    if (msg) {
                        setGenerationProgressMessage(msg);
                    }
                }
            );
            if (job.status !== "succeeded") {
                throw new Error(`job_failed:${job.error_message || job.id}`);
            }
            refreshStrategyData();
            onStrategyGenerated?.();
        } catch (error) {
            setGenerateStrategyError(getGenerateErrorMessage(error));
        } finally {
            setIsGeneratingStrategyCode(false);
            setGenerationProgressMessage(null);
            refreshStrategyData();
        }
    }, [
        strategy,
        isStreaming,
        isGeneratingStrategyCode,
        refreshStrategyData,
        onStrategyGenerated,
        getGenerateErrorMessage,
        getProgressMessage,
        t,
    ]);

    const handleRollbackToPreviousVersion = useCallback(async () => {
        if (
            !strategy ||
            isStreaming ||
            isGeneratingStrategyCode ||
            isRollingBack ||
            strategy.chat_status === "generating"
        ) {
            return;
        }
        setRollbackError(null);
        setIsRollingBack(true);
        try {
            const versions = await strategiesApi.listVersions(strategy.id);
            if (versions.length < 2) {
                setRollbackError(t("console.sidebar.rollbackNoPrevious"));
                return;
            }
            await strategiesApi.restoreVersion(strategy.id, versions[1].id);
            setGenerateStrategyError(null);
            setShowDialogRollback(false);
            refreshStrategyData();
        } catch (error) {
            if (error instanceof Error) {
                setRollbackError(error.message);
            } else {
                setRollbackError(t("console.sidebar.rollbackFailed"));
            }
        } finally {
            setIsRollingBack(false);
            refreshStrategyData();
        }
    }, [
        strategy,
        isStreaming,
        isGeneratingStrategyCode,
        isRollingBack,
        t,
        refreshStrategyData,
    ]);

    useEffect(() => {
        if (!strategy || strategy.chat_status !== "ready") {
            readyAutoTriggerRef.current = false;
            return;
        }
        if (readyAutoTriggerRef.current || isStreaming || isGeneratingStrategyCode || isRollingBack) return;
        readyAutoTriggerRef.current = true;
        void handleConfirmAndGenerateStrategy();
    }, [
        strategy,
        isStreaming,
        isGeneratingStrategyCode,
        isRollingBack,
        handleConfirmAndGenerateStrategy,
    ]);

    const handleConfirmLive = async () => {
        if (!strategy || !liveDraft) return;
        setLiveDraftStatus("confirming");
        setLiveDraftError(null);
        try {
            await strategiesApi.confirmLive(strategy.id, { code: liveDraft.code, summary: liveDraft.summary });
            setLiveDraft(null);
            setLiveDraftStatus("idle");
            queryClient.invalidateQueries({ queryKey: ["live-ready", strategy.id] });
        } catch (err) {
            setLiveDraftStatus("error");
            setLiveDraftError(err instanceof Error ? err.message : t("liveTrading.confirmFailed"));
        }
    };

    const handleDiscardLive = () => {
        setLiveDraft(null);
        setLiveDraftStatus("idle");
        setLiveDraftError(null);
    };

    const handleSendMessage = () => {
        const text = message.trim();
        if (!text) return;
        if (isStreaming) return;

        // User messages always flow directly to LLM streaming chat
        sendStreamingMessage(text);
    };

    const toggleMessageDetails = (index: number) => {
        setExpandedMessages(prev => ({ ...prev, [index]: !prev[index] }));
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    };

    const getStatusColor = (status?: string) => {
        switch (status) {
            case "generated":
            case "done":
                return "bg-green-500";
            case "ready":
                return "bg-primary";
            case "generating":
                return "bg-blue-500 animate-pulse";
            default:
                return "bg-muted-foreground";
        }
    };

    if (collapsed && !isDialog) {
        return (
            <motion.div
                initial={{ width: 64 }}
                animate={{ width: 64 }}
                className="border-r border-border bg-card/50 flex flex-col items-center py-4"
            >
                <Button
                    variant="ghost"
                    size="icon"
                    onClick={onToggleCollapse}
                    className="mb-4"
                >
                    <ChevronRight size={18} />
                </Button>
                <Button
                    variant="ghost"
                    size="icon"
                    onClick={onBackToDashboard}
                    className="mb-4"
                >
                    <ArrowLeft size={18} />
                </Button>
            </motion.div>
        );
    }

    return (
        <motion.div
            className="border-r border-border bg-card/50 flex flex-col w-full h-full min-h-0 min-w-0 overflow-hidden"
        >
            {/* Header with Back Button */}
            <div className="h-14 px-4 flex items-center justify-between border-b border-border">
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={isDialog ? onClose : onBackToDashboard}
                    className="gap-2 text-muted-foreground hover:text-foreground"
                >
                    {isDialog ? <X size={16} /> : <ArrowLeft size={16} />}
                    <span>{isDialog ? t("common.close") : t("console.sidebar.backToDashboard")}</span>
                </Button>
                {!isDialog && (
                    <div className="flex items-center gap-2">
                        {onClose && (
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={onClose}
                                className="h-8 w-8"
                            >
                                <X size={16} />
                            </Button>
                        )}
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={onToggleCollapse}
                            className="h-8 w-8"
                        >
                            <ChevronLeft size={16} />
                        </Button>
                    </div>
                )}
            </div>

            {/* Strategy Info */}
            {strategy && (
                <div className="px-4 py-3 border-b border-border">
                    <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                            <h3 className="font-semibold text-foreground truncate">{strategy.name}</h3>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
                                <span className={cn("w-2 h-2 rounded-full", getStatusColor(strategy.chat_status))} />
                                <span>{strategy.chat_status}</span>
                            </div>
                            <div className="mt-3 space-y-2">
                                {strategy.chat_status === "ready" && isGeneratingStrategyCode && (
                                    <div className="text-xs text-muted-foreground bg-muted/40 p-2 rounded flex items-center gap-2">
                                        <Loader2 size={12} className="animate-spin" />
                                        {generationProgressMessage || t("console.sidebar.confirmGenerating")}
                                    </div>
                                )}
                                {generateStrategyError && (
                                    <div className="text-xs text-destructive bg-destructive/10 p-2 rounded">
                                        {generateStrategyError}
                                    </div>
                                )}
                            </div>
                        </div>
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8">
                                    <MoreHorizontal size={16} />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                <DropdownMenuItem>
                                    <Settings size={14} className="mr-2" />
                                    {t("common.settings", { defaultValue: "Settings" })}
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                </div>
            )}

            {/* Chat Messages */}
            <div className="flex-1 min-h-0 min-w-0 relative">
                <ScrollArea className="h-full w-full" ref={scrollRef}>
                    <div className="p-4 space-y-4 max-w-full">
                    {chatHistory.length === 0 && !pendingUserMessage ? (
                        <div className="text-center py-8">
                            <MessageSquare className="w-10 h-10 text-muted-foreground/50 mx-auto mb-3" />
                            <p className="text-sm text-muted-foreground">
                                {strategy?.chat_status === "done"
                                    ? t("console.sidebar.refinePlaceholder")
                                    : t("console.sidebar.createStrategyPlaceholder")}
                            </p>
                        </div>
                    ) : (
                        <>
                            {chatHistory.map((msg, idx) => {
                                const summary = cleanSummaryText(msg.summary?.trim() || "");
                                const displayText = cleanSummaryText(summary || msg.content);
                                const hasDetails = Boolean(summary) && msg.content.trim() !== summary;
                                const showDetails = Boolean(expandedMessages[idx]);
                                const inlineAction = msg.role === "assistant" ? parseActionFromMessage(msg.content) : null;

                                return (
                                    <motion.div
                                        key={idx}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className={cn(
                                            "flex w-full min-w-0",
                                            msg.role === "user" ? "justify-end" : "justify-start"
                                        )}
                                    >
                                        <div
                                            className={cn(
                                                "max-w-[92%] min-w-0 rounded-2xl px-4 py-2.5 text-sm",
                                                msg.role === "user"
                                                    ? "bg-primary text-primary-foreground rounded-br-md"
                                                    : "bg-muted text-foreground rounded-bl-md"
                                            )}
                                        >
                                            {msg.role === "assistant" ? (
                                                <div className="space-y-2 min-w-0">
                                                    <div className="prose prose-sm dark:prose-invert max-w-none break-words [overflow-wrap:anywhere] [word-break:break-word] leading-relaxed prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-headings:my-2 prose-pre:max-w-full prose-pre:overflow-x-auto">
                                                        <ReactMarkdown
                                                            components={{
                                                                pre({ children }) {
                                                                    return <pre className="overflow-x-auto max-w-full rounded-md bg-background/50 p-2 text-xs">{children}</pre>;
                                                                },
                                                                code({ className, children, ...props }) {
                                                                    const isInline = !className && typeof children === "string" && !children.includes("\n");
                                                                    return isInline ? (
                                                                        <code className="break-all rounded bg-background/40 px-1 py-0.5 text-xs" {...props}>
                                                                            {children}
                                                                        </code>
                                                                    ) : (
                                                                        <code className={cn("break-words", className)} {...props}>
                                                                            {children}
                                                                        </code>
                                                                    );
                                                                },
                                                            }}
                                                        >
                                                            {displayText}
                                                        </ReactMarkdown>
                                                    </div>
                                                    {inlineAction && (
                                                        <div className="pt-1 w-full min-w-0">
                                                            <ActionCard
                                                                payload={inlineAction}
                                                                context={{
                                                                    strategy,
                                                                    queryClient,
                                                                    onNavigateView,
                                                                    onSendMessage: (m: string) => setMessage(m),
                                                                }}
                                                            />
                                                        </div>
                                                    )}
                                                    {hasDetails && (
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            onClick={() => toggleMessageDetails(idx)}
                                                            className="h-7 px-2 text-xs text-muted-foreground"
                                                        >
                                                            {showDetails
                                                                ? t("console.sidebar.hideDetails", { defaultValue: "Hide details" })
                                                                : t("console.sidebar.showDetails", { defaultValue: "Show details" })}
                                                        </Button>
                                                    )}
                                                    {hasDetails && showDetails && (
                                                        <div className="border-t border-border/40 pt-2 min-w-0">
                                                            <div className="prose prose-sm dark:prose-invert max-w-none break-words [overflow-wrap:anywhere] [word-break:break-word] prose-p:my-1 prose-ul:my-1 prose-li:my-0 prose-pre:overflow-x-auto prose-pre:whitespace-pre prose-pre:max-w-full">
                                                                <ReactMarkdown
                                                                    components={{
                                                                        pre({ children }) {
                                                                            return <pre className="overflow-x-auto max-w-full rounded-md bg-background/50 p-2 text-xs">{children}</pre>;
                                                                        },
                                                                        code({ className, children, ...props }) {
                                                                            const isInline = !className && typeof children === "string" && !children.includes("\n");
                                                                            return isInline ? (
                                                                                <code className="break-all rounded bg-background/40 px-1 py-0.5 text-xs" {...props}>
                                                                                    {children}
                                                                                </code>
                                                                            ) : (
                                                                                <code className={cn("break-words", className)} {...props}>
                                                                                    {children}
                                                                                </code>
                                                                            );
                                                                        },
                                                                    }}
                                                                >
                                                                    {msg.content}
                                                                </ReactMarkdown>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            ) : (
                                                <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] [word-break:break-word] leading-relaxed">
                                                    {msg.content}
                                                </p>
                                            )}
                                        </div>
                                    </motion.div>
                                );
                            })}

                            {/* Pending user message while streaming */}
                            {pendingUserMessage && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="flex justify-end w-full min-w-0"
                                >
                                    <div className="max-w-[92%] min-w-0 rounded-2xl px-4 py-2.5 text-sm bg-primary text-primary-foreground rounded-br-md">
                                        <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] [word-break:break-word] leading-relaxed">
                                            {pendingUserMessage}
                                        </p>
                                    </div>
                                </motion.div>
                            )}

                            {/* Streaming AI response with typing effect */}
                            {isStreaming && (
                                <motion.div
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="flex justify-start w-full min-w-0"
                                >
                                    <div className="max-w-[92%] min-w-0 rounded-2xl px-4 py-3 text-sm bg-muted rounded-bl-md">
                                        {streamingMessage ? (
                                            <div className="space-y-2 min-w-0">
                                                <div className="prose prose-sm dark:prose-invert max-w-none break-words [overflow-wrap:anywhere] [word-break:break-word] leading-relaxed prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-headings:my-2 prose-pre:max-w-full prose-pre:overflow-x-auto">
                                                    <ReactMarkdown
                                                        components={{
                                                            pre({ children }) {
                                                                return <pre className="overflow-x-auto max-w-full rounded-md bg-background/50 p-2 text-xs">{children}</pre>;
                                                            },
                                                            code({ className, children, ...props }) {
                                                                const isInline = !className && typeof children === "string" && !children.includes("\n");
                                                                return isInline ? (
                                                                    <code className="break-all rounded bg-background/40 px-1 py-0.5 text-xs" {...props}>
                                                                        {children}
                                                                    </code>
                                                                ) : (
                                                                    <code className={cn("break-words", className)} {...props}>
                                                                        {children}
                                                                    </code>
                                                                );
                                                            },
                                                        }}
                                                    >
                                                        {cleanSummaryText(streamingMessage) || streamingMessage}
                                                    </ReactMarkdown>
                                                </div>
                                                {(streamingProgressMessage || streamingProgressPath) && (
                                                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground pt-1.5 border-t border-border/30">
                                                        <Loader2 size={12} className="animate-spin text-primary shrink-0" />
                                                        <span className="truncate">
                                                            {streamingProgressMessage || (streamingProgressPath
                                                                ? t("console.sidebar.editingFile", { path: streamingProgressPath })
                                                                : null)}
                                                        </span>
                                                    </div>
                                                )}
                                            </div>
                                        ) : (
                                            <div className="flex items-center gap-2 text-muted-foreground">
                                                <Loader2 size={14} className="animate-spin text-primary shrink-0" />
                                                <span className="text-sm">
                                                    {streamingProgressMessage || (streamingProgressPath
                                                        ? t("console.sidebar.editingFile", { path: streamingProgressPath })
                                                        : t("console.sidebar.aiThinking"))}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </motion.div>
                            )}

                            {/* Active Action Widgets (e.g. Backtest) */}
                            {activeActions.map((act) => (
                                <motion.div
                                    key={act.id}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="w-full min-w-0"
                                >
                                    <ActionCard
                                        payload={act}
                                        context={{
                                            strategy,
                                            queryClient,
                                            onNavigateView,
                                            onSendMessage: (msg: string) => setMessage(msg),
                                        }}
                                        onRetry={() => void executeAction(act)}
                                    />
                                </motion.div>
                            ))}

                            {liveDraft && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="flex justify-start w-full min-w-0"
                                >
                                    <div className="max-w-[92%] min-w-0 rounded-2xl px-4 py-3 text-sm bg-muted rounded-bl-md">
                                        <div className="text-sm text-foreground font-medium mb-2">
                                            {t("liveTrading.ready")}
                                        </div>
                                        <div className="text-xs text-muted-foreground mb-3">
                                            {liveDraft.summary}
                                        </div>
                                        {liveDraftError && (
                                            <div className="mb-2 text-xs text-destructive bg-destructive/10 p-2 rounded">
                                                {liveDraftError}
                                            </div>
                                        )}
                                        <div className="flex items-center gap-2">
                                            <Button
                                                size="sm"
                                                onClick={handleConfirmLive}
                                                disabled={liveDraftStatus === "confirming" || isStreaming}
                                            >
                                                {liveDraftStatus === "confirming" ? (
                                                    <Loader2 size={14} className="animate-spin" />
                                                ) : (
                                                    t("liveTrading.confirm")
                                                )}
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={handleDiscardLive}
                                                disabled={liveDraftStatus === "confirming" || isStreaming}
                                            >
                                                {t("common.cancel")}
                                            </Button>
                                        </div>
                                    </div>
                                </motion.div>
                            )}

                            {!liveDraft && liveDraftError && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="flex justify-start w-full min-w-0"
                                >
                                    <div className="max-w-[92%] min-w-0 rounded-2xl px-4 py-3 text-sm bg-muted rounded-bl-md">
                                        <div className="text-sm text-foreground font-medium mb-2">
                                            {t("liveTrading.generateFailedTitle")}
                                        </div>
                                        <div className="text-xs text-destructive bg-destructive/10 p-2 rounded">
                                            {liveDraftError}
                                        </div>
                                    </div>
                                </motion.div>
                            )}

                            {showDialogRollback && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="flex justify-start w-full min-w-0"
                                >
                                    <div className="max-w-[92%] min-w-0 rounded-2xl px-4 py-3 text-sm bg-muted rounded-bl-md">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="gap-2"
                                            onClick={handleRollbackToPreviousVersion}
                                            disabled={isStreaming || isGeneratingStrategyCode || isRollingBack || strategy?.chat_status === "generating"}
                                        >
                                            {isRollingBack ? (
                                                <>
                                                    <Loader2 size={14} className="animate-spin" />
                                                    {t("console.sidebar.rollbackLoading")}
                                                </>
                                            ) : (
                                                <>
                                                    <RotateCcw size={14} />
                                                    {t("console.sidebar.rollbackOneStep")}
                                                </>
                                            )}
                                        </Button>
                                        {rollbackError && (
                                            <div className="mt-2 text-xs text-destructive bg-destructive/10 p-2 rounded">
                                                {rollbackError}
                                            </div>
                                        )}
                                    </div>
                                </motion.div>
                            )}

                        </>
                    )}

                    </div>
                </ScrollArea>

                {liveDraftStatus === "generating" && (
                    <div className="absolute inset-0 z-10 flex items-start justify-center">
                        <div className="absolute inset-0 bg-background/70 backdrop-blur-sm" />
                        <div className="relative mt-6 w-[85%] max-w-md rounded-xl border border-primary/30 bg-background/95 p-4 shadow-lg">
                            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                                <Loader2 size={16} className="animate-spin text-primary" />
                                {t("liveTrading.generating")}
                            </div>
                            <div className="mt-3 h-2 w-full rounded-full bg-muted">
                                <div className="h-2 w-2/3 rounded-full bg-primary/80 animate-pulse" />
                            </div>
                            <div className="mt-2 text-xs text-muted-foreground">
                                {t("liveTrading.generatingDetail")}
                            </div>
                        </div>
                    </div>
                )}
            </div>


            {/* Message Input */}
            <div className="p-4 border-t border-border mt-2">
                <div className="relative">
                    {refineError && (
                        <div className="mb-2 text-xs text-destructive bg-destructive/10 p-2 rounded">
                            {refineError}
                        </div>
                    )}
                    <Textarea
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={
                            strategy?.chat_status === "done"
                                ? t("console.sidebar.refinePlaceholder")
                                : t("console.sidebar.createStrategyPlaceholder")
                        }
                        className="min-h-[80px] pr-12 resize-none bg-muted/50"
                        disabled={isStreaming}
                    />
                    <Button
                        size="icon"
                        onClick={handleSendMessage}
                        disabled={!message.trim() || isStreaming}
                        className="absolute bottom-3 right-3 h-8 w-8 rounded-full"
                    >
                        {isStreaming ? (
                            <Loader2 size={14} className="animate-spin" />
                        ) : (
                            <Send size={14} />
                        )}
                    </Button>
                </div>
            </div>
        </motion.div>
    );
};

export default ConsoleSidebar;
