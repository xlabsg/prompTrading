import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import ConsoleSidebar from "@/components/console/ConsoleSidebar";
import ConsoleHeader from "@/components/console/ConsoleHeader";
import DashboardHome from "@/components/console/DashboardHome";
import StrategyOverviewView from "@/views/StrategyOverviewView";
import CodeView from "@/components/console/CodeView";
import BacktestView from "@/components/console/BacktestView";
import LiveTradingView from "@/components/console/LiveTradingView";
import PortfolioMonitorView from "@/components/console/PortfolioMonitorView";
import LogsView from "@/components/console/LogsView";
import SignalsView from "@/components/console/SignalsView";
import { AuthDialog } from "@/components/auth/AuthDialog";
import { MainLayout } from "@/components/layout/MainLayout";
import { authApi, strategiesApi } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/common/LanguageSwitcher";

export type ViewType = "overview" | "code" | "backtest" | "live" | "portfolio" | "logs" | "signals";

// Re-export Strategy type for components
export type { Strategy } from "@/lib/types";

const STRATEGY_PENDING_STORAGE_KEY = "dashboard_strategy_pending_create_v1";
const SIDEBAR_WIDTH_STORAGE_KEY = "console_sidebar_width_v1";
const SIDEBAR_DEFAULT_WIDTH = 460;
const SIDEBAR_MIN_WIDTH = 420;
const SIDEBAR_MAX_WIDTH = 760;
const SIDEBAR_COLLAPSED_WIDTH = 64;

const clampSidebarWidth = (width: number) => Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width));

