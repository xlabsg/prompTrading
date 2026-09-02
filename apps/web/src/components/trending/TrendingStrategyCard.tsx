import { Card, CardHeader, CardContent, CardFooter } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { ExternalLink, TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface BacktestSummary {
  total_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  profit_factor?: number;
  run_id: string;
}

export interface TrendingStrategy {
  id: string;
  source_type: "idea" | "script";
  tradingview_id: string;
  title: string;
  description: string | null;
  author: string | null;
  likes: number;
  views: number;
  comments: number;
  detected_symbols: string[];
  detected_markets: string[];
  scraped_at: string;
  trending_rank?: number;
  trending_category?: string;
  backtest_status: "pending" | "running" | "completed" | "failed";
  backtest_results?: Record<string, BacktestSummary>;
  backtest_error?: string | null;
  url: string;
  image_url?: string | null;
}

interface TrendingStrategyCardProps {
  strategy: TrendingStrategy;
  onSelect: () => void;
}

export const TrendingStrategyCard = ({
  strategy,
  onSelect,
}: TrendingStrategyCardProps) => {
  const { t } = useTranslation();
  const hasBacktest = strategy.backtest_status === "completed";
  const bestResult = hasBacktest && strategy.backtest_results
    ? Object.values(strategy.backtest_results).sort(
        (a, b) => b.total_return - a.total_return
      )[0]
    : null;

  return (
    <Card
      className="transition-colors cursor-pointer h-full flex flex-col group"
      onClick={onSelect}
    >
      {/* Strategy Image */}
      {strategy.image_url && (
        <div className="relative aspect-video overflow-hidden rounded-t-lg bg-muted">
          <img
            src={strategy.image_url}
            alt={strategy.title}
            className="w-full h-full object-cover transition-opacity group-hover:opacity-90"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
      )}

      <CardHeader className={strategy.image_url ? "pb-3" : ""}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold line-clamp-2 text-base">
              {strategy.title}
            </h3>
            <p className="text-sm text-muted-foreground truncate">
              {t("trending.byAuthor", { author: strategy.author || t("trending.unknown") })}
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1">
        <p className="text-sm text-muted-foreground line-clamp-3 mb-3 min-h-[60px]">
          {strategy.description || t("trending.noDescription")}
        </p>

        {/* Detected symbols */}
        {strategy.detected_symbols && strategy.detected_symbols.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {strategy.detected_symbols.slice(0, 3).map((symbol) => (
              <Badge key={symbol} variant="outline" className="text-xs">
                {symbol}
              </Badge>
            ))}
            {strategy.detected_symbols.length > 3 && (
              <Badge variant="outline" className="text-xs">
                +{strategy.detected_symbols.length - 3}
              </Badge>
            )}
          </div>
        )}

        {/* Metrics */}
        <div className="grid grid-cols-3 gap-2 text-sm mb-3">
          <div>
            <span className="text-muted-foreground text-xs">{t("trending.metrics.likes")}</span>
            <p className="font-medium">{strategy.likes.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-muted-foreground text-xs">{t("trending.metrics.views")}</span>
            <p className="font-medium">{strategy.views.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-muted-foreground text-xs">{t("trending.metrics.comments")}</span>
            <p className="font-medium">{strategy.comments.toLocaleString()}</p>
          </div>
        </div>

        {/* Backtest results */}
        {hasBacktest && bestResult && (
          <div className="mt-3 pt-3 border-t">
            <div className="flex items-center gap-1 mb-2">
              <TrendingUp className="h-4 w-4 text-long" />
              <span className="text-sm font-medium">{t("trending.bestResult")}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-muted-foreground text-xs">{t("trending.metrics.return")}</span>
                <p className={`font-medium ${
                  bestResult.total_return >= 0 ? "text-long" : "text-short"
                }`}>
                  {bestResult.total_return.toFixed(2)}%
                </p>
              </div>
              <div>
                <span className="text-muted-foreground text-xs">{t("trending.metrics.sharpe")}</span>
                <p className="font-medium">{bestResult.sharpe_ratio.toFixed(2)}</p>
              </div>
            </div>
          </div>
        )}

        {strategy.backtest_status === "running" && (
          <div className="mt-3 pt-3 border-t">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
              <span className="text-sm text-muted-foreground">{t("trending.backtesting")}</span>
            </div>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex justify-between pt-3 border-t">
        <Badge
          variant={
            strategy.backtest_status === "completed"
              ? "default"
              : strategy.backtest_status === "running"
              ? "secondary"
              : strategy.backtest_status === "failed"
              ? "destructive"
              : "outline"
          }
          className="capitalize"
        >
          {t(`trending.backtestStatus.${strategy.backtest_status}`)}
        </Badge>

        <Button
          variant="ghost"
          size="sm"
          asChild
          onClick={(e) => e.stopPropagation()}
        >
          <a
            href={strategy.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        </Button>
      </CardFooter>
    </Card>
  );
};
