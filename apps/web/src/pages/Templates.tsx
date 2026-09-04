import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Library } from "lucide-react";
import { TemplateCard } from "@/components/template/TemplateCard";
import { TemplateFilters } from "@/components/template/TemplateFilters";
import { ForkTemplateDialog } from "@/components/template/ForkTemplateDialog";
import { TemplatePerformanceDialog } from "@/components/template/TemplatePerformanceDialog";
import { MainLayout } from "@/components/layout/MainLayout";
import { templatesApi } from "@/lib/api";
import type { TemplateDetail } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";
import { useTranslation } from "react-i18next";

export function TemplatesPage() {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [search, setSearch] = useState("");
    const [templateType, setTemplateType] = useState("all");
    const [featured, setFeatured] = useState(false);
    const [sort, setSort] = useState("popular");
    const [selectedTemplate, setSelectedTemplate] = useState<TemplateDetail | null>(null);
    const [forkDialogOpen, setForkDialogOpen] = useState(false);
    const [performanceDialogOpen, setPerformanceDialogOpen] = useState(false);

    const { data, isLoading, error } = useQuery({
        queryKey: ["templates", templateType, featured, sort, search],
        queryFn: () =>
            templatesApi.list({
                template_type: templateType === "all" ? undefined : templateType,
                featured: featured || undefined,
                sort: sort || undefined,
                search: search || undefined,
                limit: 50,
            }),
    });

    const templates = data?.templates || [];

    const openTemplateDetail = (templateId: string) => {
        navigate(`/template/${templateId}/backtest`);
    };

    const openForkById = async (templateId: string) => {
        try {
            const detail = await templatesApi.get(templateId);
            setSelectedTemplate(detail);
            setForkDialogOpen(true);
        } catch (err) {
            console.error("Failed to load template details:", err);
        }
    };

    const openPerformanceById = async (templateId: string) => {
        try {
            const detail = await templatesApi.get(templateId);
            setSelectedTemplate(detail);
            setPerformanceDialogOpen(true);
        } catch (err) {
            console.error("Failed to load template details:", err);
        }
    };

    const headerActions = (
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
                <Library size={16} />
                {t("templates.count", { count: data?.total || 0 })}
            </span>
        </div>
    );

    return (
        <>
            <MainLayout currentPage="templates" headerActions={headerActions}>
                {/* Filters */}
                <div className="px-4 pt-4 border-b border-border sm:px-6">
                    <TemplateFilters
                        search={search}
                        templateType={templateType}
                        featured={featured}
                        sort={sort}
                        onSearchChange={setSearch}
                        onTemplateTypeChange={setTemplateType}
                        onSortChange={setSort}
                        onFeaturedChange={setFeatured}
                    />
                </div>

                {/* Template Grid */}
                <div className="flex-1 overflow-auto p-4 sm:p-6">
                    {isLoading ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <div key={i} className="bg-card border border-border rounded-xl p-5">
                                    <div className="flex items-center gap-2 mb-3">
                                        <Skeleton className="h-5 w-16 rounded-full" />
                                        <Skeleton className="h-4 w-12 rounded" />
                                    </div>
                                    <Skeleton className="h-6 w-3/4 mb-2" />
                                    <Skeleton className="h-4 w-full mb-4" />
                                    <div className="flex gap-1">
                                        <Skeleton className="h-5 w-16 rounded" />
                                        <Skeleton className="h-5 w-16 rounded" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center h-64 text-center">
                            <Library size={48} className="text-muted-foreground mb-4" />
                            <h3 className="text-lg font-medium mb-2">{t("templates.loadFailed")}</h3>
                            <p className="text-muted-foreground">
                                {error instanceof Error ? error.message : t("templates.tryAgain")}
                            </p>
                        </div>
                    ) : templates.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-64 text-center">
                            <Library size={48} className="text-muted-foreground mb-4" />
                            <h3 className="text-lg font-medium mb-2">{t("templates.emptyTitle")}</h3>
                            <p className="text-muted-foreground">
                                {search
                                    ? t("templates.emptySearch")
                                    : t("templates.emptyLater")}
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {templates.map((template) => (
                                <TemplateCard
                                    key={template.id}
                                    template={template}
                                    onOpenDetail={openTemplateDetail}
                                    onFork={(t) => openForkById(t.id)}
                                    onViewPerformance={(t) => openPerformanceById(t.id)}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </MainLayout>

            <ForkTemplateDialog
                template={selectedTemplate}
                open={forkDialogOpen}
                onOpenChange={setForkDialogOpen}
            />

            <TemplatePerformanceDialog
                template={selectedTemplate}
                open={performanceDialogOpen}
                onOpenChange={setPerformanceDialogOpen}
            />
        </>
    );
}

export default TemplatesPage;
