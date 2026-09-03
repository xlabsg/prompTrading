import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Copy, Sparkles, Shield, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import type { TemplateDetail, TemplateListItem } from "@/lib/types";
import { templatesApi } from "@/lib/api";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

interface ForkTemplateDialogProps {
    template: TemplateDetail | TemplateListItem | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function ForkTemplateDialog({ template, open, onOpenChange }: ForkTemplateDialogProps) {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { t } = useTranslation();
    const [loading, setLoading] = useState(false);
    const [formData, setFormData] = useState({
        name: "",
        description: "",
    });

    const handleFork = async () => {
        if (!template) return;
        if (!formData.name.trim()) {
            toast.error(t("templates.forkErrors.nameRequired", "请输入策略名称"));
            return;
        }

        setLoading(true);
        try {
            const res = await templatesApi.fork(template.id, {
                name: formData.name.trim(),
                description: formData.description.trim() || undefined,
            });
            toast.success(res.message || t("templates.forkSuccess", "策略创建成功！"));
            queryClient.invalidateQueries({ queryKey: ["strategies"] });
            onOpenChange(false);
            navigate(`/strategy/${res.strategy_id}/overview`);
        } catch (error) {
            toast.error(error instanceof Error ? error.message : t("templates.forkErrors.failed", "创建策略失败"));
        } finally {
            setLoading(false);
        }
    };

    const handleOpenChange = (newOpen: boolean) => {
        if (newOpen && template) {
            setFormData({
                name: `${template.name} (Copy)`,
                description: template.description || "",
            });
        }
        onOpenChange(newOpen);
    };

    if (!template) return null;

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Copy className="w-5 h-5 text-primary" />
                        {t("templates.forkTitle", "基于模版创建策略")}
                    </DialogTitle>
                    <DialogDescription>
                        {t("templates.forkSubtitle", "克隆官方模版至您的专属工作区，立即可回测、实盘或与 AI 对话迭代。")}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-3">
                    {/* Template Overview Card */}
                    <div className="rounded-lg border border-border bg-muted/40 p-3 text-xs space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-sm text-foreground">{template.name}</span>
                            <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                                {template.template_type}
                            </span>
                        </div>
                        {template.description && (
                            <p className="text-muted-foreground line-clamp-2">{template.description}</p>
                        )}
                        <div className="flex flex-wrap gap-2 pt-1 text-muted-foreground">
                            {template.risk_level && (
                                <span className="flex items-center gap-1">
                                    <Shield size={12} />
                                    {template.risk_level}
                                </span>
                            )}
                            {template.trading_frequency && (
                                <span className="flex items-center gap-1">
                                    <Clock size={12} />
                                    {template.trading_frequency}
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Strategy Name */}
                    <div className="space-y-2">
                        <Label htmlFor="strategy-name">
                            {t("templates.fields.strategyName", "策略名称")} <span className="text-red-500">*</span>
                        </Label>
                        <Input
                            id="strategy-name"
                            value={formData.name}
                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            placeholder={t("templates.placeholders.strategyName", "输入策略名称...")}
                            disabled={loading}
                        />
                    </div>

                    {/* Description */}
                    <div className="space-y-2">
                        <Label htmlFor="strategy-desc">
                            {t("templates.fields.description", "策略描述 (可选)")}
                        </Label>
                        <Textarea
                            id="strategy-desc"
                            value={formData.description}
                            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                            placeholder={t("templates.placeholders.description", "简短描述您的策略目标...")}
                            rows={2}
                            disabled={loading}
                        />
                    </div>
                </div>

                <DialogFooter className="gap-2 sm:gap-0">
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                        {t("common.cancel", "取消")}
                    </Button>
                    <Button onClick={handleFork} disabled={loading || !formData.name.trim()}>
                        {loading ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                {t("templates.forking", "创建中...")}
                            </>
                        ) : (
                            <>
                                <Sparkles className="mr-2 h-4 w-4" />
                                {t("templates.createStrategy", "创建策略")}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
