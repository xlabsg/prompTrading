import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Copy, MessageCircle, ChevronDown, ChevronUp } from "lucide-react";
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
import { SymbolMultiSelect } from "@/components/trading/SymbolMultiSelect";
import type { TemplateDetail } from "@/lib/types";
import { templatesApi } from "@/lib/api";
import { encryptCredential } from "@/lib/encryption";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

interface TradingSubscribeDialogProps {
    template: TemplateDetail | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function TradingSubscribeDialog({ template, open, onOpenChange }: TradingSubscribeDialogProps) {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [loading, setLoading] = useState(false);
    const [showTelegram, setShowTelegram] = useState(false);
    const [formData, setFormData] = useState({
        name: "",
        exchange: "okx",
        symbols: ["BTC-USDT-SWAP"],
        api_key_encrypted: "",
        api_secret_encrypted: "",
        api_passphrase_encrypted: "",
        max_position_pct: 10,
        stop_loss_pct: 5,
        // Telegram config
        tg_enabled: false,
        tg_bot_token: "",
        tg_chat_id: "",
        tg_notify_signal: true,
        tg_notify_execution: true,
        tg_notify_error: true,
    });

    const handleSubscribe = async () => {
        if (!template) return;

        setLoading(true);
        try {
            const baseData = {
                name: formData.name,
                exchange: formData.exchange,
                symbols: formData.symbols,
                api_key_encrypted: encryptCredential(formData.api_key_encrypted),
                api_secret_encrypted: encryptCredential(formData.api_secret_encrypted),
                api_passphrase_encrypted: formData.api_passphrase_encrypted
                    ? encryptCredential(formData.api_passphrase_encrypted)
                    : undefined,
                max_position_pct: formData.max_position_pct,
                stop_loss_pct: formData.stop_loss_pct,
            };

            // Add Telegram config if enabled
            const telegramConfig = formData.tg_enabled ? {
                bot_token_encrypted: encryptCredential(formData.tg_bot_token),
                chat_id: formData.tg_chat_id,
                enabled: true,
                notify_on_signal: formData.tg_notify_signal,
                notify_on_execution: formData.tg_notify_execution,
                notify_on_error: formData.tg_notify_error,
            } : undefined;

            const response = await templatesApi.subscribe(template.id, {
                ...baseData,
                telegram_config: telegramConfig,
            });
            toast.success(response.message);
            onOpenChange(false);
            navigate(`/strategy/${response.strategy_id}/backtest`);
        } catch (error) {
            toast.error(error instanceof Error ? error.message : t("tradingSubscribe.errors.subscribe"));
        } finally {
            setLoading(false);
        }
    };

    const handleOpenChange = (newOpen: boolean) => {
        if (newOpen && template) {
            setFormData((prev) => ({
                ...prev,
                name: `${template.name} (Copy)`,
            }));
        }
        if (!newOpen) {
            setShowTelegram(false);
        }
        onOpenChange(newOpen);
    };

    if (!template) return null;

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>{t("tradingSubscribe.title")}</DialogTitle>
                    <DialogDescription>
                        {t("tradingSubscribe.subtitle", { name: template.name })}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Strategy Name */}
                    <div className="space-y-2">
                        <Label htmlFor="name">{t("tradingSubscribe.fields.strategyName")}</Label>
                        <Input
                            id="name"
                            value={formData.name}
                            onChange={(e) =>
                                setFormData((prev) => ({ ...prev, name: e.target.value }))
                            }
                            placeholder={t("tradingSubscribe.placeholders.strategyName")}
                        />
                    </div>

