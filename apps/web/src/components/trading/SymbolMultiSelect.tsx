import { useState, useMemo, useEffect } from "react";
import { Search, Check } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { tradingApi, type SymbolInfo } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface SymbolMultiSelectProps {
    value: string[];
    onChange: (symbols: string[]) => void;
    disabled?: boolean;
    maxSelections?: number;
}

export function SymbolMultiSelect({
    value,
    onChange,
    disabled = false,
    maxSelections = 10,
}: SymbolMultiSelectProps) {
    const { t } = useTranslation();
    const [search, setSearch] = useState("");
    const [allSymbols, setAllSymbols] = useState<SymbolInfo[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Fetch symbols from API on mount
    useEffect(() => {
        const fetchSymbols = async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await tradingApi.listSymbols("okx", 100);
                setAllSymbols(data.symbols);
            } catch (err) {
                console.error("Failed to fetch symbols:", err);
                setError(t("symbolMultiSelect.errors.loadSymbols"));
                // Fallback to basic symbols
                setAllSymbols([
                    { symbol: "BTC-USDT-SWAP", base_coin: "BTC", quote_coin: "USDT", contract_type: "SWAP" },
                    { symbol: "ETH-USDT-SWAP", base_coin: "ETH", quote_coin: "USDT", contract_type: "SWAP" },
                    { symbol: "SOL-USDT-SWAP", base_coin: "SOL", quote_coin: "USDT", contract_type: "SWAP" },
                ]);
            } finally {
                setLoading(false);
            }
        };

        fetchSymbols();
    }, []);

    // Filter by search
    const displaySymbols = useMemo(() => {
        if (!search) return allSymbols;

        const lowerSearch = search.toLowerCase();
        return allSymbols.filter(s =>
            s.symbol.toLowerCase().includes(lowerSearch) ||
            s.base_coin.toLowerCase().includes(lowerSearch)
        );
    }, [allSymbols, search]);

    const toggleSymbol = (symbol: string) => {
        if (value.includes(symbol)) {
            onChange(value.filter(s => s !== symbol));
        } else {
            if (value.length >= maxSelections) {
                return;
            }
            onChange([...value, symbol]);
        }
    };

    const isSelected = (symbol: string) => value.includes(symbol);
    const selectedCount = value.length;

    return (
        <div className="space-y-3">
            {/* Header with count */}
            <div className="flex items-center justify-between">
                <label className="text-sm font-medium">{t("symbolMultiSelect.title")}</label>
                <Badge variant="secondary">
                    {t("symbolMultiSelect.selectedCount", { selected: selectedCount, total: maxSelections })}
                </Badge>
            </div>

            {/* Selection panel */}
            <div className={cn(
                "border rounded-lg overflow-hidden",
                disabled && "opacity-50 pointer-events-none"
            )}>
                {/* Search bar */}
                <div className="p-3 border-b">
                    <div className="relative">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            placeholder={t("symbolMultiSelect.searchPlaceholder")}
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="pl-9"
                            disabled={loading}
                        />
                    </div>
                </div>

                {/* Symbol list */}
                <div className="max-h-64 overflow-y-auto p-2 space-y-1">
                    {loading ? (
                        <div className="text-center py-8 text-muted-foreground text-sm">
                            {t("common.loading")}...
                        </div>
                    ) : error ? (
                        <div className="text-center py-8 text-red-500 text-sm">
                            {error}
                        </div>
                    ) : displaySymbols.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground text-sm">
                            {t("symbolMultiSelect.empty")}
                        </div>
                    ) : (
                        displaySymbols.map((item) => {
                            const selected = isSelected(item.symbol);
                            return (
                                <label
                                    key={item.symbol}
                                    className={cn(
                                        "flex items-center gap-3 p-2 rounded cursor-pointer transition-colors",
                                        selected ? "bg-primary/10" : "hover:bg-muted",
                                        value.length >= maxSelections && !selected && "opacity-50"
                                    )}
                                >
                                    <Checkbox
                                        checked={selected}
                                        disabled={!selected && value.length >= maxSelections}
                                        onCheckedChange={() => toggleSymbol(item.symbol)}
                                    />
                                    <div className="flex-1">
                                        <div className="font-medium text-sm">{item.base_coin}</div>
                                        <div className="text-xs text-muted-foreground">{item.symbol}</div>
                                    </div>
                                    {selected && (
                                        <Check size={16} className="text-primary" />
                                    )}
                                </label>
                            );
                        })
                    )}
                </div>
            </div>
        </div>
    );
}
