import { Skeleton } from "../ui/skeleton";
import { TrendingStrategyCard, type TrendingStrategy } from "./TrendingStrategyCard";
import { useTranslation } from "react-i18next";

interface TrendingStrategyGridProps {
  strategies: TrendingStrategy[];
  isLoading: boolean;
  error?: Error | null;
  onSelect: (strategy: TrendingStrategy) => void;
}

export const TrendingStrategyGrid = ({
  strategies,
  isLoading,
  error,
  onSelect,
}: TrendingStrategyGridProps) => {
  const { t } = useTranslation();
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-3">
            <Skeleton className="h-[200px] w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">
          {t("trending.errorLoading", { message: error.message })}
        </p>
      </div>
    );
  }

  if (strategies.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground text-lg mb-2">{t("trending.emptyTitle")}</p>
        <p className="text-sm text-muted-foreground">
          {t("trending.emptySubtitle")}
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {strategies.map((strategy) => (
        <TrendingStrategyCard
          key={strategy.id}
          strategy={strategy}
          onSelect={() => onSelect(strategy)}
        />
      ))}
    </div>
  );
};
