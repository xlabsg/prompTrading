import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
    Home,
    Compass,
    Layout,
    Tag,
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

const navItemClass = (isActive: boolean) =>
    cn(
        "relative flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
        isActive
            ? "bg-ink-raised text-ink-foreground"
            : "text-ink-muted hover:bg-ink-raised/60 hover:text-ink-foreground",
    );

// The active marker is a rule against the rail edge, not a filled pill: it reads
// as position within the app rather than as another button.
const ActiveMark = () => (
    <span className="absolute -left-2.5 top-1.5 h-[calc(100%-0.75rem)] w-0.5 rounded-full bg-primary" aria-hidden />
);

const SectionLabel = ({ children }: { children: React.ReactNode }) => (
    <div className="px-2.5 pb-1.5 pt-5 text-xs text-ink-muted">{children}</div>
);

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
        { icon: Tag, label: t("nav.subscriptions"), path: "/subscriptions", page: "subscriptions" as PageType },
    ];
    const adminNavItems = isAdmin
        ? [{ icon: Shield, label: t("nav.admin"), path: "/admin/trending" }]
        : [];
    const resourceItems = TRENDING_ENABLED
        ? [{ icon: Compass, label: t("sidebar.discover"), path: "/trending" }]
        : [];

    const recentStrategies = strategies.slice(0, 5);

    return (
        <aside className="ink-panel flex w-60 flex-col border-r border-ink-line">
            <div className="flex h-14 items-center border-b border-ink-line px-4">
                <Logo size="sm" onInk />
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3">
                <nav className="space-y-0.5">
                    {mainNavItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = currentPage === item.page;
                        return (
                            <button key={item.path} onClick={() => navigate(item.path)} className={navItemClass(isActive)}>
                                {isActive && <ActiveMark />}
                                <Icon size={16} strokeWidth={1.75} />
                                <span>{item.label}</span>
                            </button>
                        );
                    })}
                </nav>

                <SectionLabel>{t("sidebar.projects")}</SectionLabel>
                {renderProjects()}

                {(adminNavItems.length > 0 || resourceItems.length > 0) && (
                    <>
                        <SectionLabel>{t("sidebar.resources")}</SectionLabel>
                        <nav className="space-y-0.5">
                            {[...adminNavItems, ...resourceItems].map((item) => {
                                const Icon = item.icon;
                                const isActive = window.location.pathname === item.path;
                                return (
                                    <button key={item.label} onClick={() => navigate(item.path)} className={navItemClass(isActive)}>
                                        {isActive && <ActiveMark />}
                                        <Icon size={16} strokeWidth={1.75} />
                                        <span>{item.label}</span>
                                    </button>
                                );
                            })}
                        </nav>
                    </>
                )}
            </div>

            {user && (
                <div className="border-t border-ink-line p-3">
                    <div className="flex items-center gap-2.5 px-1.5 py-1">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-ink-raised text-xs font-medium text-ink-foreground">
                            {(user.name || user.email || "U").slice(0, 1).toUpperCase()}
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="truncate text-sm text-ink-foreground">
                                {user.name || t("console.defaultUser")}
                            </div>
                            <div className="truncate text-xs text-ink-muted">{user.email || "-"}</div>
                        </div>
                        <button
                            onClick={handleLogout}
                            disabled={isLoggingOut}
                            className="shrink-0 rounded-md p-1.5 text-ink-muted transition-colors hover:bg-ink-raised hover:text-ink-foreground disabled:opacity-50"
                            title={t("common.signOut")}
                        >
                            <LogOut size={15} strokeWidth={1.75} />
                        </button>
                    </div>
                </div>
            )}
        </aside>
    );

    function renderProjects() {
        if (error) {
            return (
                <div className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-ink-muted">
                    <AlertCircle size={13} className="text-short" />
                    <span>{t("sidebar.loadProjectsFailed")}</span>
                </div>
            );
        }

        if (!isAuthed) {
            return <div className="px-2.5 py-1.5 text-xs text-ink-muted">{t("sidebar.signInToSeeProjects")}</div>;
        }

        if (recentStrategies.length === 0) {
            return <div className="px-2.5 py-1.5 text-xs text-ink-muted">{t("sidebar.noProjects")}</div>;
        }

        return (
            <div className="space-y-0.5">
                <div className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm text-ink-muted">
                    <Clock size={15} strokeWidth={1.75} />
                    <span>{t("sidebar.recent")}</span>
                </div>
                {recentStrategies.map((strategy) => (
                    <button
                        key={strategy.id}
                        onClick={() => onStrategySelect(strategy)}
                        className="w-full truncate rounded-md py-1.5 pl-[2.1rem] pr-2.5 text-left text-sm text-ink-muted transition-colors hover:bg-ink-raised/60 hover:text-ink-foreground"
                    >
                        {strategy.name}
                    </button>
                ))}
            </div>
        );
    }
};

export default AppSidebar;
