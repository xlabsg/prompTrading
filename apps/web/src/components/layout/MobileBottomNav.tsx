import { Home, Layout, Tag, TrendingUp } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { TRENDING_ENABLED } from "@/lib/featureFlags";

type NavItem = {
    label: string;
    path: string;
    icon: typeof Home;
    isActive: (pathname: string) => boolean;
};

export const MobileBottomNav = () => {
    const { t } = useTranslation();
    const location = useLocation();
    const navigate = useNavigate();
    const pathname = location.pathname;

    const items: NavItem[] = [
        {
            label: t("nav.home"),
            path: "/",
            icon: Home,
            isActive: (path) => path === "/",
        },
        ...(TRENDING_ENABLED
            ? [{
                label: t("nav.trending"),
                path: "/trending",
                icon: TrendingUp,
                isActive: (path: string) => path.startsWith("/trending"),
            }]
            : []),
        {
            label: t("nav.templates"),
            path: "/templates",
            icon: Layout,
            isActive: (path) => path.startsWith("/templates"),
        },
        {
            label: t("nav.subscriptions"),
            path: "/subscriptions",
            icon: Tag,
            isActive: (path) => path.startsWith("/subscriptions"),
        },
    ];

    return (
        <nav className="ink-panel fixed inset-x-0 bottom-0 z-40 border-t border-ink-line md:hidden">
            <div className="flex items-stretch pb-[env(safe-area-inset-bottom)]">
                {items.map((item) => {
                    const active = item.isActive(pathname);
                    const Icon = item.icon;
                    return (
                        <button
                            key={item.path}
                            onClick={() => navigate(item.path)}
                            className={cn(
                                "relative flex flex-1 flex-col items-center gap-1 py-2.5 text-xs transition-colors",
                                active ? "text-ink-foreground" : "text-ink-muted"
                            )}
                        >
                            {/* Same active marker as the desktop rail, rotated to the top edge. */}
                            {active && (
                                <span className="absolute inset-x-4 top-0 h-0.5 rounded-full bg-primary" aria-hidden />
                            )}
                            <Icon size={18} strokeWidth={1.75} />
                            <span className="leading-none">{item.label}</span>
                        </button>
                    );
                })}
            </div>
        </nav>
    );
};

export default MobileBottomNav;
