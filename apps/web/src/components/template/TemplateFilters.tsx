import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useTranslation } from "react-i18next";

interface TemplateFiltersProps {
    search: string;
    templateType: string;
    featured: boolean;
    sort: string;
    onSearchChange: (value: string) => void;
    onTemplateTypeChange: (value: string) => void;
    onFeaturedChange: (value: boolean) => void;
    onSortChange: (value: string) => void;
}

export function TemplateFilters({
    search,
    templateType,
    featured,
    sort,
    onSearchChange,
    onTemplateTypeChange,
    onFeaturedChange,
    onSortChange,
}: TemplateFiltersProps) {
    const { t } = useTranslation();
    return (
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4 mb-6">
            <div className="relative w-full sm:flex-1 sm:min-w-[200px] sm:max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
                <Input
                    placeholder={t("templates.searchPlaceholder")}
                    value={search}
                    onChange={(e) => onSearchChange(e.target.value)}
                    className="pl-10"
                />
            </div>

            <Select value={templateType} onValueChange={onTemplateTypeChange}>
                <SelectTrigger className="w-full sm:w-[160px]">
                    <SelectValue placeholder={t("templates.filters.allTypes")} />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="all">{t("templates.filters.allTypes")}</SelectItem>
                    <SelectItem value="builtin">{t("templates.filters.builtin")}</SelectItem>
                    <SelectItem value="tradingview">{t("templates.filters.tradingview")}</SelectItem>
                    <SelectItem value="community">{t("templates.filters.community")}</SelectItem>
                </SelectContent>
            </Select>

            <Select value={sort} onValueChange={onSortChange}>
                <SelectTrigger className="w-full sm:w-[160px]">
                    <SelectValue placeholder={t("templates.filters.sort")} />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="popular">{t("templates.filters.popular")}</SelectItem>
                    <SelectItem value="quality">{t("templates.filters.quality")}</SelectItem>
                </SelectContent>
            </Select>

            <label className="flex items-center gap-2 cursor-pointer">
                <input
                    type="checkbox"
                    checked={featured}
                    onChange={(e) => onFeaturedChange(e.target.checked)}
                    className="rounded border-input bg-background"
                />
                <span className="text-sm text-muted-foreground">{t("templates.filters.featuredOnly")}</span>
            </label>

        </div>
    );
}
