"""Trending Strategies API endpoints

This router provides endpoints for scraping, listing, and managing
TradingView trending strategies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.enums import (
    JobStatus,
    JobType,
    TrendingBacktestStatus,
    TrendingSourceType,
)
from control_plane.models import Job, TradingViewTrendingStrategy, TrendingSchedule
from control_plane.queue import QUEUE_NAME
from app.deps import get_db, get_redis
from app.auth import get_current_user
from app.settings import settings

router = APIRouter()

# ============== Request/Response Schemas ==============


class TrendingScrapeRequest(BaseModel):
    """Request to trigger TradingView scraping."""

    source_types: list[TrendingSourceType] = Field(
        default=[TrendingSourceType.SCRIPT],
        description="Source types to scrape: scripts, ideas, or both",
    )
    max_count: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of strategies to scrape per source type",
    )
    auto_backtest: bool = Field(
        default=True,
        description="Whether to automatically trigger backtests for top strategies",
    )
    auto_backtest_top_n: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Number of top strategies to auto-backtest",
    )


class BacktestSummary(BaseModel):
    """Summary of backtest results for a symbol."""

    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float | None = None
    run_id: str


class TrendingStrategyResponse(BaseModel):
    """Response model for a trending strategy."""

    id: str
    source_type: TrendingSourceType
    tradingview_id: str
    title: str
    description: str | None
    author: str | None
    author_url: str | None
    likes: int
    views: int
    comments: int
    detected_symbols: list[str]
    detected_markets: list[str]
    scraped_at: datetime
    trending_rank: int | None
    trending_category: str | None
    backtest_status: TrendingBacktestStatus
    backtest_results: dict[str, BacktestSummary] | None
    backtest_error: str | None
    url: str
    image_url: str | None


class TrendingListResponse(BaseModel):
    """Response model for listing trending strategies."""

    total: int
    strategies: list[TrendingStrategyResponse]


class TrendingScrapeResponse(BaseModel):
    """Response after triggering a scrape job."""

    job_id: str
    message: str


class TrendingScheduleRequest(BaseModel):
    """Request to create/update schedule configuration."""

    enabled: bool = Field(default=True, description="Enable or disable the schedule")
    cron_expression: str = Field(default="0 */6 * * *", description="Cron expression for scheduling")
    source_types: list[TrendingSourceType] = Field(
        default=[TrendingSourceType.SCRIPT],
        description="Source types to scrape: scripts, ideas, or both",
    )
    max_count: int = Field(default=50, ge=1, le=500, description="Max strategies per source")
    auto_backtest: bool = Field(default=True, description="Auto-run backtests")
    auto_backtest_top_n: int = Field(default=15, ge=1, le=200, description="Top N strategies to backtest")


class TrendingScheduleResponse(BaseModel):
    """Response for schedule configuration."""

    id: str
    enabled: bool
    cron_expression: str
    source_types: list[str] | None
    max_count: int
    auto_backtest: bool
    auto_backtest_top_n: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TrendingImportResponse(BaseModel):
    """Response after importing a trending strategy."""

    strategy_id: str
    message: str


# ============== Helper Functions ==============


def strategy_to_dict(strategy: TradingViewTrendingStrategy) -> dict[str, Any]:
    """Convert SQLAlchemy model to dictionary."""

    def parse_backtest_results(results: dict[str, Any] | None) -> dict[str, BacktestSummary] | None:
        if not results:
            return None
        parsed = {}
        for symbol, data in results.items():
            if isinstance(data, dict):
                parsed[symbol] = BacktestSummary(**data)
        return parsed or None

    return {
        "id": strategy.id,
        "source_type": strategy.source_type,
        "tradingview_id": strategy.tradingview_id,
        "title": strategy.title,
        "description": strategy.description,
        "author": strategy.author,
        "author_url": strategy.author_url,
        "likes": strategy.likes,
        "views": strategy.views,
        "comments": strategy.comments,
        "detected_symbols": strategy.detected_symbols or [],
        "detected_markets": strategy.detected_markets or [],
        "scraped_at": strategy.scraped_at,
        "trending_rank": strategy.trending_rank,
        "trending_category": strategy.trending_category,
        "backtest_status": strategy.backtest_status,
        "backtest_results": parse_backtest_results(strategy.backtest_results),
        "backtest_error": strategy.backtest_error,
        "url": strategy.url,
        "image_url": strategy.image_url,
    }


# ============== API Endpoints ==============


@router.post("/api/trending/scrape-now", response_model=TrendingScrapeResponse)
async def trigger_scrape_now(
    req: TrendingScrapeRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds = Depends(get_redis),
) -> TrendingScrapeResponse:
    """
    Trigger a TradingView trending strategies scrape job (auth required).

    - Requires login
    - Rejects if a trending job is already queued or running
    """
    if not settings.trending_scrape_enabled:
        raise HTTPException(status_code=403, detail="trending_scrape_disabled")

    get_current_user(request, db)

    existing_job = (
        db.query(Job)
        .filter(
            Job.type.in_([JobType.TRENDING_SCRAPE.value, JobType.TRENDING_BACKTEST.value]),
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .first()
    )
    if existing_job:
        raise HTTPException(
            status_code=409,
            detail=f"Trending job already running or queued ({existing_job.type}, {existing_job.id})",
        )

    job_id = str(uuid.uuid4())

    job = Job(
        id=job_id,
        type=JobType.TRENDING_SCRAPE.value,
        payload={
            "source_types": [st.value for st in req.source_types],
            "max_count": req.max_count,
            "auto_backtest": req.auto_backtest,
            "auto_backtest_top_n": req.auto_backtest_top_n,
        },
        status="queued",
    )

    db.add(job)
    db.commit()

    import json
    rds.rpush(QUEUE_NAME, json.dumps({"job_id": job_id}))

    return TrendingScrapeResponse(
        job_id=job_id,
        message=f"Scraping job queued for {len(req.source_types)} source type(s)",
    )


@router.get("/api/trending/strategies", response_model=TrendingListResponse)
async def list_trending_strategies(
    source_type: TrendingSourceType | None = None,
    backtest_status: TrendingBacktestStatus | None = None,
    sort_by: str = "scraped_at",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> TrendingListResponse:
    """
    List trending strategies with filtering and sorting.

    - source_type: Filter by 'idea' or 'script'
    - backtest_status: Filter by backtest status
    - sort_by: Sort by 'likes' or 'scraped_at'
    - limit: Max results per page (max 100)
    - offset: Pagination offset
    """
    limit = min(limit, 100)

    query = db.query(TradingViewTrendingStrategy)

    # Optional: Filter by crypto-related strategies (disabled by default to show all)
    # query = query.filter(
    #     TradingViewTrendingStrategy.detected_markets.contains(["crypto"])
    # )

    if source_type:
        query = query.filter(TradingViewTrendingStrategy.source_type == source_type)

    if backtest_status:
        query = query.filter(TradingViewTrendingStrategy.backtest_status == backtest_status)

    # Sorting
    if sort_by == "likes":
        query = query.order_by(TradingViewTrendingStrategy.likes.desc())
    elif sort_by == "scraped_at":
        query = query.order_by(TradingViewTrendingStrategy.scraped_at.desc())
    else:
        query = query.order_by(TradingViewTrendingStrategy.scraped_at.desc())

    total = query.count()
    strategies = query.offset(offset).limit(limit).all()

    return TrendingListResponse(
        total=total,
        strategies=[TrendingStrategyResponse(**strategy_to_dict(s)) for s in strategies],
    )


@router.get("/api/trending/strategies/{strategy_id}", response_model=TrendingStrategyResponse)
async def get_trending_strategy(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> TrendingStrategyResponse:
    """Get a single trending strategy by ID."""
    strategy = db.query(TradingViewTrendingStrategy).filter_by(id=strategy_id).first()

    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    return TrendingStrategyResponse(**strategy_to_dict(strategy))


@router.post("/api/trending/strategies/{strategy_id}/import", response_model=TrendingImportResponse)
async def import_trending_strategy(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> TrendingImportResponse:
    """
    Import a trending strategy as a full Strategy.

    This creates a new Strategy record and StrategyVersion,
    using the existing TradingView import mechanism.
    """
    trending = db.query(TradingViewTrendingStrategy).filter_by(id=strategy_id).first()

    if not trending:
        raise HTTPException(status_code=404, detail="Trending strategy not found")

    # Import using existing TradingView import mechanism
    # This would call into strategies_import.py logic
    # For now, return a placeholder

    # TODO: Implement actual import logic
    # 1. Extract script_id from trending
    # 2. Call TradingView import API
    # 3. Create Strategy and StrategyVersion records
    # 4. Return new strategy_id

    raise HTTPException(
        status_code=501,
        detail="Import not yet implemented - please use TradingView import manually",
    )


@router.get("/api/trending/stats")
async def get_trending_stats(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get statistics about trending strategies."""
    total = db.query(TradingViewTrendingStrategy).count()

    crypto_count = (
        db.query(TradingViewTrendingStrategy)
        .filter(TradingViewTrendingStrategy.detected_markets.contains(["crypto"]))
        .count()
    )

    backtest_completed = (
        db.query(TradingViewTrendingStrategy)
        .filter(TradingViewTrendingStrategy.backtest_status == TrendingBacktestStatus.COMPLETED)
        .count()
    )

    backtest_pending = (
        db.query(TradingViewTrendingStrategy)
        .filter(TradingViewTrendingStrategy.backtest_status == TrendingBacktestStatus.PENDING)
        .count()
    )

    return {
        "total_strategies": total,
        "crypto_strategies": crypto_count,
        "backtest_completed": backtest_completed,
        "backtest_pending": backtest_pending,
    }


