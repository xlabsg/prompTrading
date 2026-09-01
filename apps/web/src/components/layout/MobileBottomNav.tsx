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
        <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background/95 backdrop-blur md:hidden">
            <div className="flex items-center justify-between px-2 pb-[env(safe-area-inset-bottom)]">
                {items.map((item) => {
                    const active = item.isActive(pathname);
                    const Icon = item.icon;
                    return (
                        <button
                            key={item.path}
                            onClick={() => navigate(item.path)}
                            className={cn(
                                "flex flex-1 flex-col items-center gap-1 px-2 py-2 text-xs font-medium transition-colors",
                                active ? "text-primary" : "text-muted-foreground"
                            )}
                        >
                            <span className={cn(
                                "flex h-8 w-8 items-center justify-center rounded-xl",
                                active ? "bg-primary/10" : "bg-transparent"
                            )}>
                                <Icon size={18} />
                            </span>
                            <span className="leading-none">{item.label}</span>
                        </button>
                    );
                })}
            </div>
        </nav>
    );
};

export default MobileBottomNav;
