import { Home, Compass, Layout, BookOpen, Bell, Clock, LogOut, TrendingUp, Library, Tag } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import type { Strategy } from "@/lib/types";
import { authApi } from "@/lib/api";
import { useState } from "react";
import { Logo } from "@/components/Logo";
import { TRENDING_ENABLED } from "@/lib/featureFlags";

interface DashboardSidebarProps {
    strategies: Strategy[];
    onSelectStrategy: (strategy: Strategy) => void;
    activeItem?: "Home";
}

/**
 * @deprecated Use AppSidebar from components/layout/AppSidebar instead.
 * This component is kept for backward compatibility and will be removed in a future version.
 */
export const DashboardSidebar = ({
    strategies,
    onSelectStrategy,
    activeItem = "Home",
}: DashboardSidebarProps) => {
    const navigate = useNavigate();
    const [isLoggingOut, setIsLoggingOut] = useState(false);
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
    const recentStrategies = strategies.slice(0, 5);

    const handleLogout = async () => {
        try {
            setIsLoggingOut(true);
            await authApi.logout();
            // Reload the page to clear all state and trigger auth required
            window.location.href = "/";
        } catch (error) {
            console.error("Logout failed:", error);
            setIsLoggingOut(false);
        }
    };

    const sidebarItems = [
        { icon: Home, label: "Home", path: "/" },
        ...(TRENDING_ENABLED ? [{ icon: TrendingUp, label: "Trending", path: "/trending" }] : []),
    ];

    const projectItems = [
        { icon: Clock, label: "Recent" },
        ...recentStrategies.map(s => ({ label: s.name, strategy: s })),
    ];

    const resourceItems = [
        ...(TRENDING_ENABLED ? [{ icon: Compass, label: "Discover", path: "/trending" }] : []),
        { icon: Layout, label: "Templates", path: "/templates" },
        { icon: Tag, label: "My Subscriptions", path: "/subscriptions" },
    ];

    return (
        <aside className="w-56 bg-card/80 backdrop-blur-sm border-r border-border flex flex-col">
            {/* Logo */}
            <div className="h-14 px-4 flex items-center justify-between border-b border-border">
                <Logo size="sm" />
                <button className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground">
                    <Bell size={16} />
                </button>
            </div>

            {/* Main Navigation */}
            <div className="p-3 space-y-1">
                {sidebarItems.map((item, i) => (
                    <button
                        key={i}
                        onClick={() => navigate(item.path)}
                        className={cn(
                            "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                            activeItem === item.label
                                ? "bg-primary/10 text-primary"
                                : "text-muted-foreground hover:text-foreground hover:bg-muted"
                        )}
                    >
                        <item.icon size={18} />
                        <span>{item.label}</span>
                    </button>
                ))}
            </div>

            {/* Projects Section */}
            <div className="px-3 mt-2">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-3 py-2">
                    Projects
                </div>
                <div className="space-y-0.5">
                    {projectItems.map((item, i) => (
                        <button
                            key={i}
                            onClick={() => 'strategy' in item && item.strategy && onSelectStrategy(item.strategy)}
                            className="w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        >
                            {'icon' in item && item.icon ? <item.icon size={16} /> : <div className="w-4" />}
                            <span className="truncate">{item.label}</span>
                        </button>
                    ))}
                </div>
            </div>

            {/* Resources Section */}
            <div className="px-3 mt-4 flex-1">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-3 py-2">
                    Resources
                </div>
                <div className="space-y-0.5">
                    {resourceItems.map((item, i) => {
                        const isActive = 'path' in item && window.location.pathname === item.path;
                        return (
                        <button
                            key={i}
                            onClick={() => 'path' in item && item.path && navigate(item.path)}
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

            {user && (
                <div className="p-3 border-t border-border">
                    <div className="flex items-center gap-2 px-2 py-2">
                        <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
                            <span className="text-sm font-medium text-primary">
                                {(user.name || user.email || "U").slice(0, 1).toUpperCase()}
                            </span>
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-foreground truncate">{user.name || "User"}</div>
                            <div className="text-xs text-muted-foreground truncate">{user.email || "-"}</div>
                        </div>
                        <button
                            onClick={handleLogout}
                            disabled={isLoggingOut}
                            className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                            title="Logout"
                        >
                            <LogOut size={16} />
                        </button>
                    </div>
                </div>
            )}
        </aside>
    );
};

export default DashboardSidebar;