@router.post("/api/trending/schedule", response_model=TrendingScheduleResponse)
async def create_or_update_schedule(
    req: TrendingScheduleRequest,
    db: Session = Depends(get_db),
) -> TrendingScheduleResponse:
    """Create or update the trending scrape schedule."""
    if not settings.trending_scrape_enabled:
        raise HTTPException(status_code=403, detail="trending_scrape_disabled")

    schedule = db.query(TrendingSchedule).first()

    if schedule:
        schedule.enabled = req.enabled
        schedule.cron_expression = req.cron_expression
        schedule.source_types = [st.value for st in req.source_types]
        schedule.max_count = req.max_count
        schedule.auto_backtest = req.auto_backtest
        schedule.auto_backtest_top_n = req.auto_backtest_top_n
    else:
        schedule = TrendingSchedule(
            enabled=req.enabled,
            cron_expression=req.cron_expression,
            source_types=[st.value for st in req.source_types],
            max_count=req.max_count,
            auto_backtest=req.auto_backtest,
            auto_backtest_top_n=req.auto_backtest_top_n,
        )
        db.add(schedule)

    db.commit()
    db.refresh(schedule)

    return TrendingScheduleResponse(
        id=schedule.id,
        enabled=schedule.enabled,
        cron_expression=schedule.cron_expression,
        source_types=schedule.source_types,
        max_count=schedule.max_count,
        auto_backtest=schedule.auto_backtest,
        auto_backtest_top_n=schedule.auto_backtest_top_n,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.get("/api/trending/schedule", response_model=TrendingScheduleResponse | None)
async def get_schedule(
    db: Session = Depends(get_db),
) -> TrendingScheduleResponse | None:
    """Get the current schedule configuration."""
    schedule = db.query(TrendingSchedule).first()

    if not schedule:
        return None

    return TrendingScheduleResponse(
        id=schedule.id,
        enabled=schedule.enabled,
        cron_expression=schedule.cron_expression,
        source_types=schedule.source_types,
        max_count=schedule.max_count,
        auto_backtest=schedule.auto_backtest,
        auto_backtest_top_n=schedule.auto_backtest_top_n,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.delete("/api/trending/schedule")
async def delete_schedule(
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete the schedule configuration."""
    if not settings.trending_scrape_enabled:
        raise HTTPException(status_code=403, detail="trending_scrape_disabled")

    schedule = db.query(TrendingSchedule).first()

    if schedule:
        db.delete(schedule)
        db.commit()
        return {"message": "Schedule deleted successfully"}

    return {"message": "No schedule found to delete"}
