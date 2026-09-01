import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingHeader } from "../components/trending/TrendingHeader";
import { TrendingFilters } from "../components/trending/TrendingFilters";
import { TrendingStrategyGrid } from "../components/trending/TrendingStrategyGrid";
import { TrendingDetailDialog } from "../components/trending/TrendingDetailDialog";
import { MainLayout } from "@/components/layout/MainLayout";
import { trendingApi } from "../lib/api";
import type { TrendingStrategy } from "../components/trending/TrendingStrategyCard";
import { TRENDING_ENABLED } from "@/lib/featureFlags";
import { Navigate } from "react-router-dom";

type SourceType = "all" | "scripts" | "ideas";
type BacktestStatus = "all" | "pending" | "completed";
type SortBy = "likes" | "scraped_at";

export const TrendingView = () => {
    if (!TRENDING_ENABLED) {
        return <Navigate to="/" replace />;
    }

    const [sourceType, setSourceType] = useState<SourceType>("all");
    const [backtestStatus, setBacktestStatus] = useState<BacktestStatus>("all");
    const [sortBy, setSortBy] = useState<SortBy>("scraped_at");
    const [selectedStrategy, setSelectedStrategy] = useState<TrendingStrategy | null>(null);
    const [isDetailOpen, setIsDetailOpen] = useState(false);

    const { data, isLoading, error } = useQuery({
        queryKey: ["trending", sourceType, backtestStatus, sortBy],
        queryFn: () =>
            trendingApi.list({
                source_type: sourceType === "all" ? undefined : sourceType,
                backtest_status: backtestStatus === "all" ? undefined : backtestStatus,
                sort_by: sortBy,
                limit: 50,
            }),
        refetchInterval: 5 * 60 * 1000, // 5 minutes auto-refresh
    });

    const strategies = data?.strategies || [];
    const lastScrapeTime = strategies.length > 0
        ? strategies[0]?.scraped_at
        : undefined;

    const handleSelectStrategy = (strategy: TrendingStrategy) => {
        setSelectedStrategy(strategy);
        setIsDetailOpen(true);
    };

    return (
        <>
            <MainLayout currentPage="trending">
                <TrendingHeader lastScrapeTime={lastScrapeTime} />

                <div className="p-4 sm:p-6">
                    <TrendingFilters
                        sourceType={sourceType}
                        backtestStatus={backtestStatus}
                        sortBy={sortBy}
                        onSourceTypeChange={setSourceType}
                        onBacktestStatusChange={setBacktestStatus}
                        onSortByChange={setSortBy}
                    />
                    <TrendingStrategyGrid
                        strategies={strategies}
                        isLoading={isLoading}
                        error={error}
                        onSelect={handleSelectStrategy}
                    />
                </div>
            </MainLayout>

            <TrendingDetailDialog
                strategy={selectedStrategy}
                open={isDetailOpen}
                onOpenChange={setIsDetailOpen}
            />
        </>
    );
};

export default TrendingView;
