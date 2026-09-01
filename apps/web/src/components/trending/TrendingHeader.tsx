import { Clock } from "lucide-react";
import { useTranslation } from "react-i18next";

interface TrendingHeaderProps {
  lastScrapeTime?: string;
}

export const TrendingHeader = ({
  lastScrapeTime,
}: TrendingHeaderProps) => {
  const { t, i18n } = useTranslation();
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    const rtf = new Intl.RelativeTimeFormat(i18n.language.startsWith("zh") ? "zh-CN" : "en", {
      numeric: "auto",
    });

    if (diffMins < 60) {
      return rtf.format(-diffMins, "minute");
    } else if (diffHours < 24) {
      return rtf.format(-diffHours, "hour");
    } else {
      return rtf.format(-diffDays, "day");
    }
  };

  return (
    <div className="border-b bg-background px-4 py-4 sm:px-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">{t("trending.title")}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>{t("trending.subtitle")}</span>
            {lastScrapeTime && (
              <>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {t("trending.updated", { time: formatTime(lastScrapeTime) })}
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
