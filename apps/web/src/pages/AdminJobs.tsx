import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { 
    AlertCircle, 
    CheckCircle2, 
    Clock, 
    Loader2, 
    RefreshCw, 
    ShieldAlert, 
    StopCircle, 
    Terminal
} from "lucide-react";
import MainLayout from "@/components/layout/MainLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { adminOpsApi, authApi, templatesApi } from "@/lib/api";
import type { JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { TRENDING_ENABLED } from "@/lib/featureFlags";

const msSince = (iso?: string) => {
    if (!iso) return null;
    const t = new Date(iso).getTime();
    if (!Number.isFinite(t)) return null;
    return Date.now() - t;
};

const StatusBadge = ({ status }: { status: JobStatus }) => {
    if (status === "running") {
        return (
            <Badge variant="outline" className="border-blue-500/40 text-blue-400 bg-blue-500/10 gap-1 font-mono text-xs">
                <Loader2 className="w-3 h-3 animate-spin" />
                running
            </Badge>
        );
    }
    if (status === "succeeded") {
        return (
            <Badge variant="default" className="bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 gap-1 font-mono text-xs">
                <CheckCircle2 className="w-3 h-3" />
                succeeded
            </Badge>
        );
    }
    if (status === "failed") {
        return (
            <Badge variant="destructive" className="gap-1 font-mono text-xs">
                <AlertCircle className="w-3 h-3" />
                failed
            </Badge>
        );
    }
    if (status === "queued") {
        return (
            <Badge variant="secondary" className="gap-1 font-mono text-xs">
                <Clock className="w-3 h-3" />
                queued
            </Badge>
        );
    }
    return (
        <Badge variant="secondary" className="gap-1 font-mono text-xs text-muted-foreground">
            <StopCircle className="w-3 h-3" />
            {status}
        </Badge>
    );
};

export const AdminJobs = () => {
    const { t, i18n } = useTranslation();
    const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";
    const formatShort = (iso: string) =>
        new Date(iso).toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const formatDuration = (ms?: number | null) => {
        if (!ms || ms < 0) return t("adminOps.duration.na");
        const s = Math.floor(ms / 1000);
        if (s < 60) return t("adminOps.duration.seconds", { count: s });
        const m = Math.floor(s / 60);
        if (m < 60) return t("adminOps.duration.minutes", { count: m });
        const h = Math.floor(m / 60);
        return t("adminOps.duration.hoursMinutes", { hours: h, minutes: m % 60 });
    };

    const qc = useQueryClient();
    const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
    const [statusFilter, setStatusFilter] = useState<string>("all");

    // 1. Authentication & Permission Verification
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

    const isAuthed = Boolean(authQuery.data?.user);
    const isAdmin = Boolean(authQuery.data?.is_admin);

    // 2. Queue Query
    const queueQuery = useQuery({
        queryKey: ["admin-queue"],
        queryFn: () => adminOpsApi.getQueue({ head_n: 10 }),
        enabled: isAdmin,
        refetchInterval: 3000,
        retry: false,
    });

    // 3. Jobs Query
    const jobsQuery = useQuery({
        queryKey: ["admin-jobs"],
        queryFn: () => adminOpsApi.listJobs({ limit: 100 }),
        enabled: isAdmin,
        refetchInterval: 3000,
        retry: false,
    });

    const filteredJobs = useMemo(() => {
        const jobs = jobsQuery.data?.jobs ?? [];
        if (statusFilter === "all") return jobs;
        return jobs.filter((j) => j.status === statusFilter);
    }, [jobsQuery.data?.jobs, statusFilter]);

    const selectedJob = useMemo(
        () => jobsQuery.data?.jobs.find((j) => j.id === selectedJobId) ?? null,
        [jobsQuery.data?.jobs, selectedJobId],
    );

    // 4. Job Logs Query
    const logQuery = useQuery({
        queryKey: ["admin-job-logs", selectedJobId],
        queryFn: () => adminOpsApi.getJobLogs(selectedJobId!, { tail: 200 }),
        enabled: isAdmin && Boolean(selectedJobId),
        refetchInterval: selectedJob?.status === "running" ? 2000 : false,
        retry: false,
    });

    // 5. Scraped Strategies Query (Only enabled if TRENDING_ENABLED)
    const trendingQuery = useQuery({
        queryKey: ["admin-trending-strategies"],
        queryFn: () => adminOpsApi.listTrendingStrategies({ limit: 200 }),
        enabled: isAdmin && TRENDING_ENABLED,
        refetchInterval: 10000,
        retry: false,
    });

    // 6. Job Cancel Mutation with user feedback
    const cancelMutation = useMutation({
        mutationFn: (jobId: string) => adminOpsApi.cancelJob(jobId),
        onSuccess: async (_, jobId) => {
            toast.success(t("adminOps.jobs.cancelSuccess", { id: jobId.slice(0, 8) }));
            await qc.invalidateQueries({ queryKey: ["admin-jobs"] });
            await qc.invalidateQueries({ queryKey: ["admin-queue"] });
            if (selectedJobId) {
                await qc.invalidateQueries({ queryKey: ["admin-job-logs", selectedJobId] });
            }
        },
        onError: (error) => {
            toast.error(error instanceof Error ? error.message : t("adminOps.jobs.cancelFailed"));
        },
    });

    // 7. Scraped Strategy Delete Mutation (Only if TRENDING_ENABLED)
    const deleteTrendingMutation = useMutation({
        mutationFn: (tradingviewId: string) => adminOpsApi.deleteTrendingStrategy(tradingviewId),
        onSuccess: async () => {
            await qc.invalidateQueries({ queryKey: ["admin-trending-strategies"] });
            toast.success("Item deleted");
        },
        onError: (err) => {
            toast.error(err instanceof Error ? err.message : "Delete failed");
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
            toast.error(error instanceof Error ? error.message : t("adminOps.scraped.triggerFailed"));
        },
    });

    const isRefreshing = queueQuery.isFetching || jobsQuery.isFetching || logQuery.isFetching;

    const handleRefreshAll = () => {
        queueQuery.refetch();
        jobsQuery.refetch();
        if (selectedJobId) logQuery.refetch();
        if (TRENDING_ENABLED) trendingQuery.refetch();
    };

    const headerActions = (
        <div className="flex items-center gap-2">
            <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={handleRefreshAll}
                disabled={!isAdmin || isRefreshing}
            >
                <RefreshCw size={14} className={cn(isRefreshing && "animate-spin")} />
                {t("adminOps.logs.refresh")}
            </Button>
        </div>
    );

    return (
        <MainLayout
            currentPage="home"
            title={t("adminOps.title")}
            description={t("adminOps.subtitle")}
            headerActions={headerActions}
        >
            {/* Loading state for auth verification */}
            {authQuery.isLoading ? (
                <div className="p-12 flex flex-col items-center justify-center gap-3 text-muted-foreground">
                    <Loader2 className="w-6 h-6 animate-spin text-primary" />
                    <span className="text-sm">Verifying admin permissions...</span>
                </div>
            ) : !isAuthed ? (
                /* Unauthenticated state */
                <div className="p-4 sm:p-6 max-w-xl mx-auto mt-8">
                    <Card>
                        <CardHeader className="text-center">
                            <CardTitle className="text-lg">{t("adminOps.signInRequired")}</CardTitle>
                            <CardDescription>Please log in with an administrator account to access system operations.</CardDescription>
                        </CardHeader>
                    </Card>
                </div>
            ) : !isAdmin ? (
                /* Not an administrator */
                <div className="p-4 sm:p-6 max-w-xl mx-auto mt-8">
                    <Card className="border-destructive/30">
                        <CardContent className="py-10 text-center space-y-3">
                            <div className="flex items-center justify-center gap-2 text-destructive font-medium text-lg">
                                <ShieldAlert className="w-6 h-6" />
                                <span>{t("adminOps.adminRequired")}</span>
                            </div>
                            <div className="text-sm text-muted-foreground">
                                {t("adminOps.notAllowlisted")}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            ) : (
                /* Authenticated Admin View */
                <div className="p-4 space-y-6 sm:p-6">
                    {/* Top Section: Queue Status & Quick Controls */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        {/* Queue Card */}
                        <Card className="lg:col-span-1">
                            <CardHeader className="pb-3">
                                <div className="flex items-center justify-between">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Clock className="w-4 h-4 text-primary" />
                                        {t("adminOps.queue.title")}
                                    </CardTitle>
                                    {queueQuery.data && (
                                        <Badge
                                            variant={queueQuery.data.length > 5 ? "destructive" : "secondary"}
                                            className="text-xs"
                                        >
                                            {queueQuery.data.length > 5 ? t("adminOps.queue.backlog") : t("adminOps.queue.healthy")}
                                        </Badge>
                                    )}
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {queueQuery.isLoading ? (
                                    <div className="flex items-center gap-2 text-muted-foreground text-sm">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        {t("adminOps.queue.loading")}
                                    </div>
                                ) : (
                                    <>
                                        <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/40 border border-border">
                                            <span className="text-xs text-muted-foreground">{t("adminOps.queue.length")}</span>
                                            <span className="font-mono text-base font-bold text-foreground">
                                                {queueQuery.data?.length ?? 0}
                                            </span>
                                        </div>

                                        <div className="space-y-1.5 pt-1">
                                            <div className="text-xs font-medium text-muted-foreground">
                                                {t("adminOps.queue.head")}
                                            </div>
                                            {(queueQuery.data?.head ?? []).length === 0 ? (
                                                <div className="text-xs text-muted-foreground p-3 rounded border border-dashed text-center">
                                                    {t("adminOps.queue.empty")}
                                                </div>
                                            ) : (
                                                <div className="space-y-1 max-h-36 overflow-y-auto">
                                                    {(queueQuery.data?.head ?? []).map((id) => (
                                                        <button
                                                            key={id}
                                                            onClick={() => setSelectedJobId(id)}
                                                            className={cn(
                                                                "w-full text-left text-xs font-mono px-2.5 py-1.5 rounded border transition-colors flex items-center justify-between",
                                                                selectedJobId === id
                                                                    ? "border-primary bg-primary/10 text-primary font-semibold"
                                                                    : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
                                                            )}
                                                        >
                                                            <span className="truncate">{id}</span>
                                                            <Terminal className="w-3 h-3 opacity-60 ml-1 flex-shrink-0" />
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </>
                                )}
                            </CardContent>
                        </Card>

                        {/* Background Jobs List */}
                        <Card className="lg:col-span-2">
                            <CardHeader className="pb-3">
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Terminal className="w-4 h-4 text-primary" />
                                        {t("adminOps.jobs.title")}
                                        <span className="text-xs font-normal text-muted-foreground">
                                            ({filteredJobs.length})
                                        </span>
                                    </CardTitle>

                                    {/* Status Filter */}
                                    <div className="flex items-center gap-1.5 overflow-x-auto">
                                        {["all", "running", "queued", "failed", "succeeded"].map((s) => (
                                            <Button
                                                key={s}
                                                size="sm"
                                                variant={statusFilter === s ? "default" : "ghost"}
                                                className="h-7 px-2.5 text-xs capitalize"
                                                onClick={() => setStatusFilter(s)}
                                            >
                                                {s === "all" ? t("adminOps.jobs.filterAll") : s}
                                            </Button>
                                        ))}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {jobsQuery.isLoading ? (
                                    <div className="flex items-center gap-2 text-muted-foreground text-sm py-8 justify-center">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        {t("adminOps.jobs.loading")}
                                    </div>
                                ) : filteredJobs.length === 0 ? (
                                    <div className="py-12 text-center text-sm text-muted-foreground border border-dashed rounded-lg">
                                        {t("adminOps.jobs.noJobs")}
                                    </div>
                                ) : (
                                    <div className="max-h-[380px] overflow-auto border rounded-md">
                                        <table className="w-full text-sm">
                                            <thead className="sticky top-0 bg-muted/80 backdrop-blur border-b text-xs uppercase font-medium text-muted-foreground">
                                                <tr>
                                                    <th className="text-left py-2 px-3">{t("adminOps.jobs.columns.id")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.jobs.columns.type")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.jobs.columns.status")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.jobs.columns.created")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.jobs.columns.age")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.jobs.columns.lastLog")}</th>
                                                    <th className="text-right py-2 px-3">{t("adminOps.jobs.columns.action")}</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-border/60">
                                                {filteredJobs.map((j) => {
                                                    const age = formatDuration(msSince(j.created_at));
                                                    const canCancel = j.status === "queued" || j.status === "running";
                                                    const isSelected = selectedJobId === j.id;

                                                    return (
                                                        <tr
                                                            key={j.id}
                                                            className={cn(
                                                                "cursor-pointer transition-colors hover:bg-muted/50",
                                                                isSelected && "bg-primary/5 font-medium",
                                                            )}
                                                            onClick={() => setSelectedJobId(j.id)}
                                                        >
                                                            <td className="py-2.5 px-3 font-mono text-xs text-foreground">
                                                                {j.id.slice(0, 8)}…
                                                            </td>
                                                            <td className="py-2.5 px-3">
                                                                <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-muted">
                                                                    {j.type}
                                                                </span>
                                                            </td>
                                                            <td className="py-2.5 px-3">
                                                                <StatusBadge status={j.status} />
                                                            </td>
                                                            <td className="py-2.5 px-3 text-xs text-muted-foreground whitespace-nowrap">
                                                                {formatShort(j.created_at)}
                                                            </td>
                                                            <td className="py-2.5 px-3 text-xs text-muted-foreground whitespace-nowrap">
                                                                {age}
                                                            </td>
                                                            <td className="py-2.5 px-3 text-xs text-muted-foreground">
                                                                <div className="max-w-[280px] truncate font-mono text-[11px]">
                                                                    {j.last_log || (j.error_message ? `Err: ${j.error_message}` : "-")}
                                                                </div>
                                                            </td>
                                                            <td className="py-2.5 px-3 text-right">
                                                                {canCancel && (
                                                                    <Button
                                                                        size="sm"
                                                                        variant="destructive"
                                                                        className="h-7 px-2 text-xs"
                                                                        disabled={cancelMutation.isPending && cancelMutation.variables === j.id}
                                                                        onClick={(e) => {
                                                                            e.stopPropagation();
                                                                            if (!confirm(t("adminOps.jobs.confirmCancel", { id: j.id.slice(0, 8) }))) return;
                                                                            cancelMutation.mutate(j.id);
                                                                        }}
                                                                    >
                                                                        {cancelMutation.isPending && cancelMutation.variables === j.id ? (
                                                                            <Loader2 className="w-3 h-3 animate-spin" />
                                                                        ) : (
                                                                            t("adminOps.jobs.cancel")
                                                                        )}
                                                                    </Button>
                                                                )}
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

                    {/* Middle Section: Real-time Job Container Log Viewer */}
                    <Card className="border-border shadow-sm">
                        <CardHeader className="pb-3">
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Terminal className="w-4 h-4 text-primary" />
                                        {t("adminOps.logs.title")}
                                    </CardTitle>
                                    <CardDescription className="text-xs">
                                        {selectedJobId
                                            ? `Job ID: ${selectedJobId} (${selectedJob?.type ?? "unknown"})`
                                            : t("adminOps.logs.empty")}
                                    </CardDescription>
                                </div>
                                {selectedJobId && (
                                    <div className="flex items-center gap-2">
                                        {selectedJob && <StatusBadge status={selectedJob.status} />}
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="h-7 gap-1.5 text-xs"
                                            onClick={() => logQuery.refetch()}
                                            disabled={logQuery.isFetching}
                                        >
                                            <RefreshCw size={12} className={cn(logQuery.isFetching && "animate-spin")} />
                                            {t("adminOps.logs.refresh")}
                                        </Button>
                                    </div>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent>
                            {!selectedJobId ? (
                                <div className="py-12 text-center text-sm text-muted-foreground border border-dashed rounded-lg">
                                    {t("adminOps.logs.empty")}
                                </div>
                            ) : (
                                <ScrollArea className="h-72 rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs text-zinc-200">
                                    {(logQuery.data?.lines ?? []).length === 0 ? (
                                        <div className="text-zinc-500 py-6 text-center italic">
                                            {logQuery.isLoading ? "Loading logs..." : t("adminOps.logs.noLogs")}
                                        </div>
                                    ) : (
                                        <div className="space-y-1">
                                            {(logQuery.data?.lines ?? []).map((line, idx) => (
                                                <div key={idx} className="whitespace-pre-wrap break-all leading-relaxed hover:bg-zinc-900/50 px-1 rounded">
                                                    {line}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>

                    {/* Bottom Section: Gated Peripheral Scraped Strategies (Only if TRENDING_ENABLED) */}
                    {TRENDING_ENABLED && (
                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-base">{t("adminOps.scraped.title")}</CardTitle>
                            </CardHeader>
                            <CardContent>
                                {trendingQuery.isLoading ? (
                                    <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        {t("adminOps.scraped.loading")}
                                    </div>
                                ) : (
                                    <div className="max-h-[400px] overflow-auto border rounded-md">
                                        <table className="w-full text-sm">
                                            <thead className="sticky top-0 bg-muted/80 backdrop-blur border-b text-xs uppercase font-medium text-muted-foreground">
                                                <tr>
                                                    <th className="text-left py-2 px-3">{t("adminOps.scraped.columns.id")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.scraped.columns.title")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.scraped.columns.source")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.scraped.columns.scraped")}</th>
                                                    <th className="text-left py-2 px-3">{t("adminOps.scraped.columns.backtest")}</th>
                                                    <th className="text-right py-2 px-3">{t("adminOps.scraped.columns.action")}</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {(trendingQuery.data?.items ?? []).map((s) => (
                                                    <tr key={s.tradingview_id} className="border-b border-border/50 hover:bg-muted/40">
                                                        <td className="py-2 px-3 font-mono text-xs text-muted-foreground">{s.tradingview_id}</td>
                                                        <td className="py-2 px-3">
                                                            <a
                                                                href={s.url}
                                                                target="_blank"
                                                                rel="noreferrer"
                                                                className="text-sm font-medium text-foreground hover:underline"
                                                            >
                                                                {s.title}
                                                            </a>
                                                        </td>
                                                        <td className="py-2 px-3 text-muted-foreground">{s.source_type}</td>
                                                        <td className="py-2 px-3 text-muted-foreground text-xs">{formatShort(s.scraped_at)}</td>
                                                        <td className="py-2 px-3 text-muted-foreground">{s.backtest_status}</td>
                                                        <td className="py-2 px-3 text-right">
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
                                                                    {t("adminOps.scraped.triggerPerformance")}
                                                                </Button>
                                                                <Button
                                                                    size="sm"
                                                                    variant="outline"
                                                                    disabled={deleteTrendingMutation.isPending}
                                                                    onClick={() => {
                                                                        if (!confirm(t("adminOps.scraped.confirmDelete", { id: s.tradingview_id }))) return;
                                                                        deleteTrendingMutation.mutate(s.tradingview_id);
                                                                    }}
                                                                >
                                                                    {t("adminOps.scraped.delete")}
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
                    )}
                </div>
            )}
        </MainLayout>
    );
};

export default AdminJobs;
