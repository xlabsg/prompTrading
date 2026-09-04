import { useState, useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
    Send,
    Loader2,
    Clock,
    Sparkles,
    Check,
    FileCode,
    FileText,
    Settings,
    Search,
    Star,
    GitBranch,
    Lock,
    ArrowRight,
    CheckCircle2,
    Database,
    RefreshCcw,
    ShieldCheck,
    Folder,
    Download,
    Library,
    Tag,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Strategy, ChatMessage, GitHubRepo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { strategiesApi, githubApi, reposApi, jobsApi } from "@/lib/api";
import { buildGenerationPrompt } from "@/lib/strategyPrompt";
import React from "react";
import ReactMarkdown from "react-markdown";
import ImportStrategyModal from "@/components/strategy/ImportStrategyModal";
import { TrendingSection } from "@/components/dashboard/TrendingSection";
import { useTranslation } from "react-i18next";
import { TRENDING_ENABLED } from "@/lib/featureFlags";

interface DashboardHomeProps {
    onNewStrategy: (prompt?: string) => void;
    strategies: Strategy[];
    onSelectStrategy: (strategy: Strategy) => void;
    isCreating?: boolean;
    isAuthed: boolean;
    createdStrategyId?: string;
    onGoToStrategy: (strategyId: string) => void;
    onRequireAuth: () => boolean;
}

const STRATEGY_DRAFT_STORAGE_KEY = "dashboard_strategy_draft_v1";
const STRATEGY_PENDING_STORAGE_KEY = "dashboard_strategy_pending_create_v1";

const Github = ({ className, size = 24 }: { className?: string; size?: number }) => (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
        <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
);

const cleanAssistantResponse = (content: string): string => {
    const withoutCodeBlocks = content
        .replace(/```json[\s\S]*?```/gi, "\n")
        .replace(/```[\s\S]*?```/g, "\n");

    const withoutJsonLead = withoutCodeBlocks
        .replace(/\bhere(?:'s| is)\s+the\s+json[^:\n]*[:：]?/gi, "")
        .replace(/\bjson\s*(response|payload|output)[^:\n]*[:：]?/gi, "")
        .replace(/以下是(?:你要的|请求的)?\s*json[^:\n]*[:：]?/gi, "");

    return withoutJsonLead
        .replace(/[ \t]+/g, " ")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
};

const DashboardHome = ({
    onNewStrategy,
    strategies,
    onSelectStrategy,
    isCreating = false,
    isAuthed,
    createdStrategyId,
    onGoToStrategy,
    onRequireAuth,
}: DashboardHomeProps) => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [prompt, setPrompt] = useState("");
    const [activeTab, setActiveTab] = useState("recent");
    const [chatInput, setChatInput] = useState("");
    const initialPromptSentRef = useRef(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const promptTextareaRef = useRef<HTMLTextAreaElement>(null);
    const chatTextareaRef = useRef<HTMLTextAreaElement>(null);
    const [currentGeneratingStep, setCurrentGeneratingStep] = useState(0);
    const [generatingElapsedSeconds, setGeneratingElapsedSeconds] = useState(0);
    const [isImportOpen, setIsImportOpen] = useState(false);
    const [importStage, setImportStage] = useState<"connect" | "select" | "progress" | "done">("connect");
    const [repoSearch, setRepoSearch] = useState("");
    const [selectedInstallationId, setSelectedInstallationId] = useState<string | null>(null);
    const [selectedGitHubRepo, setSelectedGitHubRepo] = useState<GitHubRepo | null>(null);
    const [importProgress, setImportProgress] = useState(0);
    const [importStepIndex, setImportStepIndex] = useState(0);
    const [, setImportJobId] = useState<string | null>(null);
    const [importedStrategyId, setImportedStrategyId] = useState<string | null>(null);  // Store the strategy created during import
    const [showImportStrategyModal, setShowImportStrategyModal] = useState(false);  // TradingView/YouTube import modal
    const [isDesktop, setIsDesktop] = useState(() =>
        typeof window !== "undefined" ? window.innerWidth >= 640 : true
    );
    const [viewportHeight, setViewportHeight] = useState(() =>
        typeof window !== "undefined" ? window.innerHeight : 900
    );

    useEffect(() => {
        if (typeof window === "undefined") return;
        const stored = window.localStorage.getItem(STRATEGY_DRAFT_STORAGE_KEY);
        if (!stored) return;
        try {
            const parsed = JSON.parse(stored) as { prompt?: string; chatInput?: string };
            if (parsed.prompt) setPrompt(parsed.prompt);
            if (parsed.chatInput) setChatInput(parsed.chatInput);
        } catch {
            window.localStorage.removeItem(STRATEGY_DRAFT_STORAGE_KEY);
        }
    }, []);

    useEffect(() => {
        if (typeof window === "undefined") return;
        if (!prompt.trim() && !chatInput.trim()) {
            window.localStorage.removeItem(STRATEGY_DRAFT_STORAGE_KEY);
            return;
        }
        window.localStorage.setItem(
            STRATEGY_DRAFT_STORAGE_KEY,
            JSON.stringify({ prompt, chatInput, updatedAt: Date.now() })
        );
    }, [prompt, chatInput]);

    useEffect(() => {
        if (!createdStrategyId || typeof window === "undefined") return;
        window.localStorage.removeItem(STRATEGY_PENDING_STORAGE_KEY);
        window.localStorage.removeItem(STRATEGY_DRAFT_STORAGE_KEY);
    }, [createdStrategyId]);

    useEffect(() => {
        if (typeof window === "undefined") return;
        const handleResize = () => {
            setIsDesktop(window.innerWidth >= 640);
            setViewportHeight(window.innerHeight);
        };
        handleResize();
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    const { t: translate, i18n } = useTranslation();
    const t = translate("dashboard", { returnObjects: true }) as any;
    const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";
    const promptMinHeight = isDesktop ? 136 : 112;
    const chatMinHeight = isDesktop ? 120 : 96;
    const textareaMaxHeight = Math.max(220, Math.floor(viewportHeight * 0.55));

    const autoResizeTextarea = (
        textarea: HTMLTextAreaElement | null,
        minHeight: number,
        maxHeight: number
    ) => {
        if (!textarea) return;
        textarea.style.height = "auto";
        const nextHeight = Math.min(maxHeight, Math.max(minHeight, textarea.scrollHeight));
        textarea.style.height = `${nextHeight}px`;
        textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
    };

    // Fetch GitHub App install URL
    const installUrlQuery = useQuery({
        queryKey: ["github-install-url"],
        queryFn: githubApi.getInstallUrl,
        enabled: isImportOpen,
        staleTime: Infinity, // URL doesn't change
    });

    const githubInstallUrl = installUrlQuery.data?.install_url || "https://github.com/settings/installations";

    // Fetch GitHub installations when import dialog opens
    const installationsQuery = useQuery({
        queryKey: ["github-installations"],
        queryFn: githubApi.listInstallations,
        enabled: isImportOpen && importStage === "select",
        retry: 1,
    });

    // Auto-select first installation when loaded
    useEffect(() => {
        if (installationsQuery.data && installationsQuery.data.length > 0 && !selectedInstallationId) {
            const firstInstallation = installationsQuery.data[0];
            setSelectedInstallationId(String(firstInstallation.id));
        }
    }, [installationsQuery.data, selectedInstallationId]);

    // Fetch repos for selected installation
    const reposQuery = useQuery({
        queryKey: ["github-installation-repos", selectedInstallationId],
        queryFn: () => githubApi.listInstallationRepos(selectedInstallationId!),
        enabled: !!selectedInstallationId && isImportOpen && importStage === "select",
        retry: 1,
    });

    const generationSteps = useMemo(() => [
        {
            id: 1,
            label: translate("dashboard.generationSteps.parse"),
            file: "strategy_config.json",
            icon: Settings,
        },
        { id: 2, label: translate("dashboard.generationSteps.code"), file: "strategy.py", icon: FileCode },
        {
            id: 3,
            label: translate("dashboard.generationSteps.config"),
            file: "",
            icon: FileText,
        },
        { id: 4, label: translate("dashboard.generationSteps.validate"), file: "validation.log", icon: Check },
    ], [translate]);

    // Strategy template examples
    const strategyTemplates = useMemo(() => [
        {
            id: "ma-crossover",
            name: translate("dashboard.strategyTemplates.maCrossover.name"),
            description: translate("dashboard.strategyTemplates.maCrossover.description"),
            prompt: translate("dashboard.strategyTemplates.maCrossover.prompt"),
            category: translate("dashboard.strategyTemplates.maCrossover.category"),
        },
        {
            id: "rsi-mean-reversion",
            name: translate("dashboard.strategyTemplates.rsiMeanReversion.name"),
            description: translate("dashboard.strategyTemplates.rsiMeanReversion.description"),
            prompt: translate("dashboard.strategyTemplates.rsiMeanReversion.prompt"),
            category: translate("dashboard.strategyTemplates.rsiMeanReversion.category"),
        },
        {
            id: "price-breakout",
            name: translate("dashboard.strategyTemplates.priceBreakout.name"),
            description: translate("dashboard.strategyTemplates.priceBreakout.description"),
            prompt: translate("dashboard.strategyTemplates.priceBreakout.prompt"),
            category: translate("dashboard.strategyTemplates.priceBreakout.category"),
        },
        {
            id: "trend-following",
            name: translate("dashboard.strategyTemplates.trendFollowing.name"),
            description: translate("dashboard.strategyTemplates.trendFollowing.description"),
            prompt: translate("dashboard.strategyTemplates.trendFollowing.prompt"),
            category: translate("dashboard.strategyTemplates.trendFollowing.category"),
        },
        {
            id: "grid-trading",
            name: translate("dashboard.strategyTemplates.gridTrading.name"),
            description: translate("dashboard.strategyTemplates.gridTrading.description"),
            prompt: translate("dashboard.strategyTemplates.gridTrading.prompt"),
            category: translate("dashboard.strategyTemplates.gridTrading.category"),
        },
    ], [translate]);

    // Filter GitHub repos based on search
    const filteredRepos = useMemo(() => {
        const repos = reposQuery.data || [];
        const keyword = repoSearch.trim().toLowerCase();
        if (!keyword) return repos;
        return repos.filter((repo) =>
            repo.name.toLowerCase().includes(keyword) ||
            repo.full_name?.toLowerCase().includes(keyword)
        );
    }, [repoSearch, reposQuery.data]);

    // Import repo mutation
    const importMutation = useMutation({
        mutationFn: async () => {
            if (!selectedGitHubRepo || !selectedInstallationId) throw new Error("No repo selected");

            const owner = selectedGitHubRepo.owner?.login || "";
            const name = selectedGitHubRepo.name;
            const branch = selectedGitHubRepo.default_branch;

            return reposApi.import({
                owner,
                name,
                branches: branch ? [branch] : undefined,
                installation_id: selectedInstallationId,
            });
        },
        onSuccess: async (data) => {
            setImportJobId(data.job.id);
            // Store the created strategy ID for navigation
            if (data.strategy?.id) {
                setImportedStrategyId(data.strategy.id);
            }
            setImportStage("progress");

            // Poll job status
            try {
                await jobsApi.waitForCompletion(
                    data.job.id,
                    (job) => {
                        // Update progress based on job status
                        if (job.status === "running") {
                            setImportProgress((prev) => Math.min(prev + 10, 90));
                        }
                    },
                    2000,
                    420000
                );
                setImportProgress(100);
                // Refresh strategies list to include the new one
                queryClient.invalidateQueries({ queryKey: ["strategies"] });
                setTimeout(() => setImportStage("done"), 500);
            } catch (error) {
                console.error("Import job failed:", error);
                setImportStage("select");
            }
        },
    });

    const createdStrategy = createdStrategyId
        ? strategies.find(s => s.id === createdStrategyId)
        : null;

    useEffect(() => {
        if (createdStrategy?.chat_status !== "generating") {
            setGeneratingElapsedSeconds(0);
            return;
        }
        const timer = setInterval(() => {
            setGeneratingElapsedSeconds((prev) => prev + 1);
        }, 1000);
        return () => clearInterval(timer);
    }, [createdStrategy?.chat_status]);

    const getGeneratingHint = (seconds: number) => {
        if (seconds < 15) return translate("dashboard.generatingHints.analyzing", { defaultValue: "正在解析策略需求与交易逻辑..." });
        if (seconds < 40) return translate("dashboard.generatingHints.writing", { defaultValue: "正在由 Docker Agent 编写 strategy.py..." });
        if (seconds < 75) return translate("dashboard.generatingHints.linting", { defaultValue: "正在执行沙箱语法审计与参数化校验..." });
        if (seconds < 110) return translate("dashboard.generatingHints.verifying", { defaultValue: "正在验证回测协议与指标计算..." });
        return translate("dashboard.generatingHints.rendering", { defaultValue: "正在生成可视化决策流架构图与概览文档，即将就绪..." });
    };

    const chatHistory: ChatMessage[] = createdStrategy?.chat_history || [];
    const formatConfigLabel = (key: string): string =>
        key
            .split("_")
            .filter(Boolean)
            .join(" ");

    const formatConfigValue = (value: unknown): string => {
        if (value === null || value === undefined || value === "") return "-";
        if (typeof value === "boolean") {
            return value ? t.booleanTrue : t.booleanFalse;
        }
        if (Array.isArray(value)) {
            const plainItems = value
                .filter((item) => item !== null && item !== undefined)
                .map((item) => (typeof item === "object" ? t.strategyConfigConfigured : String(item)));
            return plainItems.length ? plainItems.join(", ") : "-";
        }
        if (typeof value === "object") return t.strategyConfigConfigured;
        return String(value);
    };

    // Streaming chat state
    const [streamingMessage, setStreamingMessage] = useState("");
    const [streamingProgressMessage, setStreamingProgressMessage] = useState<string | null>(null);
    const [isStreaming, setIsStreaming] = useState(false);
    const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(null);
    const [generateError, setGenerateError] = useState<string | null>(null);

    // Streaming chat function
    const sendStreamingMessage = async (message: string) => {
        if (!createdStrategy || isStreaming) return;

        setIsStreaming(true);
        setStreamingMessage("");
        setStreamingProgressMessage(null);
        setPendingUserMessage(message);
        setGenerateError(null);
        setChatInput("");

        try {
            const response = await strategiesApi.chatStream(createdStrategy.id, message);
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }

            const reader = response.body?.getReader();
            if (!reader) throw new Error("No reader available");

            const decoder = new TextDecoder();
            let buffer = "";

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
                                setStreamingMessage(prev => prev + data.content);
                            } else if (data.type === "progress") {
                                const isRead = data.tool && ["read_file", "read"].includes(data.tool);
                                const msg = data.path
                                    ? (isRead
                                        ? translate("console.sidebar.readingFile", { path: data.path })
                                        : translate("console.sidebar.editingFile", { path: data.path }))
                                    : data.stage === "thinking"
                                    ? translate("console.sidebar.aiThinking")
                                    : data.message;
                                if (msg) setStreamingProgressMessage(msg);
                            } else if (data.type === "done") {
                                // Refresh strategies to get updated chat history
                                queryClient.invalidateQueries({ queryKey: ["strategies"] });
                            } else if (data.type === "error") {
                                const content = String(data.content || translate("dashboard.generateErrorGeneric"));
                                setGenerateError(content);
                                console.error("SSE error:", data.content);
                            }
                        } catch (parseError) {
                            // Skip malformed JSON
                        }
                    }
                }
            }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error);
            setGenerateError(errorMsg);
            console.error("Streaming chat error:", error);
        } finally {
            setIsStreaming(false);
            setStreamingMessage("");
            setStreamingProgressMessage(null);
            setPendingUserMessage(null);
        }
    };

    // Legacy chatMutation for compatibility (keeps isPending interface)
    const chatMutation = {
        isPending: isStreaming,
        mutate: sendStreamingMessage,
    };

    const generateMutation = useMutation({
        mutationFn: async () => {
            if (!createdStrategy) throw new Error("No strategy created");

            setCurrentGeneratingStep(0);
            setGenerateError(null);

            // Note: /confirm endpoint now only updates name, /generate handles status atomically
            await strategiesApi.confirmChat(createdStrategy.id);

            const prompt = buildGenerationPrompt(createdStrategy);

            // Backend automatically infers target symbol & interval from prompt, or falls back to standard benchmark
            const result = await strategiesApi.generateAndBacktest(createdStrategy.id, {
                prompt,
            });

            // Poll job status to show real progress
            const jobId = result.job.id;
            if (jobId) {
                    const job = await jobsApi.waitForCompletion(
                        jobId,
                        (job) => {
                            // Update progress based on job status
                            if (job.status === "queued" || job.status === "running") {
                            // Map job status to generation steps
                            // Step 0: Parse requirements (always show when running)
                            setCurrentGeneratingStep(0);

                            // If job has been running for a bit, move to step 1
                            if (job.status === "running") {
                                setCurrentGeneratingStep(1);
                            }
                        } else if (job.status === "succeeded") {
                            // Move through remaining steps quickly when done
                            setCurrentGeneratingStep(2);
                            setTimeout(() => setCurrentGeneratingStep(3), 300);
                        }
                    },
                    2000, // Poll every 2 seconds
                    420000 // 7 minute timeout
                );

                if (job.status === "failed") {
                    throw new Error(`job_failed:${job.error_message || job.id}`);
                }
            }

            setCurrentGeneratingStep(generationSteps.length);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["strategies"] });
            setGenerateError(null);
        },
        onError: (error) => {
            console.error("Strategy generation failed:", error);
            setCurrentGeneratingStep(0);
            const message = getGenerateErrorMessage(error);
            setGenerateError(message);
            // Re-fetch strategies to get correct status in case of partial failure
            queryClient.invalidateQueries({ queryKey: ["strategies"] });
        },
    });

    useEffect(() => {
        if (
            createdStrategy &&
            prompt &&
            chatHistory.length === 0 &&
            !chatMutation.isPending &&
            !initialPromptSentRef.current
        ) {
            initialPromptSentRef.current = true;
            chatMutation.mutate(prompt);
            setPrompt("");
        }
    }, [createdStrategy, prompt, chatHistory.length, chatMutation]);

    const scrollToBottom = (behavior: ScrollBehavior = "auto") => {
        const el = scrollRef.current;
        if (!el) return;
        requestAnimationFrame(() => {
            el.scrollTo({ top: el.scrollHeight, behavior });
        });
    };

    useEffect(() => {
        scrollToBottom();
    }, [chatHistory, streamingMessage, pendingUserMessage, isStreaming, currentGeneratingStep, createdStrategy?.chat_status]);

    useEffect(() => {
        if (!createdStrategyId) {
            initialPromptSentRef.current = false;
            // Reset chat state when returning to dashboard
            setChatInput("");
            setStreamingMessage("");
            setStreamingProgressMessage(null);
            setPendingUserMessage(null);
            setIsStreaming(false);
            setGenerateError(null);
        }
    }, [createdStrategyId]);

    useEffect(() => {
        if (!createdStrategy?.chat_status) return;
        if (createdStrategy.chat_status === "generating" || createdStrategy.chat_status === "done") {
            setGenerateError(null);
        }
    }, [createdStrategy?.chat_status]);

    useEffect(() => {
        autoResizeTextarea(promptTextareaRef.current, promptMinHeight, textareaMaxHeight);
    }, [prompt, promptMinHeight, textareaMaxHeight, createdStrategyId]);

    useEffect(() => {
        autoResizeTextarea(chatTextareaRef.current, chatMinHeight, textareaMaxHeight);
    }, [chatInput, chatMinHeight, textareaMaxHeight, createdStrategy?.chat_status]);

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString(locale, { month: "short", day: "numeric" });
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case "generated":
            case "done":
                return "bg-green-500";
            case "ready":
                return "bg-primary";
            case "generating":
                return "bg-blue-500 animate-pulse";
            case "chatting":
                return "bg-yellow-500";
            default:
                return "bg-muted-foreground";
        }
    };

    const getGenerateErrorMessage = (error: unknown) => {
        if (error instanceof Error) {
            const message = error.message;
            const runningMatch = message.match(/job_already_running:([a-f0-9-]+):([a-z_]+)/);
            if (runningMatch) {
                const [, jobId, jobType] = runningMatch;
                return t.generateErrorRunning
                    .replace("{jobType}", jobType)
                    .replace("{jobId}", jobId);
            }
            const failedMatch = message.match(/job_failed:(.+)$/);
            if (failedMatch) {
                return t.generateErrorFailed.replace("{reason}", failedMatch[1]);
            }
            if (message.includes("strategy_not_ready_for_generation") || message.includes("strategy_not_ready_for_confirmation")) {
                return t.generateErrorNotReady;
            }
        }
        return t.generateErrorGeneric;
    };

    const handleSubmit = (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!prompt.trim() || isCreating) return;
        if (!isAuthed && typeof window !== "undefined") {
            window.localStorage.setItem(
                STRATEGY_PENDING_STORAGE_KEY,
                JSON.stringify({ prompt, chatInput, createdAt: Date.now() })
            );
        }
        onNewStrategy(prompt);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    const handleSendChatMessage = () => {
        if (!chatInput.trim() || chatMutation.isPending) return;
        chatMutation.mutate(chatInput);
    };

    const handleChatKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSendChatMessage();
        }
    };

    // Update import step index based on progress
    useEffect(() => {
        if (importStage !== "progress") return;
        const stepCount = t.import.steps.length;
        const nextStep = Math.min(
            Math.floor((importProgress / 100) * stepCount),
            stepCount - 1
        );
        setImportStepIndex(nextStep);
    }, [importProgress, importStage, t.import.steps.length]);

    const resetImportState = () => {
        setImportStage("connect");
        setRepoSearch("");
        setSelectedInstallationId(null);
        setSelectedGitHubRepo(null);
        setImportProgress(0);
        setImportStepIndex(0);
        setImportJobId(null);
        setImportedStrategyId(null);  // Reset imported strategy ID
    };


    return (
        <div className="flex-1 flex flex-col overflow-hidden bg-gradient-to-br from-orange-50/50 via-background to-orange-100/30">
            <div className="flex-1 overflow-y-auto">
                <div className="max-w-4xl mx-auto px-4 pt-3 pb-10 sm:px-8 sm:pt-6 sm:pb-14">
                    {/* Hero Section */}
                    <div className="relative text-center mb-6 sm:mb-8">
                        <div className="absolute -top-4 left-1/2 h-36 w-36 -translate-x-1/2 rounded-full bg-orange-200/40 blur-3xl pointer-events-none" />
                        <div className="absolute right-0 top-0 h-20 w-20 rounded-full bg-orange-300/30 blur-2xl pointer-events-none" />

                        <motion.h1
                            initial={{ y: 15, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: 0.1 }}
                            className="text-2xl font-bold text-foreground mb-2 sm:text-3xl lg:text-4xl"
                        >
                            {t.heroTitle}
                        </motion.h1>

                        <motion.p
                            initial={{ y: 15, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: 0.2 }}
                            className="text-muted-foreground text-sm sm:text-base max-w-xl mx-auto"
                        >
                            {t.heroSubtitle}
                        </motion.p>
                    </div>

                    {/* Creation Interface */}
                    <motion.div
                        initial={{ y: 20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        transition={{ delay: 0.3 }}
                        className="bg-card rounded-2xl shadow-xl border border-border overflow-hidden mb-12"
                    >
                        {/* Initial Loading State - when creating strategy and waiting for first AI response */}
                        {/* Initial Loading State - only while strategy record is being created in database */}
                        <AnimatePresence>
                            {isCreating && !createdStrategy && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: "auto", opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="border-b border-border"
                                >
                                    <div className="p-4 space-y-4 sm:p-6">
                                        {/* User's initial prompt */}
                                        {prompt && (
                                            <div className="flex justify-end">
                                                <div className="max-w-[88%] rounded-2xl px-4 py-3 text-sm bg-primary text-primary-foreground rounded-br-md">
                                                    <p className="whitespace-pre-wrap leading-relaxed">{prompt}</p>
                                                </div>
                                            </div>
                                        )}
                                        {/* AI initializing indicator */}
                                        <div className="flex justify-start">
                                            <div className="max-w-[88%] rounded-2xl px-4 py-3 text-sm bg-muted rounded-bl-md">
                                                <div className="flex items-center gap-2">
                                                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                                                    <span className="text-sm text-muted-foreground">
                                                        {streamingProgressMessage || translate("console.sidebar.initializingWorkspace")}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Chat Messages (active for conversation, first message streaming, and results) */}
                        <AnimatePresence>
                            {createdStrategy && (chatHistory.length > 0 || isStreaming || pendingUserMessage) && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: "auto", opacity: 1 }}
                                    className="border-b border-border"
                                >
                                    <div ref={scrollRef} className="p-4 space-y-4 max-h-[520px] overflow-y-auto sm:p-6">
                                        {chatHistory.map((msg, i) => {
                                            const displayText = msg.role === "assistant"
                                                ? cleanAssistantResponse(msg.content)
                                                : msg.content;
                                            if (!displayText) return null;

                                            return (
                                                <div
                                                    key={i}
                                                    className={cn(
                                                        "flex",
                                                        msg.role === "user" ? "justify-end" : "justify-start"
                                                    )}
                                                >
                                                    <div
                                                        className={cn(
                                                            "max-w-[88%] rounded-2xl px-4 py-3 text-sm",
                                                            msg.role === "user"
                                                                ? "bg-primary text-primary-foreground rounded-br-md"
                                                                : "bg-muted text-foreground rounded-bl-md"
                                                        )}
                                                    >
                                                        {msg.role === "assistant" ? (
                                                            <div className="prose prose-sm dark:prose-invert max-w-none break-words leading-relaxed prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-headings:my-2">
                                                                <ReactMarkdown>{displayText}</ReactMarkdown>
                                                            </div>
                                                        ) : (
                                                            <p className="whitespace-pre-wrap break-words leading-relaxed">
                                                                {displayText}
                                                            </p>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}

                                        {/* Pending user message while streaming */}
                                        {pendingUserMessage && (
                                            <div className="flex justify-end">
                                                <div className="max-w-[88%] rounded-2xl px-4 py-3 text-sm bg-primary text-primary-foreground rounded-br-md">
                                                    <p className="whitespace-pre-wrap break-words leading-relaxed">{pendingUserMessage}</p>
                                                </div>
                                            </div>
                                        )}

                                        {/* Streaming AI response with typing effect */}
                                        {isStreaming && (
                                            <div className="flex justify-start">
                                                <div className="max-w-[88%] rounded-2xl px-4 py-3 text-sm bg-muted text-foreground rounded-bl-md">
                                                    {streamingMessage ? (
                                                        <div className="space-y-2">
                                                            <div className="prose prose-sm dark:prose-invert max-w-none break-words leading-relaxed prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-headings:my-2">
                                                                <ReactMarkdown>{cleanAssistantResponse(streamingMessage)}</ReactMarkdown>
                                                            </div>
                                                            {streamingProgressMessage && (
                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1 border-t border-border/30">
                                                                    <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
                                                                    <span>{streamingProgressMessage}</span>
                                                                </div>
                                                            )}
                                                        </div>
                                                    ) : (
                                                        <div className="flex items-center gap-2">
                                                            <Loader2 className="w-4 h-4 animate-spin text-primary" />
                                                            <span className="text-sm text-muted-foreground">
                                                                {streamingProgressMessage || t.thinking}
                                                            </span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {/* Generating status with steps */}
                                        {createdStrategy.chat_status === "generating" && (
                                            <motion.div
                                                initial={{ opacity: 0, y: 10 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                className="py-4 space-y-3"
                                            >
                                                <div className="flex items-center justify-between px-2 pb-2 text-xs border-b border-border/50">
                                                    <div className="flex items-center gap-2 font-medium text-foreground">
                                                        <Loader2 size={14} className="animate-spin text-primary" />
                                                        <span>{getGeneratingHint(generatingElapsedSeconds)}</span>
                                                    </div>
                                                    <span className="tabular-nums font-mono text-[11px] bg-muted/80 px-2 py-0.5 rounded-full text-muted-foreground">
                                                        ⏱️ {translate("dashboard.elapsedSeconds", { count: generatingElapsedSeconds, defaultValue: `已耗时 ${generatingElapsedSeconds} 秒` })}
                                                    </span>
                                                </div>
                                                {generationSteps.map((step, index) => {
                                                    const isCompleted = index < currentGeneratingStep;
                                                    const isActive = index === currentGeneratingStep;
                                                    const isPending = index > currentGeneratingStep;
                                                    const StepIcon = step.icon;

                                                    return (
                                                        <motion.div
                                                            key={step.id}
                                                            initial={{ opacity: 0, x: -20 }}
                                                            animate={{ opacity: 1, x: 0 }}
                                                            transition={{ delay: index * 0.1 }}
                                                            className="flex items-center gap-3 px-2"
                                                        >
                                                            {/* Step indicator */}
                                                            <div className={cn(
                                                                "flex items-center justify-center w-6 h-6 rounded-full transition-all",
                                                                isCompleted && "bg-green-500 text-white",
                                                                isActive && "bg-primary text-primary-foreground",
                                                                isPending && "bg-muted text-muted-foreground"
                                                            )}>
                                                                {isCompleted ? (
                                                                    <Check size={14} />
                                                                ) : isActive ? (
                                                                    <Loader2 size={14} className="animate-spin" />
                                                                ) : (
                                                                    <StepIcon size={14} />
                                                                )}
                                                            </div>

                                                            {/* Step content */}
                                                            <div className="flex-1 min-w-0">
                                                                <div className={cn(
                                                                    "text-sm font-medium transition-colors",
                                                                    isCompleted && "text-green-600",
                                                                    isActive && "text-foreground",
                                                                    isPending && "text-muted-foreground"
                                                                )}>
                                                                    {step.label}
                                                                </div>
                                                                {step.file ? (
                                                                    <div className={cn(
                                                                        "text-xs font-mono transition-colors",
                                                                        isCompleted && "text-green-600/70",
                                                                        isActive && "text-muted-foreground animate-pulse",
                                                                        isPending && "text-muted-foreground/50"
                                                                    )}>
                                                                        {step.file}
                                                                    </div>
                                                                ) : null}
                                                            </div>

                                                            {/* Status indicator */}
                                                            {isCompleted && (
                                                                <motion.div
                                                                    initial={{ scale: 0 }}
                                                                    animate={{ scale: 1 }}
                                                                    className="text-xs text-green-600 font-medium"
                                                                >
                                                                    Done
                                                                </motion.div>
                                                            )}
                                                            {isActive && (
                                                                <div className="text-xs text-primary font-medium">
                                                                    In progress...
                                                                </div>
                                                            )}
                                                        </motion.div>
                                                    );
                                                })}
                                            </motion.div>
                                        )}

                                        {/* View Strategy Button when done */}
                                        {createdStrategy.chat_status === "done" && (
                                            <motion.div
                                                initial={{ opacity: 0, y: 10 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                className="flex justify-center pt-2"
                                            >
                                                <Button
                                                    onClick={() => onGoToStrategy(createdStrategy.id)}
                                                    className="gap-2 bg-green-600 hover:bg-green-700 text-white"
                                                >
                                                    <Check size={16} />
                                                    {t.viewDetails}
                                                </Button>
                                            </motion.div>
                                        )}
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Input Area */}
                        <div className="p-4 sm:p-6">
                            {createdStrategy && createdStrategy.chat_status === "chatting" ? (
                                /* Chat input for ongoing conversation */
                                <div>
                                    <Textarea
                                        ref={chatTextareaRef}
                                        value={chatInput}
                                        onChange={(e) => setChatInput(e.target.value)}
                                        onKeyDown={handleChatKeyDown}
                                        placeholder={t.chatPlaceholder}
                                        className="resize-none bg-muted/50 text-base leading-relaxed placeholder:text-muted-foreground/60"
                                        style={{ minHeight: `${chatMinHeight}px`, maxHeight: `${textareaMaxHeight}px` }}
                                        disabled={chatMutation.isPending}
                                    />
                                    <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
                                        <span className="text-sm text-muted-foreground">
                                            {t.inputHint}
                                        </span>
                                        <Button
                                            onClick={handleSendChatMessage}
                                            disabled={!chatInput.trim() || chatMutation.isPending}
                                            className="gap-2 bg-primary hover:bg-primary/90"
                                        >
                                            {chatMutation.isPending ? (
                                                <>
                                                    <Loader2 size={16} className="animate-spin" />
                                                    {t.sending}
                                                </>
                                            ) : (
                                                <>
                                                    <Send size={16} />
                                                    {t.sendMessage}
                                                </>
                                            )}
                                        </Button>
                                    </div>
                                </div>
                            ) : createdStrategy && (createdStrategy.chat_status === "ready" || createdStrategy.chat_status === "generating" || createdStrategy.chat_status === "done") ? (
                                /* Show status message when ready/generating/done */
                                <div className="text-center py-4 text-muted-foreground text-sm space-y-2">
                                    <div>
                                        {createdStrategy.chat_status === "ready" && (createdStrategy.chat_config && Object.keys(createdStrategy.chat_config).length > 0 ? t.statusReady : t.chatPlaceholder)}
                                        {createdStrategy.chat_status === "generating" && (
                                            <div className="flex items-center justify-center gap-2">
                                                <Loader2 size={15} className="animate-spin text-primary" />
                                                <span>{t.statusGenerating}</span>
                                                <span className="font-mono text-xs text-muted-foreground ml-1">
                                                    ({translate("dashboard.elapsedSeconds", { count: generatingElapsedSeconds, defaultValue: `已耗时 ${generatingElapsedSeconds} 秒` })})
                                                </span>
                                            </div>
                                        )}
                                        {createdStrategy.chat_status === "done" && t.statusDone}
                                    </div>
                                    {generateError && (
                                        <div className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2 inline-block">
                                            {generateError}
                                        </div>
                                    )}
                                    {createdStrategy.chat_status === "ready" && createdStrategy.chat_config && Object.keys(createdStrategy.chat_config).length > 0 ? (
                                        <motion.div
                                            initial={{ opacity: 0, y: 10 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="mt-4 mb-2 text-left"
                                        >
                                            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:bg-amber-950/20 dark:border-amber-800">
                                                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                                                    <FileText size={16} className="text-amber-700 dark:text-amber-400" />
                                                    {t.strategyConfigTitle}
                                                </div>
                                                <div className="grid grid-cols-2 gap-3 text-sm">
                                                    {Object.entries(createdStrategy.chat_config).map(([key, value]) => (
                                                        <div key={key} className="rounded-lg bg-white dark:bg-card p-2 shadow-sm">
                                                            <div className="text-xs text-muted-foreground capitalize">
                                                                {formatConfigLabel(key)}
                                                            </div>
                                                            <div className="font-medium text-foreground">
                                                                {formatConfigValue(value)}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                                <Button
                                                    onClick={() => generateMutation.mutate()}
                                                    disabled={generateMutation.isPending}
                                                    className="mt-4 w-full gap-2 bg-green-600 hover:bg-green-700 text-white shadow-sm"
                                                >
                                                    {generateMutation.isPending ? (
                                                        <>
                                                            <Loader2 size={16} className="animate-spin" />
                                                            {t.generating}
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Sparkles size={16} />
                                                            {t.confirmGenerate}
                                                        </>
                                                    )}
                                                </Button>
                                            </div>
                                        </motion.div>
                                    ) : createdStrategy.chat_status === "ready" ? (
                                        /* Fallback when ready but no config: show textarea so user can continue chatting */
                                        <div className="text-left mt-3">
                                            <Textarea
                                                ref={chatTextareaRef}
                                                value={chatInput}
                                                onChange={(e) => setChatInput(e.target.value)}
                                                onKeyDown={handleChatKeyDown}
                                                placeholder={t.chatPlaceholder}
                                                className="resize-none bg-muted/50 text-base leading-relaxed placeholder:text-muted-foreground/60"
                                                style={{ minHeight: `${chatMinHeight}px`, maxHeight: `${textareaMaxHeight}px` }}
                                                disabled={chatMutation.isPending}
                                            />
                                            <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
                                                <span className="text-sm text-muted-foreground">
                                                    {t.inputHint}
                                                </span>
                                                <div className="flex items-center gap-2">
                                                    <Button
                                                        variant="outline"
                                                        onClick={() => generateMutation.mutate()}
                                                        disabled={generateMutation.isPending}
                                                        className="gap-2"
                                                    >
                                                        <Sparkles size={16} />
                                                        {t.confirmGenerate}
                                                    </Button>
                                                    <Button
                                                        onClick={handleSendChatMessage}
                                                        disabled={!chatInput.trim() || chatMutation.isPending}
                                                        className="gap-2 bg-primary hover:bg-primary/90"
                                                    >
                                                        {chatMutation.isPending ? (
                                                            <>
                                                                <Loader2 size={16} className="animate-spin" />
                                                                {t.sending}
                                                            </>
                                                        ) : (
                                                            <>
                                                                <Send size={16} />
                                                                {t.sendMessage}
                                                            </>
                                                        )}
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    ) : null}
                                </div>
                            ) : (
                                /* Initial creation input */
                                <form onSubmit={handleSubmit}>
                                    <div className="mb-3 flex flex-wrap items-center gap-2">
                                        <span className="text-xs font-medium text-muted-foreground flex items-center gap-1 mr-1">
                                            <Sparkles size={12} className="text-primary" />
                                            {t.quickInspirations || "快捷灵感"}:
                                        </span>
                                        {[
                                            {
                                                label: "BTC 均线交叉",
                                                desc: "BTC-USDT 1小时级别，双均线金叉做多死叉做空，附带 2% 追踪止损",
                                            },
                                            {
                                                label: "ETH 布林带突破",
                                                desc: "ETH-USDT 15分钟级别，突破布林带上轨做多，跌破中轨平仓，止损 1.5%",
                                            },
                                            {
                                                label: "SOL RSI 超卖反弹",
                                                desc: "SOL-USDT 1小时级别，RSI 低于 30 超卖反弹买入，高于 70 止盈",
                                            },
                                        ].map((preset) => (
                                            <button
                                                key={preset.label}
                                                type="button"
                                                onClick={() => {
                                                    setPrompt(preset.desc);
                                                    if (promptTextareaRef.current) {
                                                        promptTextareaRef.current.focus();
                                                    }
                                                }}
                                                className="inline-flex items-center gap-1 rounded-full border border-border/80 bg-background/80 px-2.5 py-1 text-xs text-muted-foreground transition-all hover:border-primary/50 hover:bg-primary/5 hover:text-foreground"
                                            >
                                                <span>{preset.label}</span>
                                            </button>
                                        ))}
                                    </div>
                                    <Textarea
                                        ref={promptTextareaRef}
                                        value={prompt}
                                        onChange={(e) => setPrompt(e.target.value)}
                                        onKeyDown={handleKeyDown}
                                        placeholder={t.inputPlaceholder}
                                        className="resize-none bg-muted/50 text-base leading-relaxed placeholder:text-muted-foreground/60"
                                        style={{ minHeight: `${promptMinHeight}px`, maxHeight: `${textareaMaxHeight}px` }}
                                        disabled={isCreating}
                                    />
                                    <div className="flex flex-col gap-3 mt-4 pt-4 border-t border-border sm:flex-row sm:items-center sm:justify-between">
                                        <span className="text-sm text-muted-foreground">
                                            {t.inputHint}
                                        </span>
                                        <div className="flex flex-wrap items-center gap-3">
                                            <Button
                                                type="button"
                                                variant="outline"
                                                onClick={() => {
                                                    if (onRequireAuth()) return;
                                                    setShowImportStrategyModal(true);
                                                }}
                                                className="gap-2"
                                            >
                                                <Download size={16} />
                                                {t.importStrategyCta}
                                            </Button>
                                            <Button
                                                type="submit"
                                                disabled={!prompt.trim() || isCreating}
                                                className="gap-2 bg-primary hover:bg-primary/90"
                                            >
                                                {isCreating ? (
                                                    <>
                                                        <Loader2 size={16} className="animate-spin" />
                                                        {t.createStatus}
                                                    </>
                                                ) : (
                                                    <>
                                                        <Send size={16} />
                                                        {t.createCta}
                                                    </>
                                                )}
                                            </Button>
                                        </div>
                                    </div>
                                </form>
                            )}
                        </div>
                    </motion.div>

                    {/* Template & Subscription Quick Access */}
                    <motion.div
                        initial={{ y: 20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        transition={{ delay: 0.35 }}
                        className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8"
                    >
                        <motion.button
                            onClick={() => navigate("/templates")}
                            whileHover={{ y: -2 }}
                            className="bg-card rounded-xl p-5 border border-border text-left hover:shadow-lg hover:border-primary/20 transition-all group"
                        >
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-orange-100 text-orange-600">
                                        <Library size={20} />
                                    </div>
                                    <div>
                                        <h3 className="font-medium text-foreground group-hover:text-primary transition-colors">
                                            {t.actions.browseTemplatesTitle}
                                        </h3>
                                        <p className="text-sm text-muted-foreground">
                                            {t.actions.browseTemplatesSubtitle}
                                        </p>
                                    </div>
                                </div>
                                <ArrowRight size={16} className="text-muted-foreground group-hover:text-primary transition-colors mt-1" />
                            </div>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <Tag size={12} />
                                <span>{t.actions.browseTemplatesHint}</span>
                            </div>
                        </motion.button>

                        <motion.button
                            onClick={() => navigate("/subscriptions")}
                            whileHover={{ y: -2 }}
                            className="bg-card rounded-xl p-5 border border-border text-left hover:shadow-lg hover:border-primary/20 transition-all group"
                        >
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-green-100 text-green-600">
                                        <Star size={20} />
                                    </div>
                                    <div>
                                        <h3 className="font-medium text-foreground group-hover:text-primary transition-colors">
                                            {t.actions.subscriptionsTitle}
                                        </h3>
                                        <p className="text-sm text-muted-foreground">
                                            {t.actions.subscriptionsSubtitle}
                                        </p>
                                    </div>
                                </div>
                                <ArrowRight size={16} className="text-muted-foreground group-hover:text-primary transition-colors mt-1" />
                            </div>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <RefreshCcw size={12} />
                                <span>{t.actions.subscriptionsHint}</span>
                            </div>
                        </motion.button>
                    </motion.div>

                    {/* Recent Strategies */}
                    {!createdStrategy && (
                        <motion.div
                            initial={{ y: 20, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: 0.4 }}
                        >
                            <Tabs value={activeTab} onValueChange={setActiveTab} className="mb-6">
                                <TabsList className="bg-muted/50">
                                    <TabsTrigger value="recent">{t.tabs.recent}</TabsTrigger>
                                    <TabsTrigger value="my">{t.tabs.my}</TabsTrigger>
                                    <TabsTrigger value="templates">{t.tabs.templates}</TabsTrigger>
                                </TabsList>
                            </Tabs>

                            {/* Trending Strategies Section */}
                            {activeTab === "recent" && TRENDING_ENABLED && (
                                <motion.div
                                    initial={{ y: 10, opacity: 0 }}
                                    animate={{ y: 0, opacity: 1 }}
                                    transition={{ delay: 0.45 }}
                                    className="mb-6"
                                >
                                    <TrendingSection />
                                </motion.div>
                            )}

                            {activeTab === "templates" ? (
                                /* Templates Grid */
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {strategyTemplates.map((template) => (
                                        <motion.button
                                            key={template.id}
                                            onClick={() => {
                                                setPrompt(template.prompt);
                                                window.scrollTo({ top: 0, behavior: "smooth" });
                                            }}
                                            whileHover={{ y: -2 }}
                                            className="bg-card rounded-xl p-5 border border-border text-left hover:shadow-lg hover:border-primary/20 transition-all group"
                                        >
                                            <div className="flex items-start justify-between mb-2">
                                                <div>
                                                    <span className="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-primary/10 text-primary mb-2">
                                                        {template.category}
                                                    </span>
                                                    <h3 className="font-medium text-foreground group-hover:text-primary transition-colors">
                                                        {template.name}
                                                    </h3>
                                                </div>
                                                <ArrowRight size={16} className="text-muted-foreground group-hover:text-primary transition-colors mt-1" />
                                            </div>
                                            <p className="text-sm text-muted-foreground line-clamp-2">
                                                {template.description}
                                            </p>
                                        </motion.button>
                                    ))}
                                </div>
                            ) : strategies.length === 0 ? (
                                <div className="text-center py-12 text-muted-foreground">
                                    <p>{t.emptyStrategies}</p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    {strategies.slice(0, 9).map((strategy) => (
                                        <motion.button
                                            key={strategy.id}
                                            onClick={() => onSelectStrategy(strategy)}
                                            whileHover={{ y: -2 }}
                                            className="bg-card rounded-xl p-4 border border-border text-left hover:shadow-lg hover:border-primary/20 transition-all group"
                                        >
                                            <div className="flex items-start justify-between mb-2">
                                                <h3 className="font-medium text-foreground group-hover:text-primary transition-colors truncate pr-2">
                                                    {strategy.name}
                                                </h3>
                                                <div
                                                    className={cn(
                                                        "w-2 h-2 rounded-full shrink-0 mt-1.5",
                                                        getStatusColor(strategy.chat_status)
                                                    )}
                                                />
                                            </div>
                                            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                                                <Clock size={14} />
                                                <span>{formatDate(strategy.created_at)}</span>
                                            </div>
                                        </motion.button>
                                    ))}
                                </div>
                            )}
                        </motion.div>
                    )}
                </div>
            </div>

            <Dialog
                open={isImportOpen}
                onOpenChange={(open) => {
                    setIsImportOpen(open);
                    if (!open) resetImportState();
                }}
            >
                <DialogContent className="max-w-3xl border-orange-100 bg-white/95 p-0">
                    <div className="border-b border-orange-100 px-4 py-5 sm:px-8 sm:py-6">
                        <div className="flex items-center gap-3">
                            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-orange-50 text-orange-600">
                                <Github className="h-6 w-6" />
                            </div>
                            <div>
                                <h2 className="text-xl font-semibold text-foreground">{t.import.title}</h2>
                                <p className="text-sm text-muted-foreground">{t.import.subtitle}</p>
                            </div>
                        </div>
                    </div>

                    <div className="px-4 py-5 sm:px-8 sm:py-6">
                        {importStage === "connect" && (
                            <div className="grid gap-6">
                                <div className="grid gap-4 text-center">
                                    <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-orange-500 to-orange-400 text-white shadow-lg">
                                        <Github className="h-9 w-9" />
                                    </div>
                                    <div>
                                        <h3 className="text-2xl font-semibold text-foreground">
                                            {t.import.connectTitle}
                                        </h3>
                                        <p className="mt-2 text-sm text-muted-foreground">
                                            {t.import.connectSubtitle}
                                        </p>
                                    </div>
                                </div>
                                <div className="mx-auto grid w-full max-w-md gap-3 text-sm text-muted-foreground">
                                    {t.import.connectBenefits.map((benefit: string) => (
                                        <div key={benefit} className="flex items-center gap-3 rounded-xl bg-orange-50/60 px-4 py-3">
                                            <ShieldCheck className="h-4 w-4 text-orange-500" />
                                            <span>{benefit}</span>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex flex-col items-center gap-3">
                                    <Button
                                        className="gap-2 bg-primary px-5 text-base hover:bg-primary/90 sm:px-8"
                                        onClick={() => setImportStage("select")}
                                    >
                                        <Github size={18} />
                                        {t.import.connectAction}
                                    </Button>
                                    <p className="text-xs text-muted-foreground text-center">
                                        {t.import.firstTime}
                                        <button
                                            type="button"
                                            onClick={() => window.open(githubInstallUrl, "_blank")}
                                            className="text-primary hover:underline"
                                        >
                                            {t.import.installFirst}
                                        </button>
                                    </p>
                                </div>
                            </div>
                        )}

                        {importStage === "select" && (
                            <div className="grid gap-6">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-lg font-semibold text-foreground">{t.import.selectTitle}</h3>
                                    <Button variant="ghost" size="sm" onClick={() => setImportStage("connect")}>
                                        {t.import.back}
                                    </Button>
                                </div>
                                <div className="relative">
                                    <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" />
                                    <Input
                                        value={repoSearch}
                                        onChange={(e) => setRepoSearch(e.target.value)}
                                        placeholder={t.import.searchPlaceholder}
                                        className="pl-10"
                                    />
                                </div>
                                {installationsQuery.isLoading && (
                                    <div className="flex items-center justify-center py-8 text-muted-foreground">
                                        <Loader2 className="h-6 w-6 animate-spin" />
                                        <span className="ml-2">{t.import.loadingInstallations}</span>
                                    </div>
                                )}
                                {installationsQuery.isError && (
                                    <div className="text-center py-8">
                                        <p className="text-red-500 mb-4">
                                            {t.import.loadInstallationsFailed}
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-4">
                                            {t.import.installHint}
                                        </p>
                                        <div className="flex flex-col items-center gap-2">
                                            <Button
                                                onClick={() => window.open(githubInstallUrl, "_blank")}
                                                className="gap-2 bg-primary hover:bg-primary/90"
                                            >
                                                <Github size={16} />
                                                {t.import.installCta}
                                            </Button>
                                            <p className="text-xs text-muted-foreground">
                                                {t.import.installAccessHint}
                                            </p>
                                        </div>
                                    </div>
                                )}
                                {installationsQuery.data && installationsQuery.data.length === 0 && (
                                    <div className="text-center py-8">
                                        <p className="text-muted-foreground mb-4">
                                            {t.import.noInstallations}
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-4">
                                            {t.import.installHint}
                                        </p>
                                        <div className="flex flex-col items-center gap-2">
                                            <Button
                                                onClick={() => window.open(githubInstallUrl, "_blank")}
                                                className="gap-2 bg-primary hover:bg-primary/90"
                                            >
                                                <Github size={16} />
                                                {t.import.installCta}
                                            </Button>
                                            <p className="text-xs text-muted-foreground">
                                                {t.import.installAccessHint}
                                            </p>
                                        </div>
                                    </div>
                                )}
                                {reposQuery.isLoading && !installationsQuery.isLoading && (
                                    <div className="flex items-center justify-center py-8 text-muted-foreground">
                                        <Loader2 className="h-6 w-6 animate-spin" />
                                        <span className="ml-2">{t.import.loadingRepos}</span>
                                    </div>
                                )}
                                {reposQuery.isError && (
                                    <div className="text-center py-8 text-red-500">
                                        {t.import.loadReposFailed}
                                    </div>
                                )}
                                {!reposQuery.isLoading && !installationsQuery.isLoading && filteredRepos.length === 0 && selectedInstallationId && (
                                    <div className="text-center py-8 text-muted-foreground">
                                        {t.import.noRepos}
                                    </div>
                                )}
                                <div className="grid gap-4">
                                    {filteredRepos.map((repo) => {
                                        const isSelected = selectedGitHubRepo?.id === repo.id;
                                        return (
                                            <button
                                                key={repo.id}
                                                type="button"
                                                onClick={() => setSelectedGitHubRepo(repo)}
                                                className={cn(
                                                    "rounded-2xl border p-4 text-left transition",
                                                    isSelected
                                                        ? "border-orange-400 bg-orange-50 shadow-sm"
                                                        : "border-orange-100 hover:border-orange-200"
                                                )}
                                            >
                                                <div className="flex items-start justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <Folder className="h-5 w-5 text-orange-500" />
                                                        <div className="flex items-center gap-2">
                                                            <span className="font-semibold text-foreground">{repo.name}</span>
                                                            {repo.private && (
                                                                <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-xs text-orange-700">
                                                                    <Lock className="h-3 w-3" />
                                                                    {t.metadata.private}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                    {isSelected && <CheckCircle2 className="h-5 w-5 text-orange-500" />}
                                                </div>
                                                {repo.full_name && (
                                                    <p className="mt-2 text-sm text-muted-foreground">{repo.full_name}</p>
                                                )}
                                                <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                                                    {repo.default_branch && (
                                                        <span className="inline-flex items-center gap-1">
                                                            <GitBranch className="h-3 w-3" />
                                                            {repo.default_branch}
                                                        </span>
                                                    )}
                                                </div>
                                            </button>
                                        );
                                    })}
                                </div>
                                <div className="flex items-center justify-between">
                                    <Button variant="ghost" onClick={() => setImportStage("connect")}>
                                        {t.import.back}
                                    </Button>
                                    <Button
                                        onClick={() => importMutation.mutate()}
                                        disabled={!selectedGitHubRepo || importMutation.isPending}
                                        className="gap-2 bg-primary px-6 hover:bg-primary/90"
                                    >
                                        {importMutation.isPending ? (
                                            <>
                                                <Loader2 className="h-4 w-4 animate-spin" />
                                                Importing...
                                            </>
                                        ) : (
                                            <>
                                                {t.import.startImport}
                                                <ArrowRight className="h-4 w-4" />
                                            </>
                                        )}
                                    </Button>
                                </div>
                            </div>
                        )}

                        {importStage === "progress" && selectedGitHubRepo && (
                            <div className="grid gap-6">
                                <div className="flex items-center justify-between">
                                    <Button variant="ghost" size="sm" onClick={() => setImportStage("select")}>
                                        {t.import.back}
                                    </Button>
                                    <span className="inline-flex items-center gap-2 rounded-full bg-orange-50 px-4 py-1 text-sm text-orange-600">
                                        <Folder className="h-4 w-4" />
                                        {selectedGitHubRepo.full_name || selectedGitHubRepo.name}
                                    </span>
                                </div>
                                <div className="text-center">
                                    <h3 className="text-2xl font-semibold text-foreground">{t.import.progressTitle}</h3>
                                    <p className="mt-2 text-sm text-muted-foreground">{t.import.progressSubtitle}</p>
                                </div>
                                <div>
                                    <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
                                        <span>{t.import.progressLabel}</span>
                                        <span>{importProgress}%</span>
                                    </div>
                                    <div className="h-2 w-full rounded-full bg-muted">
                                        <div
                                            className="h-2 rounded-full bg-gradient-to-r from-orange-400 to-orange-500 transition-all"
                                            style={{ width: `${importProgress}%` }}
                                        />
                                    </div>
                                </div>
                                <div className="grid gap-3">
                                    {t.import.steps.map((step: { label: string; detail: string }, index: number) => {
                                        const isCompleted = index < importStepIndex;
                                        const isActive = index === importStepIndex;
                                        return (
                                            <div
                                                key={step.label}
                                                className={cn(
                                                    "flex items-center gap-4 rounded-2xl border px-4 py-3",
                                                    isActive
                                                        ? "border-orange-300 bg-orange-50"
                                                        : "border-orange-100 bg-white"
                                                )}
                                            >
                                                <div
                                                    className={cn(
                                                        "flex h-10 w-10 items-center justify-center rounded-full",
                                                        isCompleted && "bg-green-500 text-white",
                                                        isActive && "bg-orange-500 text-white",
                                                        !isCompleted && !isActive && "bg-muted text-muted-foreground"
                                                    )}
                                                >
                                                    {isCompleted ? (
                                                        <Check className="h-5 w-5" />
                                                    ) : isActive ? (
                                                        <Loader2 className="h-5 w-5 animate-spin" />
                                                    ) : index === 2 ? (
                                                        <Database className="h-5 w-5" />
                                                    ) : index === 3 ? (
                                                        <Settings className="h-5 w-5" />
                                                    ) : (
                                                        <RefreshCcw className="h-5 w-5" />
                                                    )}
                                                </div>
                                                <div className="flex-1">
                                                    <div className="text-sm font-semibold text-foreground">
                                                        {step.label}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">{step.detail}</div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {importStage === "done" && (
                            <div className="grid gap-6 text-center">
                                <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-green-500 text-white shadow-lg">
                                    <Check className="h-9 w-9" />
                                </div>
                                <div>
                                    <h3 className="text-2xl font-semibold text-foreground">{t.import.doneTitle}</h3>
                                    <p className="mt-2 text-sm text-muted-foreground">{t.import.doneSubtitle}</p>
                                </div>
                                <div className="mx-auto grid w-full max-w-md grid-cols-3 gap-3">
                                    <div className="rounded-2xl border border-orange-100 bg-orange-50/60 px-4 py-4">
                                        <FileText className="mx-auto mb-2 h-5 w-5 text-orange-500" />
                                        <div className="text-lg font-semibold text-foreground">12</div>
                                        <div className="text-xs text-muted-foreground">{t.import.stats.files}</div>
                                    </div>
                                    <div className="rounded-2xl border border-orange-100 bg-orange-50/60 px-4 py-4">
                                        <FileCode className="mx-auto mb-2 h-5 w-5 text-orange-500" />
                                        <div className="text-lg font-semibold text-foreground">2.4k</div>
                                        <div className="text-xs text-muted-foreground">{t.import.stats.lines}</div>
                                    </div>
                                    <div className="rounded-2xl border border-orange-100 bg-orange-50/60 px-4 py-4">
                                        <Database className="mx-auto mb-2 h-5 w-5 text-orange-500" />
                                        <div className="text-lg font-semibold text-foreground">{t.import.stats.ready}</div>
                                        <div className="text-xs text-muted-foreground">{t.import.stats.kb}</div>
                                    </div>
                                </div>
                                <div className="flex justify-center">
                                    <Button
                                        className="gap-2 bg-primary px-5 text-base hover:bg-primary/90 sm:px-8"
                                        onClick={() => {
                                            setIsImportOpen(false);
                                            if (importedStrategyId) {
                                                onGoToStrategy(importedStrategyId);
                                            }
                                            resetImportState();
                                        }}
                                    >
                                        {t.import.doneAction}
                                        <ArrowRight className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                </DialogContent>
            </Dialog>

            <ImportStrategyModal
                open={showImportStrategyModal}
                onOpenChange={setShowImportStrategyModal}
            />
        </div>
    );
};

export default DashboardHome;
