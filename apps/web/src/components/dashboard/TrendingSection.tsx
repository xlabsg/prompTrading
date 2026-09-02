import { Card, CardHeader, CardContent } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { TrendingUp, ArrowRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { trendingApi } from "../../lib/api";
import { useNavigate } from "react-router-dom";
import type { TrendingStrategy } from "../trending/TrendingStrategyCard";
import { useTranslation } from "react-i18next";
import { TRENDING_ENABLED } from "@/lib/featureFlags";

export const TrendingSection = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();

  if (!TRENDING_ENABLED) {
    return null;
  }

  const { data, isLoading } = useQuery({
    queryKey: ["trending-preview"],
    queryFn: () =>
      trendingApi.list({
        sort_by: "scraped_at",
        limit: 3, // Only show top 3
      }),
    refetchInterval: 10 * 60 * 1000, // 10 minutes refresh
  });

  const strategies = data?.strategies || [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">{t("trendingSection.title")}</h2>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/trending")}
            className="shrink-0"
          >
            {t("trendingSection.viewAll")} <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}...</p>
        ) : strategies.length === 0 ? (
          <div className="text-center py-6">
            <TrendingUp className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              {t("trendingSection.empty")}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {strategies.map((strategy) => (
              <div
                key={strategy.id}
                className="flex items-start justify-between p-3 rounded-lg border hover:bg-muted/50 cursor-pointer transition-colors"
                onClick={() => navigate(`/trending?id=${strategy.id}`)}
              >
                <div className="flex-1 min-w-0">
                  <h4 className="font-medium text-sm line-clamp-1 mb-1">
                    {strategy.title}
                  </h4>
                  <p className="text-xs text-muted-foreground mb-1">
                    {strategy.author || t("trendingSection.unknown")} • {strategy.likes.toLocaleString()} {t("trendingSection.likes")}
                  </p>
                  {strategy.detected_symbols && strategy.detected_symbols.length > 0 && (
                    <div className="flex gap-1 flex-wrap">
                      {strategy.detected_symbols.slice(0, 2).map((symbol) => (
                        <Badge key={symbol} variant="outline" className="text-xs">
                          {symbol}
                        </Badge>
                      ))}
                      {strategy.detected_symbols.length > 2 && (
                        <Badge variant="outline" className="text-xs">
                          +{strategy.detected_symbols.length - 2}
                        </Badge>
                      )}
                    </div>
                  )}
                </div>

                <div className="ml-3 flex flex-col items-end gap-1 shrink-0">
                  {strategy.backtest_status === "completed" && (
                    <span className="text-xs text-long">{t("trendingSection.backtested")}</span>
                  )}
                  {strategy.backtest_status === "running" && (
                    <span className="text-xs text-primary">{t("trendingSection.testing")}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
