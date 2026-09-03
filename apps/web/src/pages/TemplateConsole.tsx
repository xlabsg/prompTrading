import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bell, Copy } from "lucide-react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { authApi, subscriptionsApi, templatesApi } from "@/lib/api";
import type { SubscriptionResponse, TemplateDetail } from "@/lib/types";
import { ForkTemplateDialog } from "@/components/template/ForkTemplateDialog";
import BacktestView from "@/components/console/BacktestView";
import { useTranslation } from "react-i18next";

type TemplateTab = "backtest";

function isTemplateTab(value: string | undefined): value is TemplateTab {
    return value === "backtest";
}

export function TemplateConsole() {
    const navigate = useNavigate();
    const { templateId, tab } = useParams();
    const activeTab = isTemplateTab(tab) ? tab : ("backtest" as TemplateTab);
    const { t } = useTranslation();

    const [forkDialogOpen, setForkDialogOpen] = useState(false);

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

    const templateQuery = useQuery<TemplateDetail>({
        queryKey: ["template", templateId],
        queryFn: () => templatesApi.get(templateId!),
        enabled: Boolean(templateId),
        refetchOnWindowFocus: false,
    });

    const subscriptionsQuery = useQuery({
        queryKey: ["subscriptions"],
        queryFn: () => subscriptionsApi.list(),
        enabled: Boolean(user),
        refetchOnWindowFocus: false,
        retry: false,
    });

    const template = templateQuery.data ?? null;

    const subscription = useMemo<SubscriptionResponse | null>(() => {
        const list = subscriptionsQuery.data?.subscriptions ?? [];
        const match = list.find((s) => s.template_id === templateId);
        return match ?? null;
    }, [subscriptionsQuery.data, templateId]);

    const headerActions = useMemo(() => {
        return (
            <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" onClick={() => navigate("/templates")}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    {t("common.back")}
                </Button>
                {subscription && (
                    <Button
                        onClick={() => navigate(`/strategy/${subscription.strategy_id}/overview`)}
                        title={t("templates.openCopyTooltip")}
                        variant="outline"
                    >
                        <Copy className="mr-2 h-4 w-4" />
                        {t("templates.openCopy")}
                    </Button>
                )}
                <Button onClick={() => setForkDialogOpen(true)} disabled={!template}>
                    <Copy className="mr-2 h-4 w-4" />
                    {t("templates.useTemplate", "使用模版")}
                </Button>
            </div>
        );
    }, [navigate, subscription, template, t]);

    return (
        <>
            <MainLayout
                currentPage="templates"
                title={template?.name ?? t("templateConsole.titleFallback")}
                description={template?.description ?? t("templateConsole.descriptionFallback")}
                headerActions={headerActions}
            >
                <div className="px-4 py-3 border-b border-border sm:px-6 sm:py-4">
                    <div className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
                        <div className="font-medium">{t("templateConsole.readOnly.title")}</div>
                        <div className="text-muted-foreground">
                            {t("templateConsole.readOnly.subtitle")}
                        </div>
                        {subscription && (
                            <div className="mt-2 text-muted-foreground">
                                {t("templateConsole.readOnly.subscribedAs")}{" "}
                                <span className="text-foreground">{subscription.strategy_name}</span>
                            </div>
                        )}
                    </div>
                </div>

                <div className="p-4 sm:p-6">
                    {templateQuery.isLoading ? (
                        <div className="space-y-4">
                            <Skeleton className="h-8 w-72" />
                            <Skeleton className="h-4 w-full" />
                            <Skeleton className="h-4 w-2/3" />
                        </div>
                    ) : templateQuery.error ? (
                        <div className="text-sm text-destructive">
                            {templateQuery.error instanceof Error
                                ? templateQuery.error.message
                                : t("templateConsole.errors.loadTemplate")}
                        </div>
                    ) : (
                        <Tabs
                            value={activeTab}
                            onValueChange={(value) => {
                                if (!isTemplateTab(value)) return;
                                navigate(`/template/${templateId}/${value}`);
                            }}
                            className="w-full"
                        >
                            <TabsList className="grid w-full grid-cols-1">
                                <TabsTrigger value="backtest">{t("templateConsole.tabs.backtest")}</TabsTrigger>
                            </TabsList>

                            <TabsContent value="backtest" className="mt-4 space-y-4">
                                <BacktestView
                                    strategy={null}
                                    mode="template"
                                    templateId={templateId}
                                    readOnly
                                    hideActions
                                    hideSettings
                                />
                            </TabsContent>

                        </Tabs>
                    )}
                </div>
            </MainLayout>

            <ForkTemplateDialog template={template} open={forkDialogOpen} onOpenChange={setForkDialogOpen} />
        </>
    );
}

export default TemplateConsole;
