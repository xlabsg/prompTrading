import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { TrendingUp, Eye, Heart, MessageCircle, Calendar } from "lucide-react";
import { BacktestSummary } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface TrendingStrategy {
  id: string;
  source_type: "idea" | "script";
  tradingview_id: string;
  title: string;
  description: string | null;
  author: string | null;
  author_url: string | null;
  likes: number;
  views: number;
  comments: number;
  detected_symbols: string[];
  detected_markets: string[];
  scraped_at: string;
  trending_rank: number | null;
  trending_category: string | null;
  backtest_status: "pending" | "running" | "completed" | "failed";
  backtest_results: Record<string, BacktestSummary> | null;
  backtest_error: string | null;
  url: string;
  image_url: string | null;
}

interface TrendingDetailDialogProps {
  strategy: TrendingStrategy | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const TrendingDetailDialog = ({
  strategy,
  open,
  onOpenChange,
}: TrendingDetailDialogProps) => {
  if (!strategy) return null;
  const { t, i18n } = useTranslation();

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString(i18n.language.startsWith("zh") ? "zh-CN" : "en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "bg-green-500";
      case "running":
        return "bg-blue-500 animate-pulse";
      case "failed":
        return "bg-red-500";
      default:
        return "bg-muted-foreground";
    }
  };

  const hasBacktest = strategy.backtest_status === "completed" && strategy.backtest_results;
  const backtestEntries = hasBacktest ? Object.entries(strategy.backtest_results) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <Badge variant="outline" className="text-xs">
                  {t(`trending.source.${strategy.source_type}`)}
                </Badge>
                {strategy.trending_rank && (
                  <Badge variant="secondary" className="text-xs">
                    <TrendingUp className="w-3 h-3 mr-1" />
                    {t("trending.rank", { rank: strategy.trending_rank })}
                  </Badge>
                )}
                <Badge className={`text-xs text-white ${getStatusColor(strategy.backtest_status)}`}>
                  {t(`trending.backtestStatus.${strategy.backtest_status}`)}
                </Badge>
              </div>
              <DialogTitle className="text-xl pr-8">{strategy.title}</DialogTitle>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {/* Strategy Image */}
          {strategy.image_url && (
            <div className="rounded-lg overflow-hidden border">
              <img
                src={strategy.image_url}
                alt={strategy.title}
                className="w-full h-auto"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            </div>
          )}

          {/* Description */}
          {strategy.description && (
            <div>
              <h3 className="text-sm font-semibold mb-2">{t("trending.description")}</h3>
              <div className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
                {strategy.description}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <div className="flex items-center text-xs text-muted-foreground">
                <Heart className="w-3 h-3 mr-1" />
                {t("trending.metrics.likes")}
              </div>
              <div className="text-lg font-semibold">{strategy.likes}</div>
            </div>
            <div className="space-y-1">
              <div className="flex items-center text-xs text-muted-foreground">
                <Eye className="w-3 h-3 mr-1" />
                {t("trending.metrics.views")}
              </div>
              <div className="text-lg font-semibold">{strategy.views}</div>
            </div>
            <div className="space-y-1">
              <div className="flex items-center text-xs text-muted-foreground">
                <MessageCircle className="w-3 h-3 mr-1" />
                {t("trending.metrics.comments")}
              </div>
              <div className="text-lg font-semibold">{strategy.comments}</div>
            </div>
          </div>

          {/* Detected Symbols */}
          {strategy.detected_symbols && strategy.detected_symbols.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-2">{t("trending.detectedSymbols")}</h3>
              <div className="flex flex-wrap gap-2">
                {strategy.detected_symbols.map((symbol) => (
                  <Badge key={symbol} variant="outline">
                    {symbol}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Backtest Results */}
          {hasBacktest && backtestEntries.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-3">{t("trending.backtestResults")}</h3>
              <div className="space-y-3">
                {backtestEntries.map(([symbol, result]) => (
                  <div key={symbol} className="border rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <Badge variant="outline">{symbol}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {t("trending.runId", { runId: result.run_id.slice(0, 8) })}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                      <div>
                        <div className="text-xs text-muted-foreground">{t("trending.metrics.return")}</div>
                        <div className={`font-semibold ${result.total_return >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {result.total_return.toFixed(2)}%
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">{t("trending.metrics.drawdown")}</div>
                        <div className="font-semibold text-red-600">
                          {result.max_drawdown.toFixed(2)}%
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">{t("trending.metrics.sharpe")}</div>
                        <div className="font-semibold">{result.sharpe_ratio.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">{t("trending.metrics.winRate")}</div>
                        <div className="font-semibold">{result.win_rate.toFixed(1)}%</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Backtest Error */}
          {strategy.backtest_status === "failed" && strategy.backtest_error && (
            <div className="border border-red-200 bg-red-50 rounded-lg p-3">
              <h3 className="text-sm font-semibold text-red-800 mb-1">{t("trending.backtestErrorTitle")}</h3>
              <p className="text-sm text-red-600">{strategy.backtest_error}</p>
            </div>
          )}

          {/* Author & Scraped At */}
          <div className="flex items-center justify-between text-xs text-muted-foreground border-t pt-4">
            <div>
              {strategy.author && <span>{t("trending.byAuthor", { author: strategy.author })}</span>}
            </div>
            <div className="flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              {t("trending.scrapedAt", { date: formatDate(strategy.scraped_at) })}
            </div>
          </div>

          {/* Actions */}
        </div>
      </DialogContent>
    </Dialog>
  );
};
