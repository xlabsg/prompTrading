import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Home, TrendingUp, Layout, Tag, type LucideIcon } from "lucide-react";
import { AppSidebar, type PageType } from "./AppSidebar";
import { MobileBottomNav } from "./MobileBottomNav";
import type { Strategy } from "@/lib/types";
import { authApi, strategiesApi } from "@/lib/api";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/common/LanguageSwitcher";
import { AuthDialog } from "@/components/auth/AuthDialog";

interface PageConfig {
    title: string;
    description: string;
    icon: LucideIcon;
}

interface MainLayoutProps {
    children: ReactNode;
    currentPage: PageType;
    title?: string;
    description?: string;
    headerActions?: ReactNode;
    onStrategySelect?: (strategy: Strategy) => void;
}

export const MainLayout = ({
    children,
    currentPage,
    title,
    description,
    headerActions,
    onStrategySelect,
}: MainLayoutProps) => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [isAuthOpen, setIsAuthOpen] = useState(false);
    const [authStep, setAuthStep] = useState<"login" | "register">("login");

    const pageConfigs = useMemo<Record<PageType, PageConfig>>(
        () => ({
            home: {
                title: t("nav.dashboard"),
                description: t("nav.dashboardDesc"),
                icon: Home,
            },
            trending: {
                title: t("nav.trending"),
                description: t("nav.trendingDesc"),
                icon: TrendingUp,
            },
            templates: {
                title: t("nav.templates"),
                description: t("nav.templatesDesc"),
                icon: Layout,
            },
            subscriptions: {
                title: t("nav.subscriptions"),
                description: t("nav.subscriptionsDesc"),
                icon: Tag,
            },
        }),
        [t],
    );

    // Fetch user data
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

    const user = authQuery.data?.user ?? null;
    const isAuthed = Boolean(user);
    const isAdmin = Boolean(authQuery.data?.is_admin);

    useEffect(() => {
        if (typeof window === "undefined") return;
        const handler = () => {
            setAuthStep("login");
            setIsAuthOpen(true);
        };
        window.addEventListener("auth-required", handler);
        return () => window.removeEventListener("auth-required", handler);
    }, []);

    // Fetch strategies
    const { data: strategies = [], error: strategiesError } = useQuery({
        queryKey: ["strategies"],
        queryFn: strategiesApi.list,
        refetchInterval: 5000,
        enabled: isAuthed,
        retry: false,
    });

    const pageConfig = pageConfigs[currentPage];
    const displayTitle = title || pageConfig.title;
    const displayDescription = description || pageConfig.description;
    const Icon = pageConfig.icon;

    const handleStrategySelect = (strategy: Strategy) => {
        if (onStrategySelect) {
            onStrategySelect(strategy);
        } else {
            navigate(`/strategy/${strategy.id}`);
        }
    };

    return (
        <>
            <div className="h-screen flex bg-background overflow-hidden">
                <div className="hidden md:flex">
                    <AppSidebar
                        currentPage={currentPage}
                        strategies={strategies}
                        user={user}
                        isAdmin={isAdmin}
                        onStrategySelect={handleStrategySelect}
                        error={strategiesError}
                        isAuthed={isAuthed}
                    />
                </div>

                <div className="flex-1 flex flex-col overflow-hidden">
                    <header className="border-b border-border px-4 py-4 sm:p-6">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-primary/10 rounded-lg">
                                    <Icon className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                                </div>
                                <div>
                                    <h1 className="text-xl font-bold sm:text-2xl">{displayTitle}</h1>
                                    <p className="text-sm text-muted-foreground sm:text-base sm:mt-0.5">
                                        {displayDescription}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center justify-between gap-2 sm:justify-end sm:gap-3">
                                <LanguageSwitcher />
                                {headerActions && <div>{headerActions}</div>}
                            </div>
                        </div>
                    </header>

                    <div className="flex-1 overflow-y-auto pb-24 md:pb-0">
                        {children}
                    </div>
                </div>

                <MobileBottomNav />
            </div>
            <AuthDialog open={isAuthOpen} onOpenChange={setIsAuthOpen} initialStep={authStep} />
        </>
    );
};

export default MainLayout;
