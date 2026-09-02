import { useEffect, useMemo, useState } from "react";
import {
    Code,
    LineChart,
    FileText,
    Plus,
    Radio,
    Users,
    LogOut,
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
            { id: "live" as ViewType, label: t("console.views.live"), icon: Radio },
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
                className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-3"
            >
                <div className="flex items-center gap-3">
                    <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold">
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
        <header className="bg-card">
            {/* Identity rail: what you are working on, and who you are. */}
            <div className="flex h-14 items-center gap-3 border-b border-border px-3 sm:px-4">
                {strategy && (
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => navigate("/")}
                        className="h-8 w-8 shrink-0"
                        title={t("console.sidebar.backToDashboard")}
                    >
                        <ArrowLeft size={16} />
                    </Button>
                )}

                {strategy && (
                    <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm font-medium text-foreground">{strategy.name}</span>
                        {originTemplate && (
                            <button
                                onClick={() => navigate(`/template/${originTemplate.templateId}/backtest`)}
                                className="hidden shrink-0 truncate text-xs text-muted-foreground transition-colors hover:text-foreground sm:block"
                                title={t("console.fromTemplateTitle", { name: originTemplate.templateName })}
                            >
                                {t("console.fromTemplateLabel", { name: originTemplate.templateName })}
                            </button>
                        )}
                    </div>
                )}

                <div className="ml-auto flex shrink-0 items-center gap-1">
                    <div className="hidden lg:flex">
                        <LanguageSwitcher />
                    </div>
                    {false && strategy && (
                        <Button variant="ghost" size="sm" className="gap-2" onClick={() => setIsShareOpen(true)}>
                            <Users size={14} />
                            <span className="hidden sm:inline">{t("console.share")}</span>
                        </Button>
                    )}
                    {user && (
                        <div className="flex items-center gap-2 pl-1">
                            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-muted text-xs font-medium text-foreground">
                                {(user.name || user.email || "U").slice(0, 1).toUpperCase()}
                            </div>
                            <span className="hidden text-sm text-foreground sm:inline">
                                {user.name || user.email || t("console.defaultUser")}
                            </span>
                            <button
                                type="button"
                                onClick={() => logoutMutation.mutate()}
                                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                                title={t("common.signOut")}
                            >
                                <LogOut size={14} />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* View rail: underlined tabs on a hairline, matching the Tabs primitive. */}
            <div className="flex items-stretch gap-5 overflow-x-auto border-b border-border px-3 sm:px-4">
                {onOpenSidebar && (
                    <button
                        onClick={onOpenSidebar}
                        className="-mb-px flex shrink-0 items-center gap-2 whitespace-nowrap border-b-2 border-transparent py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground md:hidden"
                    >
                        <MessageSquare size={15} strokeWidth={1.75} />
                        <span>{t("console.sidebar.chat", { defaultValue: "Chat" })}</span>
                    </button>
                )}

                {views.map((view) => {
                    const isActive = currentView === view.id;
                    return (
                        <button
                            key={view.id}
                            onClick={() => onViewChange(view.id)}
                            className={cn(
                                "-mb-px flex shrink-0 items-center gap-2 whitespace-nowrap border-b-2 py-2.5 text-sm font-medium transition-colors",
                                isActive
                                    ? "border-primary text-foreground"
                                    : "border-transparent text-muted-foreground hover:text-foreground",
                            )}
                        >
                            <view.icon size={15} strokeWidth={1.75} />
                            <span>{view.label}</span>
                        </button>
                    );
                })}

                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <button
                            className="-mb-px flex shrink-0 items-center border-b-2 border-transparent px-0.5 py-2.5 text-muted-foreground transition-colors hover:text-foreground"
                            title={t("console.views.logs")}
                        >
                            <Plus size={15} strokeWidth={1.75} />
                        </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="w-44">
                        {additionalViews.map((view) => (
                            <DropdownMenuItem
                                key={view.id}
                                className="flex items-center gap-2"
                                onClick={() => onViewChange(view.id as ViewType)}
                            >
                                <view.icon size={14} />
                                <span>{view.label}</span>
                            </DropdownMenuItem>
                        ))}
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>

            <AuthDialog open={isAuthOpen} onOpenChange={setIsAuthOpen} />

            <Dialog open={isShareOpen} onOpenChange={setIsShareOpen}>
                <DialogContent className="max-w-2xl border-border bg-popover p-0">
                    <div className="px-8 py-6 border-b border-border">
                        <div className="flex items-center gap-3">
                            <div className="flex h-12 w-12 items-center justify-center rounded-md bg-primary/5 text-primary">
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
                            <div className="rounded-md border border-border bg-primary/5 px-4 py-3 text-sm text-primary">
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
                                <div className="rounded-md border border-dashed border-border bg-primary/5 px-4 py-6 text-center text-sm text-muted-foreground">
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
