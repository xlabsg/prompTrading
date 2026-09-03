import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
    Code,
    LineChart,
    FileText,
    Plus,
    Radio,
    Users,
    LogOut,
    TrendingUp,
    MessageSquare,
    ArrowLeft,
    Network,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { ViewType, Strategy } from "@/pages/Console";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useNavigate } from "react-router-dom";
import { authApi, strategyMembersApi, subscriptionsApi } from "@/lib/api";
import type { StrategyMember, StrategyRole } from "@/lib/types";
import { AuthDialog } from "@/components/auth/AuthDialog";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/common/LanguageSwitcher";

interface ConsoleHeaderProps {
    currentView: ViewType;
    onViewChange: (view: ViewType) => void;
    strategy: Strategy | null;
    onOpenSidebar?: () => void;
}

const ConsoleHeader = ({ currentView, onViewChange, strategy, onOpenSidebar }: ConsoleHeaderProps) => {
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [isAuthOpen, setIsAuthOpen] = useState(false);
    const [isShareOpen, setIsShareOpen] = useState(false);
    const [memberEmail, setMemberEmail] = useState("");
    const [memberRole, setMemberRole] = useState<StrategyRole>("viewer");
    const views = useMemo(
        () => [
            { id: "overview" as ViewType, label: t("console.views.overview", { defaultValue: "Overview" }), icon: Network },
            { id: "code" as ViewType, label: t("console.views.code"), icon: Code },
            { id: "backtest" as ViewType, label: t("console.views.backtest"), icon: LineChart },
            { id: "live" as ViewType, label: t("console.views.live"), icon: Radio, badge: "Pro" },
            { id: "portfolio" as ViewType, label: t("console.views.portfolio"), icon: LineChart },
        ],
        [t],
    );

    const additionalViews = useMemo(
        () => [{ id: "logs", label: t("console.views.logs"), icon: FileText }],
        [t],
    );

    useEffect(() => {
        if (typeof window === "undefined") return;
        const handler = () => setIsAuthOpen(true);
        window.addEventListener("auth-required", handler);
        return () => window.removeEventListener("auth-required", handler);
    }, []);

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

    const membersQuery = useQuery({
        queryKey: ["strategy-members", strategy?.id],
        queryFn: () => (strategy ? strategyMembersApi.list(strategy.id) : Promise.resolve([])),
        enabled: Boolean(strategy) && Boolean(user),
    });

    const subscriptionsQuery = useQuery({
        queryKey: ["subscriptions"],
        queryFn: () => subscriptionsApi.list(),
        enabled: Boolean(strategy) && Boolean(user),
        retry: false,
        refetchOnWindowFocus: false,
    });

    const originTemplate = useMemo(() => {
        if (!strategy) return null;
        const subs = subscriptionsQuery.data?.subscriptions ?? [];
        const match = subs.find((s) => s.strategy_id === strategy.id);
        if (!match) return null;
        return { templateId: match.template_id, templateName: match.template_name };
    }, [strategy, subscriptionsQuery.data]);

    const addMemberMutation = useMutation({
        mutationFn: (payload: { email?: string; role?: StrategyRole }) => {
            if (!strategy) throw new Error("missing_strategy");
            return strategyMembersApi.add(strategy.id, payload);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["strategy-members", strategy?.id] });
            setMemberEmail("");
        },
    });

    const removeMemberMutation = useMutation({
        mutationFn: (memberId: string) => {
            if (!strategy) throw new Error("missing_strategy");
            return strategyMembersApi.remove(strategy.id, memberId);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["strategy-members", strategy?.id] });
        },
    });

    const logoutMutation = useMutation({
        mutationFn: authApi.logout,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["auth-me"] });
            setIsShareOpen(false);
        },
    });

    const currentMember = useMemo(() => {
        if (!membersQuery.data || !user) return null;
        return membersQuery.data.find((member) => member.user.id === user.id) || null;
    }, [membersQuery.data, user]);


    const handleAddMember = () => {
        if (!memberEmail.trim()) return;
        addMemberMutation.mutate({ email: memberEmail.trim(), role: memberRole });
    };

    const renderMemberRow = (member: StrategyMember) => {
        const isSelf = user?.id === member.user.id;
        return (
            <div
                key={member.id}
                className="flex items-center justify-between rounded-xl border border-orange-100 bg-white px-4 py-3"
            >
                <div className="flex items-center gap-3">
                    <div className="h-9 w-9 rounded-full bg-orange-100 flex items-center justify-center text-orange-700 text-sm font-semibold">
                        {(member.user.name || member.user.email || "U").slice(0, 1).toUpperCase()}
                    </div>
                    <div>
                        <div className="text-sm font-semibold text-foreground">
                            {member.user.name || member.user.email || member.user.id}
                            {isSelf && <span className="ml-2 text-xs text-muted-foreground">{t("console.you")}</span>}
                        </div>
                        <div className="text-xs text-muted-foreground">{member.user.email || "-"}</div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <Badge variant="secondary" className="capitalize">
                        {member.role === "admin"
                            ? t("console.roleAdmin")
                            : member.role === "editor"
                                ? t("console.roleEditor")
                                : t("console.roleViewer")}
                    </Badge>
                    {currentMember?.role === "admin" && !isSelf && (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => removeMemberMutation.mutate(member.id)}
                        >
                            {t("common.remove")}
                        </Button>
                    )}
                </div>
            </div>
        );
    };

    return (
        <header className="border-b border-border bg-card/50 backdrop-blur-sm px-4 py-3 sm:py-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-4 md:min-w-0 md:flex-1 md:overflow-hidden">
                    <div className="flex items-center gap-3 min-w-0 mt-1 md:mt-0 md:h-9 shrink-0">
                        {strategy && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => navigate("/")}
                                className="md:hidden h-8 w-8 p-0"
                            >
                                <ArrowLeft size={16} />
                            </Button>
                        )}
                        {strategy && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => navigate("/")}
                                className="hidden md:inline-flex h-9 gap-2"
                            >
                                <ArrowLeft size={16} />
                                <span>{t("console.sidebar.backToDashboard")}</span>
                            </Button>
                        )}
                        {strategy && (
                            <div className="flex items-center gap-2 text-sm min-w-0 md:h-9">
                                <span className="text-muted-foreground whitespace-nowrap">{t("console.strategyLabel", { defaultValue: "Strategy:" })}</span>
                                <span className="font-medium text-foreground truncate max-w-[220px]">
                                    {strategy.name}
                                </span>
                                {originTemplate && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                                        onClick={() => navigate(`/template/${originTemplate.templateId}/backtest`)}
                                        title={t("console.fromTemplateTitle", { name: originTemplate.templateName })}
                                    >
                                        {t("console.fromTemplateLabel", { name: originTemplate.templateName })}
                                    </Button>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="flex items-center gap-2 md:flex-1 min-w-0 overflow-hidden">
                        <div className="flex items-center gap-1 bg-muted/50 rounded-lg p-1 overflow-hidden w-full md:h-9">
                            {onOpenSidebar && (
                                <button
                                    onClick={onOpenSidebar}
                                    className="md:hidden relative flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground whitespace-nowrap"
                                >
                                    <MessageSquare size={16} className="relative z-10" />
                                    <span className="relative z-10">{t("console.sidebar.chat", { defaultValue: "Chat" })}</span>
                                </button>
                            )}
                            {views.map((view) => (
                                <button
                                    key={view.id}
                                    onClick={() => onViewChange(view.id)}
                                    className={cn(
                                        "relative flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap",
                                        currentView === view.id
                                            ? "text-primary"
                                            : "text-muted-foreground hover:text-foreground"
                                    )}
                                >
                                    {currentView === view.id && (
                                        <motion.div
                                            layoutId="activeTab"
                                            className="absolute inset-0 bg-primary/10 border border-primary/20 rounded-md shadow-sm"
                                            transition={{ duration: 0.2 }}
                                        />
                                    )}
                                    <view.icon size={16} className="relative z-10" />
                                    <span className="relative z-10 hidden sm:inline">{view.label}</span>
                                    {"badge" in view && (
                                        <span className="relative z-10 text-[10px] px-1 py-0.2 leading-tight rounded font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                                            {(view as { badge?: string }).badge}
                                        </span>
                                    )}
                                </button>
                            ))}

                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <button className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                                        <Plus size={16} />
                                    </button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="start" className="w-48">
                                    {additionalViews.map((view) => (
                                        <DropdownMenuItem
                                            key={view.id}
                                            disabled={view.coming}
                                            className="flex items-center justify-between"
                                            onClick={() => !view.coming && onViewChange(view.id as ViewType)}
                                        >
                                            <div className="flex items-center gap-2">
                                                <view.icon size={14} />
                                                <span>{view.label}</span>
                                            </div>
                                            {view.coming && (
                                                <span className="text-xs text-muted-foreground">{t("common.comingSoon")}</span>
                                            )}
                                        </DropdownMenuItem>
                                    ))}
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </div>
                    </div>
                </div>

                <div className="hidden items-center justify-between gap-2 sm:flex sm:justify-end sm:gap-3">
                    <div className="hidden lg:flex">
                        <LanguageSwitcher />
                    </div>
                    {user ? (
                        <>
                            {false && strategy && (
                                <Button variant="outline" size="sm" className="gap-2" onClick={() => setIsShareOpen(true)}>
                                    <Users size={14} />
                                    <span className="hidden sm:inline">{t("console.share")}</span>
                                </Button>
                            )}
                            <div className="flex items-center gap-2 rounded-full border border-orange-200 bg-white px-2 py-1">
                                <div className="h-6 w-6 rounded-full bg-orange-100 flex items-center justify-center text-xs font-semibold text-orange-700">
                                    {(user.name || user.email || "U").slice(0, 1).toUpperCase()}
                                </div>
                                <span className="hidden sm:inline text-sm font-medium text-foreground">
                                    {user.name || user.email || t("console.defaultUser")}
                                </span>
                                <button
                                    type="button"
                                    onClick={() => logoutMutation.mutate()}
                                    className="rounded-full p-1 text-muted-foreground hover:text-foreground"
                                >
                                    <LogOut size={14} />
                                </button>
                            </div>
                        </>
                    ) : null}
                </div>
            </div>


            <AuthDialog open={isAuthOpen} onOpenChange={setIsAuthOpen} />

            <Dialog open={isShareOpen} onOpenChange={setIsShareOpen}>
                <DialogContent className="max-w-2xl border-orange-100 bg-white/95 p-0">
                    <div className="px-8 py-6 border-b border-orange-100">
                        <div className="flex items-center gap-3">
                            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-orange-50 text-orange-600">
                                <Users className="h-6 w-6" />
                            </div>
                            <div>
                                <h2 className="text-xl font-semibold text-foreground">{t("console.membersTitle")}</h2>
                                <p className="text-sm text-muted-foreground">{t("console.membersSubtitle")}</p>
                            </div>
                        </div>
                    </div>
                    <div className="px-8 py-6 space-y-5">
                        {!user && (
                            <div className="rounded-xl border border-orange-100 bg-orange-50 px-4 py-3 text-sm text-orange-700">
                                {t("console.loginRequired")}
                            </div>
                        )}
                        {user && (
                            <div className="grid gap-3">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                                    <div className="flex-1">
                                        <label className="text-sm font-medium text-foreground">{t("console.addMember")}</label>
                                        <Input
                                            value={memberEmail}
                                            onChange={(e) => setMemberEmail(e.target.value)}
                                            placeholder={t("console.memberEmail")}
                                            className="mt-2"
                                        />
                                    </div>
                                    <div className="sm:w-40">
                                        <label className="text-sm font-medium text-foreground">{t("console.roleLabel")}</label>
                                        <select
                                            value={memberRole}
                                            onChange={(e) => setMemberRole(e.target.value as StrategyRole)}
                                            className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        >
                                            <option value="admin">{t("console.roleAdmin")}</option>
                                            <option value="editor">{t("console.roleEditor")}</option>
                                            <option value="viewer">{t("console.roleViewer")}</option>
                                        </select>
                                    </div>
                                    <Button
                                        onClick={handleAddMember}
                                        disabled={!memberEmail.trim() || addMemberMutation.isPending || currentMember?.role !== "admin"}
                                        className="sm:self-end"
                                    >
                                        {t("console.addMember")}
                                    </Button>
                                </div>
                                {currentMember?.role !== "admin" && (
                                    <p className="text-xs text-muted-foreground">
                                        {t("console.onlyAdmins")}
                                    </p>
                                )}
                            </div>
                        )}
                        <div className="grid gap-3">
                            {membersQuery.data?.length ? (
                                membersQuery.data.map(renderMemberRow)
                            ) : (
                                <div className="rounded-xl border border-dashed border-orange-200 bg-orange-50/40 px-4 py-6 text-center text-sm text-muted-foreground">
                                    {t("console.noMembers")}
                                </div>
                            )}
                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </header>
    );
};

export default ConsoleHeader;
