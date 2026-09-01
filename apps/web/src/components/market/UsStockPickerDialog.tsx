import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { marketsApi } from "@/lib/api";
import type { USStockSymbol } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface UsStockPickerDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelect: (symbol: USStockSymbol) => void;
    selectedSymbol?: string;
}

const DEFAULT_LIMIT = 8000;

const UsStockPickerDialog = ({
    open,
    onOpenChange,
    onSelect,
    selectedSymbol,
}: UsStockPickerDialogProps) => {
    const { t } = useTranslation();
    const [search, setSearch] = useState("");
    const [sector, setSector] = useState("all");

    const normalizedQuery = search.trim();
    const { data: symbols = [], isLoading } = useQuery<USStockSymbol[]>({
        queryKey: ["us-stock-picker", normalizedQuery],
        queryFn: () => marketsApi.listUsStocks({ q: normalizedQuery, limit: DEFAULT_LIMIT }),
        enabled: open,
    });

    const sectors = useMemo(() => {
        const uniq = new Set<string>();
        for (const item of symbols) {
            const sec = item.sector?.trim();
            if (sec) uniq.add(sec);
        }
        return Array.from(uniq).sort((a, b) => a.localeCompare(b));
    }, [symbols]);

    const filteredSymbols = useMemo(() => {
        const needle = normalizedQuery.toLowerCase();
        return symbols.filter((item) => {
            if (sector !== "all" && item.sector !== sector) return false;
            if (!needle) return true;
            return item.symbol.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle);
        });
    }, [symbols, normalizedQuery, sector]);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[720px]">
                <DialogHeader>
                    <DialogTitle>{t("usStockPicker.title")}</DialogTitle>
                    <DialogDescription>
                        {t("usStockPicker.subtitle")}
                    </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-2">
                    <div className="grid gap-2">
                        <Label>{t("usStockPicker.searchLabel")}</Label>
                        <Input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder={t("usStockPicker.searchPlaceholder")}
                        />
                    </div>
                    <div className="grid gap-2">
                        <Label>{t("usStockPicker.sectorLabel")}</Label>
                        <Select value={sector} onValueChange={setSector}>
                            <SelectTrigger>
                                <SelectValue placeholder={t("usStockPicker.sectorPlaceholder")} />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">{t("common.all")}</SelectItem>
                                {sectors.map((sec) => (
                                    <SelectItem key={sec} value={sec}>
                                        {sec}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="border rounded-lg">
                        <ScrollArea className="h-[360px]">
                            <div className="divide-y">
                                {isLoading && (
                                    <div className="p-4 text-sm text-muted-foreground">{t("common.loading")}...</div>
                                )}
                                {!isLoading && filteredSymbols.length === 0 && (
                                    <div className="p-4 text-sm text-muted-foreground">{t("usStockPicker.noResults")}</div>
                                )}
                                {!isLoading && filteredSymbols.map((item) => (
                                    <button
                                        key={item.symbol}
                                        type="button"
                                        onClick={() => {
                                            onSelect(item);
                                            onOpenChange(false);
                                        }}
                                        className={cn(
                                            "w-full text-left px-4 py-3 hover:bg-muted transition",
                                            item.symbol === selectedSymbol && "bg-muted"
                                        )}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div className="font-medium text-sm">{item.symbol}</div>
                                            <div className="text-xs text-muted-foreground">{item.sector}</div>
                                        </div>
                                        <div className="text-xs text-muted-foreground line-clamp-1">{item.name}</div>
                                    </button>
                                ))}
                            </div>
                        </ScrollArea>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        {t("common.close")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};

export default UsStockPickerDialog;
