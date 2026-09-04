import { useState, useEffect, useMemo, useRef } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
    Send,
    Loader2,
    Clock,
    Sparkles,
    Check,
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
    Settings,
    FileText,
    FileCode,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Strategy, GitHubRepo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { githubApi, reposApi, jobsApi } from "@/lib/api";
import React from "react";
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
    onRequireAuth: () => boolean;
}

const STRATEGY_DRAFT_STORAGE_KEY = "dashboard_strategy_draft_v1";
const STRATEGY_PENDING_STORAGE_KEY = "dashboard_strategy_pending_create_v1";

const Github = ({ className, size = 24 }: { className?: string; size?: number }) => (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
        <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
);

const DashboardHome = ({
    onNewStrategy,
    strategies,
    onSelectStrategy,
    isCreating = false,
    isAuthed,
    onRequireAuth,
}: DashboardHomeProps) => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [prompt, setPrompt] = useState("");
    const [activeTab, setActiveTab] = useState("recent");
    const promptTextareaRef = useRef<HTMLTextAreaElement>(null);
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
            const parsed = JSON.parse(stored) as { prompt?: string };
            if (parsed.prompt) setPrompt(parsed.prompt);
        } catch {
            window.localStorage.removeItem(STRATEGY_DRAFT_STORAGE_KEY);
        }
    }, []);

    useEffect(() => {
        if (typeof window === "undefined") return;
        if (!prompt.trim()) {
            window.localStorage.removeItem(STRATEGY_DRAFT_STORAGE_KEY);
            return;
        }
        window.localStorage.setItem(
            STRATEGY_DRAFT_STORAGE_KEY,
            JSON.stringify({ prompt, updatedAt: Date.now() })
        );
    }, [prompt]);

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

    useEffect(() => {
        autoResizeTextarea(promptTextareaRef.current, promptMinHeight, textareaMaxHeight);
    }, [prompt, promptMinHeight, textareaMaxHeight]);

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

    const handleSubmit = (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!prompt.trim() || isCreating) return;
        if (!isAuthed && typeof window !== "undefined") {
            window.localStorage.setItem(
                STRATEGY_PENDING_STORAGE_KEY,
                JSON.stringify({ prompt, createdAt: Date.now() })
            );
        }
        window.localStorage.removeItem(STRATEGY_DRAFT_STORAGE_KEY);
        onNewStrategy(prompt);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
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
                        <div className="p-4 sm:p-6">
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
                                                navigate(`/strategy/${importedStrategyId}/overview`);
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
