import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useTranslation } from "react-i18next";

export interface BacktestSettings {
    exchange: string;
    symbol: string;
    interval: string;
    startTime: string;
    endTime: string;
    params: string;
}

interface BacktestSettingsDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    settings: BacktestSettings;
    onSave: (settings: BacktestSettings) => void;
}

const BacktestSettingsDialog = ({
    open,
    onOpenChange,
    settings,
    onSave,
}: BacktestSettingsDialogProps) => {
    const { t } = useTranslation();
    const handleSave = () => {
        onSave(settings);
        onOpenChange(false);
    };

    const updateSetting = <K extends keyof BacktestSettings>(
        key: K,
        value: BacktestSettings[K]
    ) => {
        onSave({ ...settings, [key]: value });
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>{t("backtestSettings.title")}</DialogTitle>
                    <DialogDescription>
                        {t("backtestSettings.subtitle")}
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="exchange" className="text-right">
                            {t("backtestSettings.exchange")}
                        </Label>
                        <Select
                            value={settings.exchange}
                            onValueChange={(value) => updateSetting("exchange", value)}
                        >
                            <SelectTrigger className="col-span-3">
                                <SelectValue placeholder={t("backtestSettings.selectExchange")} />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="OKX">OKX</SelectItem>
                                <SelectItem value="Binance">Binance</SelectItem>
                                <SelectItem value="Bybit">Bybit</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="symbol" className="text-right">
                            {t("backtestSettings.symbol")}
                        </Label>
                        <Input
                            id="symbol"
                            value={settings.symbol}
                            onChange={(e) => updateSetting("symbol", e.target.value)}
                            className="col-span-3"
                            placeholder={t("backtestSettings.symbolPlaceholder")}
                        />
                    </div>

                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="interval" className="text-right">
                            {t("backtestSettings.interval")}
                        </Label>
                        <Select
                            value={settings.interval}
                            onValueChange={(value) => updateSetting("interval", value)}
                        >
                            <SelectTrigger className="col-span-3">
                                <SelectValue placeholder={t("backtestSettings.selectInterval")} />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="15m">{t("backtestSettings.intervals.m15")}</SelectItem>
                                <SelectItem value="1h">{t("backtestSettings.intervals.h1")}</SelectItem>
                                <SelectItem value="4h">{t("backtestSettings.intervals.h4")}</SelectItem>
                                <SelectItem value="1d">{t("backtestSettings.intervals.d1")}</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="startTime" className="text-right">
                            {t("backtestSettings.startTime")}
                        </Label>
                        <Input
                            id="startTime"
                            type="datetime-local"
                            value={settings.startTime}
                            onChange={(e) => updateSetting("startTime", e.target.value)}
                            className="col-span-3"
                        />
                    </div>

                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="endTime" className="text-right">
                            {t("backtestSettings.endTime")}
                        </Label>
                        <Input
                            id="endTime"
                            type="datetime-local"
                            value={settings.endTime}
                            onChange={(e) => updateSetting("endTime", e.target.value)}
                            className="col-span-3"
                        />
                    </div>

                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="params" className="text-right">
                            {t("backtestSettings.parameters")}
                        </Label>
                        <Textarea
                            id="params"
                            value={settings.params}
                            onChange={(e) => updateSetting("params", e.target.value)}
                            className="col-span-3"
                            placeholder={t("backtestSettings.parametersPlaceholder")}
                            rows={3}
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        {t("common.cancel")}
                    </Button>
                    <Button onClick={handleSave}>{t("backtestSettings.save")}</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};

export default BacktestSettingsDialog;