                    {/* Exchange & Symbol */}
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="exchange">{t("tradingSubscribe.fields.exchange")}</Label>
                            <select
                                id="exchange"
                                value={formData.exchange}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, exchange: e.target.value }))
                                }
                                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                                <option value="okx">OKX</option>
                                {/* More exchanges coming soon */}
                            </select>
                        </div>
                        <SymbolMultiSelect
                            value={formData.symbols}
                            onChange={(symbols) => setFormData((prev) => ({ ...prev, symbols }))}
                            maxSelections={3}
                        />
                    </div>

                    {/* API Credentials */}
                    <div className="space-y-2">
                        <Label htmlFor="api_key">{t("tradingSubscribe.fields.apiKey")}</Label>
                        <Input
                            id="api_key"
                            type="password"
                            value={formData.api_key_encrypted}
                            onChange={(e) =>
                                setFormData((prev) => ({ ...prev, api_key_encrypted: e.target.value }))
                            }
                            placeholder={t("tradingSubscribe.placeholders.apiKey")}
                        />
                        <p className="text-xs text-muted-foreground">
                            {t("tradingSubscribe.securityNotice")}
                        </p>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="api_secret">{t("tradingSubscribe.fields.apiSecret")}</Label>
                        <Input
                            id="api_secret"
                            type="password"
                            value={formData.api_secret_encrypted}
                            onChange={(e) =>
                                setFormData((prev) => ({ ...prev, api_secret_encrypted: e.target.value }))
                            }
                            placeholder={t("tradingSubscribe.placeholders.apiSecret")}
                        />
                    </div>

                    {formData.exchange === "okx" && (
                        <div className="space-y-2">
                            <Label htmlFor="api_passphrase">{t("tradingSubscribe.fields.apiPassphrase")}</Label>
                            <Input
                                id="api_passphrase"
                                type="password"
                                value={formData.api_passphrase_encrypted}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, api_passphrase_encrypted: e.target.value }))
                                }
                                placeholder={t("tradingSubscribe.placeholders.apiPassphrase")}
                            />
                        </div>
                    )}

                    {/* Risk Settings */}
                    <div className="grid grid-cols-2 gap-4 pt-2 border-t">
                        <div className="space-y-2">
                            <Label htmlFor="max_position">{t("tradingSubscribe.fields.maxPosition")}</Label>
                            <Input
                                id="max_position"
                                type="number"
                                min={1}
                                max={100}
                                value={formData.max_position_pct}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, max_position_pct: parseFloat(e.target.value) || 10 }))
                                }
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="stop_loss">{t("tradingSubscribe.fields.stopLoss")}</Label>
                            <Input
                                id="stop_loss"
                                type="number"
                                min={0.5}
                                max={50}
                                step={0.5}
                                value={formData.stop_loss_pct}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, stop_loss_pct: parseFloat(e.target.value) || 5 }))
                                }
                            />
                        </div>
                    </div>

                    {/* Telegram Configuration */}
                    <div className="border-t pt-4">
                        <button
                            type="button"
                            onClick={() => setShowTelegram(!showTelegram)}
                            className="flex items-center justify-between w-full text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                            <span className="flex items-center gap-2">
                                <MessageCircle size={16} />
                                {t("tradingSubscribe.telegram.title")}
                            </span>
                            {showTelegram ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>

                        {showTelegram && (
                            <div className="mt-4 space-y-4 pl-6 border-l-2 border-muted">
                                <div className="flex items-center justify-between">
                                    <Label htmlFor="tg_enabled">{t("tradingSubscribe.telegram.enable")}</Label>
                                    <Switch
                                        id="tg_enabled"
                                        checked={formData.tg_enabled}
                                        onCheckedChange={(checked) =>
                                            setFormData((prev) => ({ ...prev, tg_enabled: checked }))
                                        }
                                    />
                                </div>

                                {formData.tg_enabled && (
                                    <>
                                        <div className="space-y-2">
                                            <Label htmlFor="tg_bot_token">{t("tradingSubscribe.telegram.botToken")}</Label>
                                            <Input
                                                id="tg_bot_token"
                                                type="password"
                                                value={formData.tg_bot_token}
                                                onChange={(e) =>
                                                    setFormData((prev) => ({ ...prev, tg_bot_token: e.target.value }))
                                                }
                                                placeholder={t("tradingSubscribe.telegram.botTokenPlaceholder")}
                                            />
                                            <p className="text-xs text-muted-foreground">
                                                {t("tradingSubscribe.telegram.botTokenHint")}
                                            </p>
                                        </div>

                                        <div className="space-y-2">
                                            <Label htmlFor="tg_chat_id">{t("tradingSubscribe.telegram.chatId")}</Label>
                                            <Input
                                                id="tg_chat_id"
                                                value={formData.tg_chat_id}
                                                onChange={(e) =>
                                                    setFormData((prev) => ({ ...prev, tg_chat_id: e.target.value }))
                                                }
                                                placeholder={t("tradingSubscribe.telegram.chatIdPlaceholder")}
                                            />
                                            <p className="text-xs text-muted-foreground">
                                                {t("tradingSubscribe.telegram.chatIdHint")}
                                            </p>
                                        </div>

                                        <div className="space-y-3 pt-2">
                                            <div className="flex items-center justify-between">
                                                <Label htmlFor="tg_signal" className="text-sm">{t("tradingSubscribe.telegram.signals")}</Label>
                                                <Switch
                                                    id="tg_signal"
                                                    checked={formData.tg_notify_signal}
                                                    onCheckedChange={(checked) =>
                                                        setFormData((prev) => ({ ...prev, tg_notify_signal: checked }))
                                                    }
                                                />
                                            </div>

                                            <div className="flex items-center justify-between">
                                                <Label htmlFor="tg_exec" className="text-sm">{t("tradingSubscribe.telegram.execution")}</Label>
                                                <Switch
                                                    id="tg_exec"
                                                    checked={formData.tg_notify_execution}
                                                    onCheckedChange={(checked) =>
                                                        setFormData((prev) => ({ ...prev, tg_notify_execution: checked }))
                                                    }
                                                />
                                            </div>

                                            <div className="flex items-center justify-between">
                                                <Label htmlFor="tg_error" className="text-sm">{t("tradingSubscribe.telegram.errors")}</Label>
                                                <Switch
                                                    id="tg_error"
                                                    checked={formData.tg_notify_error}
                                                    onCheckedChange={(checked) =>
                                                        setFormData((prev) => ({ ...prev, tg_notify_error: checked }))
                                                    }
                                                />
                                            </div>
                                        </div>
                                    </>
                                )}
                            </div>
                        )}
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
                                {t("tradingSubscribe.creating")}
                            </>
                        ) : (
                            <>
                                <Copy className="mr-2 h-4 w-4" />
                                {t("tradingSubscribe.submit")}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
