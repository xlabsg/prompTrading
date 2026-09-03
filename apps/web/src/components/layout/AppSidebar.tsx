import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
    Home,
    Compass,
    Layout,
    Tag,
    Bell,
    Clock,
    LogOut,
    TrendingUp,
    AlertCircle,
    Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Strategy, User } from "@/lib/types";
import { authApi } from "@/lib/api";
import { Logo } from "@/components/Logo";
import { useTranslation } from "react-i18next";
import { TRENDING_ENABLED } from "@/lib/featureFlags";

export type PageType = "home" | "trending" | "templates" | "subscriptions";

interface AppSidebarProps {
    currentPage: PageType;
    strategies: Strategy[];
    user: User | null;
    isAdmin?: boolean;
    onStrategySelect: (strategy: Strategy) => void;
    error?: unknown;
    isAuthed: boolean;
}

export const AppSidebar = ({
    currentPage,
    strategies,
    user,
    isAdmin = false,
    onStrategySelect,
    error,
    isAuthed,
}: AppSidebarProps) => {
    const navigate = useNavigate();
    const [isLoggingOut, setIsLoggingOut] = useState(false);
    const { t } = useTranslation();

    const handleLogout = async () => {
        try {
            setIsLoggingOut(true);
            await authApi.logout();
            window.location.href = "/";
        } catch (error) {
            console.error("Logout failed:", error);
            setIsLoggingOut(false);
        }
    };

    const mainNavItems = [
        { icon: Home, label: t("nav.home"), path: "/", page: "home" as PageType },
        ...(TRENDING_ENABLED
            ? [{ icon: TrendingUp, label: t("nav.trending"), path: "/trending", page: "trending" as PageType }]
            : []),
        { icon: Layout, label: t("nav.templates"), path: "/templates", page: "templates" as PageType },
    ];
    const adminNavItems = isAdmin ? [
        { icon: Shield, label: t("nav.admin"), path: "/admin/trending", page: "home" as PageType },
    ] : [];

    const recentStrategies = strategies.slice(0, 5);

    const resourceItems = [
        ...(TRENDING_ENABLED ? [{ icon: Compass, label: t("sidebar.discover"), path: "/trending" }] : []),
    ];

    return (
        <aside className="w-56 bg-card/80 backdrop-blur-sm border-r border-border flex flex-col">
            {/* Logo */}
            <div className="h-14 px-4 flex items-center border-b border-border">
                <Logo size="sm" />
            </div>

            {/* Main Navigation */}
            <div className="p-3 space-y-1">
                {mainNavItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = currentPage === item.page;
                    return (
                        <button
                            key={item.path}
                            onClick={() => navigate(item.path)}
                            className={cn(
                                "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                                isActive
                                    ? "bg-primary/10 text-primary"
                                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                            )}
                        >
                            <Icon size={18} />
                            <span>{item.label}</span>
                        </button>
                    );
                })}
            </div>

            {/* Projects Section */}
            <div className="px-3 mt-2">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-3 py-2">
                    {t("sidebar.projects")}
                </div>
                {renderProjects()}
            </div>

            {/* Resources Section */}
            <div className="px-3 mt-4 flex-1">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-3 py-2">
                    {t("sidebar.resources")}
                </div>
                <div className="space-y-0.5">
                    {adminNavItems.map((item) => (
                        <button
                            key={item.path}
                            onClick={() => navigate(item.path)}
                            className={cn(
                                "w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm transition-colors",
                                window.location.pathname.startsWith("/admin/")
                                    ? "bg-primary/10 text-primary"
                                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                            )}
                        >
                            <item.icon size={16} />
                            <span>{item.label}</span>
                        </button>
                    ))}
                    {resourceItems.map((item, i) => {
                        const isActive = item.path ? window.location.pathname === item.path : false;
                        return (
                            <button
                                key={i}
                                onClick={() => item.path && navigate(item.path)}
                                className={cn(
                                    "w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm transition-colors",
                                    isActive
                                        ? "bg-primary/10 text-primary"
                                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                                )}
                            >
                                <item.icon size={16} />
                                <span>{item.label}</span>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* User Section */}
            {user && (
                <div className="p-3 border-t border-border">
                    <div className="flex items-center gap-2 px-2 py-2">
                        <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
                            <span className="text-sm font-medium text-primary">
                                {(user.name || user.email || "U").slice(0, 1).toUpperCase()}
                            </span>
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-foreground truncate">{user.name || t("console.defaultUser")}</div>
                            <div className="text-xs text-muted-foreground truncate">{user.email || "-"}</div>
                        </div>
                        <button
                            onClick={handleLogout}
                            disabled={isLoggingOut}
                            className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                            title={t("common.signOut")}
                        >
                            <LogOut size={16} />
                        </button>
                    </div>
                </div>
            )}
        </aside>
    );

    function renderProjects() {
        // Show error state but don't block the sidebar
        if (error) {
            return (
                <div className="px-3 py-2">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <AlertCircle size={14} className="text-destructive" />
                        <span>{t("sidebar.loadProjectsFailed")}</span>
                    </div>
                </div>
            );
        }

        // Not authenticated - show empty state
        if (!isAuthed) {
            return (
                <div className="px-3 py-2">
                    <div className="text-xs text-muted-foreground">{t("sidebar.signInToSeeProjects")}</div>
                </div>
            );
        }

        // No strategies
        if (recentStrategies.length === 0) {
            return (
                <div className="px-3 py-2">
                    <div className="text-xs text-muted-foreground">{t("sidebar.noProjects")}</div>
                </div>
            );
        }

        // Show recent strategies
        return (
            <div className="space-y-0.5">
                <button className="w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                    <Clock size={16} />
                    <span>{t("sidebar.recent")}</span>
                </button>
                {recentStrategies.map((strategy) => (
                    <button
                        key={strategy.id}
                        onClick={() => onStrategySelect(strategy)}
                        className="w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    >
                        <div className="w-4" />
                        <span className="truncate">{strategy.name}</span>
                    </button>
                ))}
            </div>
        );
    }
};

export default AppSidebar;
