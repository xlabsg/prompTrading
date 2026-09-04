import { Tabs, TabsList, TabsTrigger } from "../ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { useTranslation } from "react-i18next";

type SourceType = "all" | "scripts" | "ideas";

interface TrendingFiltersProps {
  sourceType: SourceType;
  backtestStatus: "all" | "pending" | "completed";
  sortBy: "likes" | "scraped_at";
  onSourceTypeChange: (value: SourceType) => void;
  onBacktestStatusChange: (value: "all" | "pending" | "completed") => void;
  onSortByChange: (value: "likes" | "scraped_at") => void;
}

export const TrendingFilters = ({
  sourceType,
  backtestStatus,
  sortBy,
  onSourceTypeChange,
  onBacktestStatusChange,
  onSortByChange,
}: TrendingFiltersProps) => {
  const { t } = useTranslation();
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
      <Tabs value={sourceType} onValueChange={(value) => onSourceTypeChange(value as SourceType)} className="w-full sm:w-auto">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="all" className="flex-1 sm:flex-none">
            {t("trending.filters.all")}
          </TabsTrigger>
          <TabsTrigger value="scripts" className="flex-1 sm:flex-none">
            {t("trending.filters.scripts")}
          </TabsTrigger>
          <TabsTrigger value="ideas" className="flex-1 sm:flex-none">
            {t("trending.filters.ideas")}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <Select value={backtestStatus} onValueChange={onBacktestStatusChange}>
        <SelectTrigger className="w-full sm:w-[180px]">
          <SelectValue placeholder={t("trending.filters.backtestStatus")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("trending.filters.allStatus")}</SelectItem>
          <SelectItem value="pending">{t("trending.filters.pending")}</SelectItem>
          <SelectItem value="completed">{t("trending.filters.completed")}</SelectItem>
        </SelectContent>
      </Select>

      <Select value={sortBy} onValueChange={onSortByChange}>
        <SelectTrigger className="w-full sm:w-[180px]">
          <SelectValue placeholder={t("trending.filters.sortBy")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="likes">{t("trending.filters.mostLiked")}</SelectItem>
          <SelectItem value="scraped_at">{t("trending.filters.recentlyAdded")}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
};
