import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { RefreshCw, Pause, Play, AlertCircle, CheckCircle2, MessageCircle, Settings, Star, Library } from "lucide-react";
import { subscriptionsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SubscriptionResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { MainLayout } from "@/components/layout/MainLayout";
import { TelegramConfigDialog, TelegramStatusBadge } from "@/components/template/TelegramConfigDialog";
import { useTranslation } from "react-i18next";

export function SubscriptionsPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [telegramDialogOpen, setTelegramDialogOpen] = useState(false);
    const [selectedSubscriptionId, setSelectedSubscriptionId] = useState<string | null>(null);
    const { t, i18n } = useTranslation();

    const { data, isLoading, error } = useQuery({
        queryKey: ["subscriptions"],
        queryFn: subscriptionsApi.list,
    });

    const syncMutation = useMutation({
        mutationFn: subscriptionsApi.sync,
        onSuccess: (result) => {
            toast.success(result.message);
            queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
        },
        onError: (err) => {
            toast.error(err instanceof Error ? err.message : t("subscriptions.syncFailed"));
        },
    });

    const pauseMutation = useMutation({
        mutationFn: subscriptionsApi.pause,
        onSuccess: () => {
            toast.success(t("subscriptions.paused"));
            queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
        },
        onError: (err) => {
            toast.error(err instanceof Error ? err.message : t("subscriptions.pauseFailed"));
        },
    });

    const resumeMutation = useMutation({
        mutationFn: subscriptionsApi.resume,
        onSuccess: () => {
            toast.success(t("subscriptions.resumed"));
            queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
        },
        onError: (err) => {
            toast.error(err instanceof Error ? err.message : t("subscriptions.resumeFailed"));
        },
    });

    const openTelegramConfig = (subscriptionId: string) => {
        setSelectedSubscriptionId(subscriptionId);
        setTelegramDialogOpen(true);
    };

    const subscriptions = data?.subscriptions || [];

    const getStatusBadge = (status: string, isOutdated: boolean) => {
        if (status === "sync_error") {
            return (
                <span className="flex items-center gap-1 text-xs text-red-500 bg-red-500/10 px-2 py-0.5 rounded-full">
                    <AlertCircle size={12} />
                    {t("subscriptions.status.syncError")}
                </span>
            );
        }
        if (isOutdated) {
            return (
                <span className="flex items-center gap-1 text-xs text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded-full">
                    <RefreshCw size={12} />
                    {t("subscriptions.status.updateAvailable")}
                </span>
            );
        }
        return (
            <span className="flex items-center gap-1 text-xs text-green-500 bg-green-500/10 px-2 py-0.5 rounded-full">
                <CheckCircle2 size={12} />
                {status === "paused" ? t("subscriptions.status.paused") : t("subscriptions.status.active")}
            </span>
        );
    };

    const headerActions = (
        <Button onClick={() => navigate("/templates")}>
            <Library className="mr-2 h-4 w-4" />
            {t("templates.browse")}
        </Button>
    );

    return (
        <>
            <MainLayout currentPage="subscriptions" headerActions={headerActions}>
                {/* Subscription List */}
                <div className="flex-1 overflow-auto p-4 sm:p-6">
                    {isLoading ? (
                        <div className="space-y-4">
                            {Array.from({ length: 3 }).map((_, i) => (
                                <div key={i} className="bg-card border border-border rounded-xl p-5">
                                    <div className="flex items-center justify-between">
                                        <div className="space-y-2">
                                            <Skeleton className="h-6 w-48" />
                                            <Skeleton className="h-4 w-32" />
                                        </div>
                                        <Skeleton className="h-8 w-24" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center h-64 text-center">
                            <AlertCircle size={48} className="text-red-500 mb-4" />
                            <h3 className="text-lg font-medium mb-2">{t("subscriptions.loadFailed")}</h3>
                            <p className="text-muted-foreground">
                                {error instanceof Error ? error.message : t("subscriptions.tryAgain")}
                            </p>
                        </div>
                    ) : subscriptions.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-64 text-center">
                            <Star size={48} className="text-muted-foreground mb-4" />
                            <h3 className="text-lg font-medium mb-2">{t("subscriptions.emptyTitle")}</h3>
                            <p className="text-muted-foreground mb-4">
                                {t("subscriptions.emptySubtitle")}
                            </p>
                            <Button onClick={() => navigate("/templates")}>
                                <Library className="mr-2 h-4 w-4" />
                                {t("templates.browse")}
                            </Button>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {subscriptions.map((sub) => (
                                <div
                                    key={sub.id}
                                    className="bg-card border border-border rounded-xl p-4 hover:border-primary/50 transition-colors sm:p-5"
                                >
                                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-2 flex-wrap">
                                                <h3 className="font-semibold text-lg truncate">
                                                    {sub.strategy_name}
                                                </h3>
                                                {getStatusBadge(sub.status, sub.is_outdated)}
                                            </div>

                                            <p className="text-sm text-muted-foreground mb-3">
                                                {t("subscriptions.fromTemplate", { name: sub.template_name })}
                                            </p>

                                            <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-3">
                                                {sub.user_config && (
                                                    <>
                                                        <span>
                                                            {(sub.user_config as Record<string, unknown>).exchange as string}
                                                        </span>
                                                        <span>
                                                            {(sub.user_config as Record<string, unknown>).symbol as string}
                                                        </span>
                                                    </>
                                                )}
                                                <span>
                                                    {t("subscriptions.version", { current: sub.subscribed_version, latest: sub.template_version })}
                                                </span>
                                                {sub.last_synced_at && (
                                                    <span>
                                                        {t("subscriptions.lastSynced", {
                                                            date: new Date(sub.last_synced_at).toLocaleDateString(
                                                                i18n.language.startsWith("zh") ? "zh-CN" : "en-US",
                                                            ),
                                                        })}
                                                    </span>
                                                )}
                                            </div>

                                            {/* Telegram Status */}
                                            {sub.telegram_status && (
                                                <div className="flex items-center gap-2 pt-2 border-t">
                                                    <MessageCircle size={14} className="text-muted-foreground" />
                                                    <TelegramStatusBadge status={sub.telegram_status} />
                                                    {sub.telegram_status.is_configured && (
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="h-6 px-2 text-xs"
                                                            onClick={() => openTelegramConfig(sub.id)}
                                                        >
                                                            <Settings size={12} className="mr-1" />
                                                            {t("subscriptions.configure")}
                                                        </Button>
                                                    )}
                                                </div>
                                            )}
                                        </div>

                                        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
                                            {sub.is_outdated && sub.status === "active" && (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => syncMutation.mutate(sub.id)}
                                                    disabled={syncMutation.isPending()}
                                                >
                                                    <RefreshCw
                                                        className={cn(
                                                            "mr-2 h-4 w-4",
                                                            syncMutation.isPending() && "animate-spin"
                                                        )}
                                                    />
                                                    {t("subscriptions.update")}
                                                </Button>
                                            )}

                                            {sub.status === "active" ? (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => pauseMutation.mutate(sub.id)}
                                                    disabled={pauseMutation.isPending()}
                                                >
                                                    <Pause className="mr-2 h-4 w-4" />
                                                    {t("subscriptions.pause")}
                                                </Button>
                                            ) : sub.status === "paused" ? (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => resumeMutation.mutate(sub.id)}
                                                    disabled={resumeMutation.isPending()}
                                                >
                                                    <Play className="mr-2 h-4 w-4" />
                                                    {t("subscriptions.resume")}
                                                </Button>
                                            ) : null}

                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => navigate(`/strategy/${sub.strategy_id}`)}
                                            >
                                                {t("common.open")}
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </MainLayout>

            {/* Telegram Configuration Dialog */}
            <TelegramConfigDialog
                subscriptionId={selectedSubscriptionId || ""}
                open={telegramDialogOpen}
                onOpenChange={setTelegramDialogOpen}
                onSuccess={() => queryClient.invalidateQueries({ queryKey: ["subscriptions"] })}
            />
        </>
    );
}

export default SubscriptionsPage;
