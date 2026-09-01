import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw, XCircle } from "lucide-react";
import MainLayout from "@/components/layout/MainLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { adminOpsApi, authApi, templatesApi } from "@/lib/api";
import type { JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

const msSince = (iso?: string) => {
    if (!iso) return null;
    const t = new Date(iso).getTime();
    if (!Number.isFinite(t)) return null;
    return Date.now() - t;
};

const statusVariant = (s: JobStatus): "default" | "secondary" | "destructive" => {
    if (s === "succeeded") return "default";
    if (s === "failed") return "destructive";
    if (s === "cancelled") return "secondary";
    return "secondary";
};

const AdminTrending = () => {
    const { t, i18n } = useTranslation();
    const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";
    const formatShort = (iso: string) =>
        new Date(iso).toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    const formatDuration = (ms?: number | null) => {
        if (!ms || ms < 0) return t("adminTrending.duration.na");
        const s = Math.floor(ms / 1000);
        if (s < 60) return t("adminTrending.duration.seconds", { count: s });
        const m = Math.floor(s / 60);
        if (m < 60) return t("adminTrending.duration.minutes", { count: m });
        const h = Math.floor(m / 60);
        return t("adminTrending.duration.hoursMinutes", { hours: h, minutes: m % 60 });
    };
    const qc = useQueryClient();
    const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

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

    const isAdmin = Boolean(authQuery.data?.is_admin);

    const queueQuery = useQuery({
        queryKey: ["admin-queue"],
        queryFn: () => adminOpsApi.getQueue({ head_n: 10 }),
        enabled: isAdmin,
        refetchInterval: 2000,
        retry: false,
    });

    const jobsQuery = useQuery({
        queryKey: ["admin-jobs"],
        queryFn: () =>
            adminOpsApi.listJobs({
                limit: 80,
                types: [
                    "trending_scrape",
                    "trending_backtest",
                    "generate_strategy",
                    "generate_and_backtest",
                    "backtest",
                    "template_stable5_screening",
                ].join(","),
            }),
        enabled: isAdmin,
        refetchInterval: 2000,
        retry: false,
    });

    const selectedJob = useMemo(
        () => jobsQuery.data?.jobs.find((j) => j.id === selectedJobId) ?? null,
        [jobsQuery.data?.jobs, selectedJobId],
    );

    const logQuery = useQuery({
        queryKey: ["admin-job-logs", selectedJobId],
        queryFn: () => adminOpsApi.getJobLogs(selectedJobId!, { tail: 160 }),
        enabled: isAdmin && Boolean(selectedJobId),
        refetchInterval: 2000,
        retry: false,
    });

    const trendingQuery = useQuery({
        queryKey: ["admin-trending-strategies"],
        queryFn: () => adminOpsApi.listTrendingStrategies({ limit: 200 }),
        enabled: isAdmin,
        refetchInterval: 5000,
        retry: false,
    });

    const cancelMutation = useMutation({
        mutationFn: (jobId: string) => adminOpsApi.cancelJob(jobId),
        onSuccess: async () => {
            await qc.invalidateQueries({ queryKey: ["admin-jobs"] });
            await qc.invalidateQueries({ queryKey: ["admin-queue"] });
        },
    });

    const deleteMutation = useMutation({
        mutationFn: (tradingviewId: string) => adminOpsApi.deleteTrendingStrategy(tradingviewId),
        onSuccess: async () => {
            await qc.invalidateQueries({ queryKey: ["admin-trending-strategies"] });
        },
    });

    const triggerPerformanceMutation = useMutation({
        mutationFn: (templateId: string) => templatesApi.triggerPerformanceUpdate(templateId),
        onSuccess: (data) => {
            toast.success(data.message);
            qc.invalidateQueries({ queryKey: ["admin-jobs"] });
            qc.invalidateQueries({ queryKey: ["admin-queue"] });
        },
        onError: (error) => {
            toast.error(error instanceof Error ? error.message : t("adminTrending.scraped.triggerFailed"));
        },
    });

    const headerActions = (
        <div className="flex items-center gap-2">
            <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => {
                    queueQuery.refetch();
                    jobsQuery.refetch();
                    trendingQuery.refetch();
                    logQuery.refetch();
                }}
                disabled={!isAdmin}
            >
                <RefreshCw size={14} />
                Refresh
            </Button>
        </div>
    );

    return (
        <MainLayout
            currentPage="home"
            title={t("adminTrending.title")}
            description={t("adminTrending.subtitle")}
            headerActions={headerActions}
        >
            {!authQuery.data?.user ? (
            <div className="p-4 sm:p-6">
                    <Card>
                        <CardContent className="py-10 text-center text-muted-foreground">
                            {t("adminTrending.signInRequired")}
                        </CardContent>
                    </Card>
                </div>
            ) : !isAdmin ? (
            <div className="p-4 sm:p-6">
                    <Card>
                        <CardContent className="py-10 text-center">
                            <div className="flex items-center justify-center gap-2 text-destructive">
                                <XCircle className="w-5 h-5" />
                                <span>{t("adminTrending.adminRequired")}</span>
                            </div>
                            <div className="mt-2 text-sm text-muted-foreground">
                                {t("adminTrending.notAllowlisted")}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            ) : (
            <div className="p-4 space-y-6 sm:p-6">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <Card className="lg:col-span-1">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base">{t("adminTrending.queue.title")}</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-2">
                                {queueQuery.isLoading ? (
                                    <div className="flex items-center gap-2 text-muted-foreground text-sm">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        {t("adminTrending.queue.loading")}
                                    </div>
                                ) : (
                                    <>
                                        <div className="text-sm">
                                            <span className="text-muted-foreground">{t("adminTrending.queue.length")}:</span>{" "}
                                            <span className="font-medium">{queueQuery.data?.length ?? "-"}</span>
                                        </div>
                                        <div className="text-xs text-muted-foreground">{t("adminTrending.queue.head")}</div>
                                        <div className="space-y-1">
                                            {(queueQuery.data?.head ?? []).length === 0 ? (
                                                <div className="text-sm text-muted-foreground">{t("adminTrending.queue.empty")}</div>
                                            ) : (
                                                (queueQuery.data?.head ?? []).map((id) => (
                                                    <button
                                                        key={id}
                                                        onClick={() => setSelectedJobId(id)}
                                                        className={cn(
                                                            "w-full text-left text-xs font-mono px-2 py-1 rounded border",
                                                            selectedJobId === id
                                                                ? "border-primary bg-primary/5 text-foreground"
                                                                : "border-border text-muted-foreground hover:bg-muted",
                                                        )}
                                                    >
                                                        {id}
                                                    </button>
                                                ))
                                            )}
                                        </div>
                                    </>
                                )}
                            </CardContent>
                        </Card>

                        <Card className="lg:col-span-2">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base">{t("adminTrending.jobs.title")}</CardTitle>
                            </CardHeader>
                            <CardContent>
                                {jobsQuery.isLoading ? (
                                    <div className="flex items-center gap-2 text-muted-foreground text-sm">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        {t("adminTrending.jobs.loading")}
                                    </div>
                                ) : (
                                    <div className="max-h-[420px] overflow-auto">
                                        <table className="w-full text-sm">
                                            <thead className="sticky top-0 bg-card">
                                                <tr className="border-b border-border">
                                                    <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.jobs.columns.id")}</th>
                                                    <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.jobs.columns.type")}</th>
                                                    <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.jobs.columns.status")}</th>
                                                    <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.jobs.columns.created")}</th>
                                                    <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.jobs.columns.age")}</th>
                                                    <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.jobs.columns.lastLog")}</th>
                                                    <th className="text-right py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.jobs.columns.action")}</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {(jobsQuery.data?.jobs ?? []).map((j) => {
                                                    const age = formatDuration(msSince(j.created_at));
                                                    const canCancel = j.status === "queued" || j.status === "running";
                                                    return (
                                                        <tr
                                                            key={j.id}
                                                            className={cn(
                                                                "border-b border-border/50 cursor-pointer",
                                                                selectedJobId === j.id && "bg-primary/5",
                                                            )}
                                                            onClick={() => setSelectedJobId(j.id)}
                                                        >
                                                            <td className="py-2 px-2 font-mono text-xs text-muted-foreground">{j.id.slice(0, 8)}…</td>
                                                            <td className="py-2 px-2 text-muted-foreground">{j.type}</td>
                                                            <td className="py-2 px-2">
                                                                <Badge variant={statusVariant(j.status)}>{j.status}</Badge>
                                                            </td>
                                                            <td className="py-2 px-2 text-muted-foreground">
                                                                {formatShort(j.created_at)}
                                                            </td>
                                                            <td className="py-2 px-2 text-muted-foreground">{age}</td>
                                                            <td className="py-2 px-2 text-xs text-muted-foreground">
                                                                <div className="max-w-[420px] truncate">{j.last_log ?? ""}</div>
                                                            </td>
                                                            <td className="py-2 px-2 text-right">
                                                                <Button
                                                                    size="sm"
                                                                    variant="outline"
                                                                    disabled={!canCancel || cancelMutation.isPending}
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        if (!confirm(t("adminTrending.jobs.confirmCancel", { id: j.id }))) return;
                                                                        cancelMutation.mutate(j.id);
                                                                    }}
                                                                >
                                                                    {t("adminTrending.jobs.cancel")}
                                                                </Button>
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>

                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-base">{t("adminTrending.logs.title")}</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {!selectedJobId ? (
                                <div className="text-sm text-muted-foreground">{t("adminTrending.logs.empty")}</div>
                            ) : (
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <div className="text-sm">
                                            <span className="font-mono">{selectedJobId}</span>{" "}
                                            {selectedJob ? (
                                                <Badge variant={statusVariant(selectedJob.status)} className="ml-2">
                                                    {selectedJob.status}
                                                </Badge>
                                            ) : null}
                                        </div>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="gap-2"
                                            onClick={() => logQuery.refetch()}
                                            disabled={!logQuery.isFetched}
                                        >
                                            <RefreshCw size={14} />
                                            {t("adminTrending.logs.refresh")}
                                        </Button>
                                    </div>
                                    <ScrollArea className="h-64 rounded-md border border-border bg-zinc-950">
                                        <div className="p-2 font-mono text-xs text-zinc-200 space-y-1">
                                            {(logQuery.data?.lines ?? []).length === 0 ? (
                                                <div className="text-zinc-400">{t("adminTrending.logs.noLogs")}</div>
                                            ) : (
                                                (logQuery.data?.lines ?? []).map((line, idx) => (
                                                    <div key={idx} className="whitespace-pre-wrap break-words">
                                                        {line}
                                                    </div>
                                                ))
                                            )}
                                        </div>
                                    </ScrollArea>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-base">{t("adminTrending.scraped.title")}</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {trendingQuery.isLoading ? (
                                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    {t("adminTrending.scraped.loading")}
                                </div>
                            ) : (
                                <div className="max-h-[520px] overflow-auto">
                                    <table className="w-full text-sm">
                                        <thead className="sticky top-0 bg-card">
                                            <tr className="border-b border-border">
                                                <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.scraped.columns.id")}</th>
                                                <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.scraped.columns.title")}</th>
                                                <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.scraped.columns.source")}</th>
                                                <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.scraped.columns.scraped")}</th>
                                                <th className="text-left py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.scraped.columns.backtest")}</th>
                                                <th className="text-right py-2 px-2 font-medium text-muted-foreground uppercase text-xs">{t("adminTrending.scraped.columns.action")}</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {(trendingQuery.data?.items ?? []).map((s) => (
                                                <tr key={s.tradingview_id} className="border-b border-border/50">
                                                    <td className="py-2 px-2 font-mono text-xs text-muted-foreground">{s.tradingview_id}</td>
                                                    <td className="py-2 px-2">
                                                        <a
                                                            href={s.url}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            className="text-sm font-medium text-foreground hover:underline"
                                                        >
                                                            {s.title}
                                                        </a>
                                                    </td>
                                                    <td className="py-2 px-2 text-muted-foreground">{s.source_type}</td>
                                                    <td className="py-2 px-2 text-muted-foreground">{formatShort(s.scraped_at)}</td>
                                                    <td className="py-2 px-2 text-muted-foreground">{s.backtest_status}</td>
                                                    <td className="py-2 px-2 text-right">
                                                        <div className="flex justify-end gap-2">
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                disabled={!s.template_id || triggerPerformanceMutation.isPending}
                                                                onClick={() => {
                                                                    if (!s.template_id) return;
                                                                    triggerPerformanceMutation.mutate(s.template_id);
                                                                }}
                                                            >
                                                                {t("adminTrending.scraped.triggerPerformance")}
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                disabled={deleteMutation.isPending}
                                                                onClick={() => {
                                                                    if (!confirm(t("adminTrending.scraped.confirmDelete", { id: s.tradingview_id }))) return;
                                                                    deleteMutation.mutate(s.tradingview_id);
                                                                }}
                                                            >
                                                                {t("adminTrending.scraped.delete")}
                                                            </Button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            )}
        </MainLayout>
    );
};

export default AdminTrending;
