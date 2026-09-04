import { useState } from "react";
import { MessageCircle, Check, X, Loader2, Send } from "lucide-react";
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
import { subscriptionsApi } from "@/lib/api";
import { encryptCredential } from "@/lib/encryption";
import { toast } from "sonner";
import type { TelegramStatus } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface TelegramConfigDialogProps {
    subscriptionId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: () => void;
}

export function TelegramConfigDialog({
    subscriptionId,
    open,
    onOpenChange,
    onSuccess,
}: TelegramConfigDialogProps) {
    const { t } = useTranslation();
    const [loading, setLoading] = useState(false);
    const [testing, setTesting] = useState(false);
    const [formData, setFormData] = useState({
        bot_token: "",
        chat_id: "",
        enabled: true,
        notify_on_signal: true,
        notify_on_execution: true,
        notify_on_error: true,
    });

    const handleTest = async () => {
        if (!formData.bot_token || !formData.chat_id) {
            toast.error(t("telegramConfig.errors.missingFields"));
            return;
        }

        setTesting(true);
        try {
            const encrypted = {
                bot_token_encrypted: encryptCredential(formData.bot_token),
                chat_id: formData.chat_id,
            };
            const response = await subscriptionsApi.testTelegram(subscriptionId, encrypted);
            if (response.success) {
                toast.success(t("telegramConfig.connected", { bot: response.bot_username || t("telegramConfig.botFallback") }));
            } else {
                toast.error(response.message);
            }
        } catch (error) {
            toast.error(error instanceof Error ? error.message : t("telegramConfig.errors.connectionFailed"));
        } finally {
            setTesting(false);
        }
    };

    const handleSave = async () => {
        if (!formData.bot_token || !formData.chat_id) {
            toast.error(t("telegramConfig.errors.missingFields"));
            return;
        }

        setLoading(true);
        try {
            const encrypted = {
                bot_token_encrypted: encryptCredential(formData.bot_token),
                chat_id: formData.chat_id,
                enabled: formData.enabled,
                notify_on_signal: formData.notify_on_signal,
                notify_on_execution: formData.notify_on_execution,
                notify_on_error: formData.notify_on_error,
            };
            await subscriptionsApi.updateTelegramConfig(subscriptionId, encrypted);
            toast.success(t("telegramConfig.saved"));
            onOpenChange(false);
            onSuccess?.();
        } catch (error) {
            toast.error(error instanceof Error ? error.message : t("telegramConfig.errors.saveFailed"));
        } finally {
            setLoading(false);
        }
    };

    const handleOpenChange = (newOpen: boolean) => {
        if (!newOpen) {
            setFormData({
                bot_token: "",
                chat_id: "",
                enabled: true,
                notify_on_signal: true,
                notify_on_execution: true,
                notify_on_error: true,
            });
        }
        onOpenChange(newOpen);
    };

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <MessageCircle className="h-5 w-5" />
                        {t("telegramConfig.title")}
                    </DialogTitle>
                    <DialogDescription>
                        {t("telegramConfig.subtitle")}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Bot Token */}
                    <div className="space-y-2">
                        <Label htmlFor="bot_token">{t("telegramConfig.fields.botToken")}</Label>
                        <Input
                            id="bot_token"
                            type="password"
                            value={formData.bot_token}
                            onChange={(e) =>
                                setFormData((prev) => ({ ...prev, bot_token: e.target.value }))
                            }
                            placeholder={t("telegramConfig.placeholders.botToken")}
                        />
                        <p className="text-xs text-muted-foreground">
                            {t("telegramConfig.hints.botToken")}
                        </p>
                    </div>

                    {/* Chat ID */}
                    <div className="space-y-2">
                        <Label htmlFor="chat_id">{t("telegramConfig.fields.chatId")}</Label>
                        <Input
                            id="chat_id"
                            value={formData.chat_id}
                            onChange={(e) =>
                                setFormData((prev) => ({ ...prev, chat_id: e.target.value }))
                            }
                            placeholder={t("telegramConfig.placeholders.chatId")}
                        />
                        <p className="text-xs text-muted-foreground">
                            {t("telegramConfig.hints.chatId")}
                        </p>
                    </div>

                    {/* Test Connection */}
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleTest}
                        disabled={testing || !formData.bot_token || !formData.chat_id}
                        className="w-full"
                    >
                        {testing ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                {t("telegramConfig.testing")}
                            </>
                        ) : (
                            <>
                                <Send className="mr-2 h-4 w-4" />
                                {t("telegramConfig.testConnection")}
                            </>
                        )}
                    </Button>

                    <div className="border-t pt-4 space-y-4">
                        {/* Enable Toggle */}
                        <div className="flex items-center justify-between">
                            <Label htmlFor="enabled">{t("telegramConfig.enable")}</Label>
                            <Switch
                                id="enabled"
                                checked={formData.enabled}
                                onCheckedChange={(checked) =>
                                    setFormData((prev) => ({ ...prev, enabled: checked }))
                                }
                            />
                        </div>

                        {/* Notification Types */}
                        {formData.enabled && (
                            <div className="space-y-3 pl-4 border-l-2 border-muted">
                                <div className="flex items-center justify-between">
                                    <Label htmlFor="notify_signal" className="text-sm">
                                        {t("telegramConfig.notify.signals")}
                                    </Label>
                                    <Switch
                                        id="notify_signal"
                                        checked={formData.notify_on_signal}
                                        onCheckedChange={(checked) =>
                                            setFormData((prev) => ({ ...prev, notify_on_signal: checked }))
                                        }
                                    />
                                </div>

                                <div className="flex items-center justify-between">
                                    <Label htmlFor="notify_execution" className="text-sm">
                                        {t("telegramConfig.notify.execution")}
                                    </Label>
                                    <Switch
                                        id="notify_execution"
                                        checked={formData.notify_on_execution}
                                        onCheckedChange={(checked) =>
                                            setFormData((prev) => ({ ...prev, notify_on_execution: checked }))
                                        }
                                    />
                                </div>

                                <div className="flex items-center justify-between">
                                    <Label htmlFor="notify_error" className="text-sm">
                                        {t("telegramConfig.notify.errors")}
                                    </Label>
                                    <Switch
                                        id="notify_error"
                                        checked={formData.notify_on_error}
                                        onCheckedChange={(checked) =>
                                            setFormData((prev) => ({ ...prev, notify_on_error: checked }))
                                        }
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                        {t("common.cancel")}
                    </Button>
                    <Button onClick={handleSave} disabled={loading}>
                        {loading ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                {t("telegramConfig.saving")}
                            </>
                        ) : (
                            t("telegramConfig.save")
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// Telegram Status Badge Component
export function TelegramStatusBadge({ status }: { status: TelegramStatus | null }) {
    const { t } = useTranslation();
    if (!status || !status.is_configured) {
        return (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <X size={12} />
                {t("telegramConfig.status.notConfigured")}
            </span>
        );
    }

    if (status.error) {
        return (
            <span className="flex items-center gap-1 text-xs text-red-500 bg-red-500/10 px-2 py-0.5 rounded-full">
                <X size={12} />
                {t("telegramConfig.status.error", { message: status.error.slice(0, 30) })}
            </span>
        );
    }

    return (
        <span className="flex items-center gap-1 text-xs text-green-500 bg-green-500/10 px-2 py-0.5 rounded-full">
            <Check size={12} />
            {status.is_enabled ? t("telegramConfig.status.active") : t("telegramConfig.status.paused")}
        </span>
    );
}
