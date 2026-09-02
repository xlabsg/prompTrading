import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Bell, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import type { TemplateDetail } from "@/lib/types";
import { templatesApi } from "@/lib/api";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

interface SignalSubscribeDialogProps {
    template: TemplateDetail | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function SignalSubscribeDialog({ template, open, onOpenChange }: SignalSubscribeDialogProps) {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [loading, setLoading] = useState(false);
    const [formData, setFormData] = useState({
        name: "",
        tg_bot_token: "",
        tg_chat_id: "",
        tg_notify_signal: true,
    });

    const handleSubscribe = async () => {
        if (!template) return;

        if (!formData.tg_bot_token || !formData.tg_chat_id) {
            toast.error(t("signalSubscribe.errors.missingTelegram"));
            return;
        }

        setLoading(true);
        try {
            const response = await templatesApi.subscribe(template.id, {
                name: formData.name,
                exchange: "okx",
                symbols: ["BTC-USDT-SWAP"], // Placeholder for signal-only subscriptions
                api_key_encrypted: "",  // Empty for signal-only
                api_secret_encrypted: "",
                api_passphrase_encrypted: "",
                max_position_pct: 10,
                stop_loss_pct: 5,
                telegram_config: {
                    bot_token_encrypted: formData.tg_bot_token,
                    chat_id: formData.tg_chat_id,
                    enabled: true,
                    notify_on_signal: formData.tg_notify_signal,
                    notify_on_execution: false,  // No trading, so no execution notifications
                    notify_on_error: true,
                },
            });
            toast.success(response.message);
            onOpenChange(false);
            navigate(`/strategy/${response.strategy_id}/backtest`);
        } catch (error) {
            toast.error(error instanceof Error ? error.message : t("signalSubscribe.errors.subscribe"));
        } finally {
            setLoading(false);
        }
    };

    const handleOpenChange = (newOpen: boolean) => {
        if (newOpen && template) {
            setFormData((prev) => ({
                ...prev,
                name: `${template.name} (Signal)`,
            }));
        }
        onOpenChange(newOpen);
    };

    if (!template) return null;

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Bell className="w-5 h-5 text-primary" />
                        {t("signalSubscribe.title")}
                    </DialogTitle>
                    <DialogDescription>
                        {t("signalSubscribe.subtitle", { name: template.name })}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Strategy Name */}
                    <div className="space-y-2">
                        <Label htmlFor="name">{t("signalSubscribe.fields.strategyName")}</Label>
                        <Input
                            id="name"
                            value={formData.name}
                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            placeholder={t("signalSubscribe.placeholders.strategyName")}
                        />
                    </div>

                    {/* Telegram Configuration */}
                    <div className="space-y-4 pt-4 border-t">
                        <div className="space-y-2">
                            <p className="text-sm font-medium">{t("signalSubscribe.telegram.title")}</p>
                            <p className="text-xs text-muted-foreground">
                                {t("signalSubscribe.telegram.subtitle")}
                            </p>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="tg_bot_token">
                                {t("signalSubscribe.telegram.botToken")} <span className="text-short">*</span>
                            </Label>
                            <Input
                                id="tg_bot_token"
                                type="password"
                                value={formData.tg_bot_token}
                                onChange={(e) => setFormData({ ...formData, tg_bot_token: e.target.value })}
                                placeholder={t("signalSubscribe.telegram.botTokenPlaceholder")}
                            />
                            <p className="text-xs text-muted-foreground">
                                {t("signalSubscribe.telegram.botTokenHint")}
                            </p>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="tg_chat_id">
                                {t("signalSubscribe.telegram.chatId")} <span className="text-short">*</span>
                            </Label>
                            <Input
                                id="tg_chat_id"
                                value={formData.tg_chat_id}
                                onChange={(e) => setFormData({ ...formData, tg_chat_id: e.target.value })}
                                placeholder={t("signalSubscribe.telegram.chatIdPlaceholder")}
                            />
                            <p className="text-xs text-muted-foreground">
                                {t("signalSubscribe.telegram.chatIdHint")}
                            </p>
                        </div>

                        <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                            <Label htmlFor="tg_signal" className="text-sm cursor-pointer">
                                {t("signalSubscribe.telegram.enableSignals")}
                            </Label>
                            <Switch
                                id="tg_signal"
                                checked={formData.tg_notify_signal}
                                onCheckedChange={(checked) => setFormData({ ...formData, tg_notify_signal: checked })}
                            />
                        </div>

                        <div className="text-xs text-muted-foreground p-3 bg-muted rounded-md">
                            {t("signalSubscribe.telegram.notice")}
                        </div>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                        {t("common.cancel")}
                    </Button>
                    <Button onClick={handleSubscribe} disabled={loading}>
                        {loading ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                {t("signalSubscribe.subscribing")}
                            </>
                        ) : (
                            <>
                                <Bell className="mr-2 h-4 w-4" />
                                {t("signalSubscribe.submit")}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