const Console = () => {
    const { strategyId, tab } = useParams<{ strategyId?: string; tab?: string }>();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { t } = useTranslation();

    // Valid tab values
    const validTabs: ViewType[] = ["overview", "code", "backtest", "live", "portfolio", "logs", "signals"];
    const initialTab = tab && validTabs.includes(tab as ViewType) ? (tab as ViewType) : "overview";

    const [currentView, setCurrentView] = useState<ViewType>(initialTab);
    const [activeBacktestRunId, setActiveBacktestRunId] = useState<string | undefined>();
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const [isAuthOpen, setIsAuthOpen] = useState(false);
    const [authStep, setAuthStep] = useState<"login" | "register">("register");
    const [sidebarDialogOpen, setSidebarDialogOpen] = useState(false);
    const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
        if (typeof window === "undefined") return SIDEBAR_DEFAULT_WIDTH;
        const storedWidth = Number(window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
        return Number.isFinite(storedWidth) ? clampSidebarWidth(storedWidth) : SIDEBAR_DEFAULT_WIDTH;
    });
    const [isResizingSidebar, setIsResizingSidebar] = useState(false);
    const sidebarResizeStartRef = useRef<{ startX: number; startWidth: number } | null>(null);
    const sidebarResizeRafRef = useRef<number | null>(null);

    // Sync URL with tab changes
    const handleViewChange = (view: ViewType, targetId?: string) => {
        setCurrentView(view);
        if (view === "backtest" && targetId) {
            setActiveBacktestRunId(targetId);
        }
        if (strategyId) {
            navigate(`/strategy/${strategyId}/${view}`, { replace: true });
        }
    };

    // Sync state with URL on URL change
    useEffect(() => {
        if (tab && validTabs.includes(tab as ViewType)) {
            setCurrentView(tab as ViewType);
        }
    }, [tab]);

    // Default to backtest when no tab is provided
    useEffect(() => {
        if (!strategyId) return;
        if (!tab || !validTabs.includes(tab as ViewType)) {
            setCurrentView("overview");
            navigate(`/strategy/${strategyId}/overview`, { replace: true });
        }
    }, [strategyId, tab]);

    const authQuery = useQuery({
        queryKey: ["auth-me"],
        queryFn: async () => {
            try {
                return await authApi.me();
            } catch {
                return null;
            }
        },
        retry: false,
    });

    const isAuthed = Boolean(authQuery.data?.user);

    // Auth header buttons
    const authHeaderActions = !isAuthed ? (
        <div className="flex items-center gap-3">
            <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                    setAuthStep("login");
                    setIsAuthOpen(true);
                }}
            >
                {t("common.logIn")}
            </Button>
            <Button
                size="sm"
                onClick={() => {
                    setAuthStep("register");
                    setIsAuthOpen(true);
                }}
            >
                {t("common.signUp")}
            </Button>
        </div>
    ) : null;

    // Fetch strategies from API
    const { data: strategies = [], error } = useQuery({
        queryKey: ["strategies"],
        queryFn: strategiesApi.list,
        refetchInterval: 5000,
        enabled: isAuthed,
        retry: false,
    });

    const strategyQuery = useQuery({
        queryKey: ["strategy", strategyId],
        queryFn: () => strategiesApi.get(strategyId!),
        enabled: Boolean(strategyId && isAuthed),
        retry: false,
    });

    // Get current strategy from URL param
    const selectedStrategy = strategyId
        ? strategies.find(s => s.id === strategyId) || strategyQuery.data || null
        : null;

    // Create strategy mutation
    const createStrategyMutation = useMutation({
        mutationFn: (prompt?: string) => strategiesApi.create(prompt ? prompt.slice(0, 50) : undefined),
        onSuccess: (newStrategy, prompt) => {
            queryClient.invalidateQueries({ queryKey: ["strategies"] });
            if (prompt) {
                sessionStorage.setItem("pending_chat_message", prompt);
            }
            if (typeof window !== "undefined" && window.innerWidth < 768) {
                setSidebarDialogOpen(true);
            }
            navigate(`/strategy/${newStrategy.id}/overview`);
        },
    });

    useEffect(() => {
        if (!isAuthed || typeof window === "undefined") return;
        const stored = window.localStorage.getItem(STRATEGY_PENDING_STORAGE_KEY);
        if (!stored) return;
        window.localStorage.removeItem(STRATEGY_PENDING_STORAGE_KEY);
        try {
            const parsed = JSON.parse(stored) as { prompt?: string };
            const prompt = parsed.prompt?.trim();
            if (prompt) {
                createStrategyMutation.mutate(prompt);
            }
        } catch {
            // Ignore malformed stored data
        }
    }, [isAuthed, createStrategyMutation]);

    const handleNewStrategy = (prompt?: string) => {
        if (!isAuthed) {
            setIsAuthOpen(true);
            return;
        }
        createStrategyMutation.mutate(prompt);
    };

    const handleRequireAuth = () => {
        if (!isAuthed) {
            setIsAuthOpen(true);
            return true; // authentication required
        }
        return false; // already authenticated
    };

    const handleSelectStrategy = (strategy: Strategy) => {
        navigate(`/strategy/${strategy.id}`);
    };

    const handleBackToDashboard = () => {
        navigate("/");
    };

    const handleSidebarResizeStart = (event: React.PointerEvent<HTMLDivElement>) => {
        if (sidebarCollapsed) return;
        event.preventDefault();
        sidebarResizeStartRef.current = {
            startX: event.clientX,
            startWidth: sidebarWidth,
        };
        setIsResizingSidebar(true);
    };

    useEffect(() => {
        if (typeof window === "undefined") return;
        window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth));
    }, [sidebarWidth]);

    useEffect(() => {
        if (!isResizingSidebar) return;

        const previousUserSelect = document.body.style.userSelect;
        document.body.style.userSelect = "none";

        const handlePointerMove = (event: PointerEvent) => {
            const resizeState = sidebarResizeStartRef.current;
            if (!resizeState) return;
            const nextWidth = clampSidebarWidth(resizeState.startWidth + (event.clientX - resizeState.startX));

            if (sidebarResizeRafRef.current !== null) {
                cancelAnimationFrame(sidebarResizeRafRef.current);
            }
            sidebarResizeRafRef.current = requestAnimationFrame(() => {
                setSidebarWidth(current => (current === nextWidth ? current : nextWidth));
                sidebarResizeRafRef.current = null;
            });
        };

        const stopResizing = () => {
            setIsResizingSidebar(false);
            sidebarResizeStartRef.current = null;
        };

        window.addEventListener("pointermove", handlePointerMove);
        window.addEventListener("pointerup", stopResizing);
        window.addEventListener("pointercancel", stopResizing);

        return () => {
            document.body.style.userSelect = previousUserSelect;
            window.removeEventListener("pointermove", handlePointerMove);
            window.removeEventListener("pointerup", stopResizing);
            window.removeEventListener("pointercancel", stopResizing);
            if (sidebarResizeRafRef.current !== null) {
                cancelAnimationFrame(sidebarResizeRafRef.current);
                sidebarResizeRafRef.current = null;
            }
        };
    }, [isResizingSidebar]);

    const renderView = () => {
        switch (currentView) {
            case "overview":
                return (
                    <StrategyOverviewView
                        strategy={selectedStrategy}
                        onNavigateToChat={(message) => {
                            // Navigate to code view (where sidebar shows chat)
                            handleViewChange("code");
                            // Store message in session to be picked up by sidebar
                            if (message) {
                                sessionStorage.setItem("pending_chat_message", message);
                            }
                        }}
                    />
                );
            case "code":
                return <CodeView strategy={selectedStrategy} />;
            case "backtest":
                return <BacktestView strategy={selectedStrategy} initialRunId={activeBacktestRunId} />;
            case "live":
                return (
                    <LiveTradingView
                        strategy={selectedStrategy}
                        onNavigateToPortfolio={() => handleViewChange("portfolio")}
                        onNavigateToChat={(message) => {
                            // Navigate to code view (where sidebar shows chat)
                            handleViewChange("code");
                            // Store message in session to be picked up by sidebar
                            if (message) {
                                sessionStorage.setItem("pending_chat_message", message);
                            }
                        }}
                    />
                );
            case "portfolio":
                return (
                    <PortfolioMonitorView
                        strategy={selectedStrategy}
                        onNavigateToLive={() => handleViewChange("live")}
                    />
                );
            case "logs":
                return selectedStrategy ? <LogsView strategy={selectedStrategy} /> : null;
            case "signals":
                return selectedStrategy ? <SignalsView strategy={selectedStrategy} /> : null;
            default:
                return <CodeView strategy={selectedStrategy} />;
        }
    };

    if (error) {
        return (
            <div className="h-screen flex items-center justify-center bg-background">
                <div className="text-center">
                    <p className="text-destructive mb-2">{t("console.errors.loadStrategies")}</p>
                    <p className="text-muted-foreground text-sm">{(error as Error).message}</p>
                </div>
            </div>
        );
    }

    // Dashboard view (no strategy selected)
    if (!strategyId) {
        return (
            <MainLayout currentPage="home" headerActions={authHeaderActions}>
                <DashboardHome
                    onNewStrategy={handleNewStrategy}
                    strategies={strategies}
                    onSelectStrategy={handleSelectStrategy}
                    isCreating={createStrategyMutation.isPending}
                    isAuthed={isAuthed}
                    onRequireAuth={handleRequireAuth}
                />
                <AuthDialog open={isAuthOpen} onOpenChange={setIsAuthOpen} initialStep={authStep} />
            </MainLayout>
        );
    }

    // Strategy detail view
    if (!selectedStrategy && strategyQuery.isLoading) {
        return (
            <div className="h-screen flex items-center justify-center bg-background">
                <p className="text-muted-foreground text-sm">{t("console.loadingStrategy")}</p>
            </div>
        );
    }

    return (
        <div className="h-screen min-h-0 flex bg-background overflow-hidden">
            <div
                className="hidden md:flex relative shrink-0"
                style={{ width: sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : sidebarWidth }}
            >
                <ConsoleSidebar
                    strategy={selectedStrategy}
                    onBackToDashboard={handleBackToDashboard}
                    collapsed={sidebarCollapsed}
                    onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
                    onStrategyGenerated={() => handleViewChange("code")}
                    onNavigateView={handleViewChange}
                />
                {!sidebarCollapsed && (
                    <div
                        role="separator"
                        aria-label="Resize chat sidebar"
                        aria-orientation="vertical"
                        onPointerDown={handleSidebarResizeStart}
                        className="group absolute right-0 top-0 z-20 h-full w-2 translate-x-1/2 cursor-col-resize touch-none"
                    >
                        <div
                            className={`mx-auto h-full w-px transition-colors ${isResizingSidebar ? "bg-primary" : "bg-border group-hover:bg-primary/60"}`}
                        />
                    </div>
                )}
            </div>

            <Dialog open={sidebarDialogOpen} onOpenChange={setSidebarDialogOpen}>
                <DialogContent className="h-[100dvh] w-[100vw] max-w-none rounded-none border-0 p-0">
                    <ConsoleSidebar
                        strategy={selectedStrategy}
                        onBackToDashboard={handleBackToDashboard}
                        collapsed={false}
                        onToggleCollapse={() => {}}
                        onStrategyGenerated={() => handleViewChange("code")}
                        variant="dialog"
                        onClose={() => setSidebarDialogOpen(false)}
                    />
                </DialogContent>
            </Dialog>

            <div className="flex-1 min-h-0 flex flex-col min-w-0">
                <ConsoleHeader
                    currentView={currentView}
                    onViewChange={handleViewChange}
                    strategy={selectedStrategy}
                    onOpenSidebar={() => setSidebarDialogOpen(true)}
                />

                <main className="flex-1 min-h-0 overflow-hidden">{renderView()}</main>
                <div className="lg:hidden border-t border-border bg-background px-4 py-2">
                    <LanguageSwitcher />
                </div>
            </div>
        </div>
    );
};

export default Console;
