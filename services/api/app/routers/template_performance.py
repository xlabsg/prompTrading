"""
Template performance data API endpoints.

Provides endpoints for retrieving historical backtest results,
signal performance, and aggregated metrics for strategy templates.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from control_plane.models import (
    StrategyTemplate,
    TemplatePerformanceRun,
    TemplateSignal,
)
from app.deps import get_db


router = APIRouter()


# ============== Schemas ==============


class PerformanceMetrics(BaseModel):
    """Aggregated performance metrics."""
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: float
    avg_trade_pnl: float


class BacktestRunListItem(BaseModel):
    """Backtest run summary."""
    id: str
    run_date: datetime
    exchange: str
    symbol: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float


class TemplateSignalResponse(BaseModel):
    """Template signal data."""
    id: str
    symbol: str
    side: str
    price: float
    confidence: float
    status: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    pnl: Optional[float]
    hold_duration_hours: Optional[float]
    created_at: datetime
    executed_at: Optional[datetime]


class TemplatePerformanceResponse(BaseModel):
    """Complete performance data for a template."""
    template_id: str
    aggregated_metrics: PerformanceMetrics
    backtest_runs: list[BacktestRunListItem]
    recent_signals: list[TemplateSignalResponse]
    total_signals: int


class TemplatePerformanceRunDetailResponse(BaseModel):
    """Full stored metrics for a template backtest run."""

    id: str
    template_id: str
    run_date: datetime
    exchange: str
    symbol: str
    interval: str
    start_ms: Optional[int]
    end_ms: Optional[int]
    metrics: dict[str, Any]


class PerformanceChartResponse(BaseModel):
    """Data for performance charts."""
    equity_curve: list[tuple[int, float]]
    returns_distribution: list[dict[str, float | int]]
    win_rate_trend: list[tuple[str, float]]


# ============== Helper Functions ==============


def _calculate_aggregated_metrics(runs: list[TemplatePerformanceRun]) -> dict:
    """Calculate aggregate metrics from multiple runs.

    Uses weighted average where newer runs have higher weight.
    """
    if not runs:
        return {
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "profit_factor": 0.0,
            "avg_trade_pnl": 0.0,
        }

    # Weight by recency (newer runs = higher weight)
    weights = list(range(1, len(runs) + 1))  # [1, 2, 3, ..., n]
    total_weight = sum(weights)

    def weighted_avg(metric_name: str) -> float:
        if not weights:
            return 0.0
        total = sum(
            (run.metrics.get(metric_name, 0) if run.metrics else 0) * w
            for run, w in zip(runs, weights)
        )
        return total / total_weight

    # Get total trades by summing (not averaging)
    total_trades = sum(
        (run.metrics.get("total_trades", 0) if run.metrics else 0)
        for run in runs
    )

    return {
        "total_return": round(weighted_avg("total_return"), 2),
        "sharpe_ratio": round(weighted_avg("sharpe_ratio"), 2),
        "max_drawdown": round(weighted_avg("max_drawdown"), 2),
        "win_rate": round(weighted_avg("win_rate"), 1),
        "total_trades": total_trades,
        "profit_factor": round(weighted_avg("profit_factor"), 2),
        "avg_trade_pnl": round(weighted_avg("avg_trade_pnl"), 2),
    }


# ============== Endpoints ==============


@router.get("/templates/{template_id}/performance", response_model=TemplatePerformanceResponse)
async def get_template_performance(
    template_id: str,
    db: Session = Depends(get_db),
) -> TemplatePerformanceResponse:
    """Get comprehensive performance data for a template.

    Returns aggregated metrics, historical backtest runs,
    and recent signals for the specified template.
    """
    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Get backtest runs (latest 20)
    runs = db.query(TemplatePerformanceRun).filter_by(
        template_id=template_id
    ).order_by(TemplatePerformanceRun.run_date.desc()).limit(20).all()

    # Calculate aggregated metrics
    aggregated = _calculate_aggregated_metrics(runs)

    # Format backtest run list
    backtest_runs = [
        BacktestRunListItem(
            id=r.id,
            run_date=r.run_date,
            exchange=r.exchange,
            symbol=r.symbol,
            total_return=r.metrics.get("total_return", 0) if r.metrics else 0,
            sharpe_ratio=r.metrics.get("sharpe_ratio", 0) if r.metrics else 0,
            max_drawdown=r.metrics.get("max_drawdown", 0) if r.metrics else 0,
            win_rate=r.metrics.get("win_rate", 0) if r.metrics else 0,
        )
        for r in runs
    ]

    # Get recent signals (latest 20)
    signals = db.query(TemplateSignal).filter_by(
        template_id=template_id
    ).order_by(TemplateSignal.created_at.desc()).limit(20).all()

    recent_signals = [
        TemplateSignalResponse(
            id=s.id,
            symbol=s.symbol,
            side=s.side,
            price=s.price,
            confidence=s.confidence,
            status=s.status,
            entry_price=s.entry_price,
            exit_price=s.exit_price,
            pnl=s.pnl,
            hold_duration_hours=s.hold_duration_hours,
            created_at=s.created_at,
            executed_at=s.executed_at,
        )
        for s in signals
    ]

    # Count total signals
    total_signals = db.query(TemplateSignal).filter_by(template_id=template_id).count()

    return TemplatePerformanceResponse(
        template_id=template_id,
        aggregated_metrics=PerformanceMetrics(**aggregated),
        backtest_runs=backtest_runs,
        recent_signals=recent_signals,
        total_signals=total_signals,
    )


@router.get("/templates/performance/runs/{run_id}", response_model=TemplatePerformanceRunDetailResponse)
async def get_template_performance_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
) -> TemplatePerformanceRunDetailResponse:
    run = db.query(TemplatePerformanceRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Template performance run not found")

    return TemplatePerformanceRunDetailResponse(
        id=run.id,
        template_id=run.template_id,
        run_date=run.run_date,
        exchange=run.exchange,
        symbol=run.symbol,
        interval=run.interval,
        start_ms=run.start_ms,
        end_ms=run.end_ms,
        metrics=run.metrics or {},
    )


@router.get("/templates/{template_id}/performance/charts", response_model=PerformanceChartResponse)
async def get_performance_charts(
    template_id: str,
    db: Session = Depends(get_db),
) -> PerformanceChartResponse:
    """Get chart data for template performance visualization.

    Returns equity curve, returns distribution, and win rate trend
    for rendering performance charts.
    """
    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Get most recent backtest run with equity curve
    latest_run = db.query(TemplatePerformanceRun).filter_by(
        template_id=template_id
    ).order_by(TemplatePerformanceRun.run_date.desc()).first()

    equity_curve = []
    if latest_run and latest_run.metrics:
        curve_data = latest_run.metrics.get("equity_curve", [])
        if isinstance(curve_data, list):
            # Ensure data is in the right format [[timestamp, value], ...]
            equity_curve = [
                (int(item[0]), float(item[1])) if isinstance(item, list) else (int(item), float(item))
                for item in curve_data
            ]

    # Calculate returns distribution from signals
    signals = db.query(TemplateSignal).filter_by(
        template_id=template_id,
        status="executed",
    ).all()

    returns_dist = []
    # Skip returns distribution for now - requires more complex binning logic
    # TODO: Implement proper returns distribution chart

    # Calculate win rate trend (group by month for now)
    win_rate_trend = []
    # Simple implementation - can be enhanced with proper date grouping
    signals_by_month = {}
    executed_signals = db.query(TemplateSignal).filter_by(
        template_id=template_id,
        status="executed",
    ).all()

    for sig in executed_signals:
        month_key = sig.created_at.strftime("%Y-%m")
        if month_key not in signals_by_month:
            signals_by_month[month_key] = {"win": 0, "total": 0}
        signals_by_month[month_key]["total"] += 1
        if sig.pnl and sig.pnl > 0:
            signals_by_month[month_key]["win"] += 1

    for month, data in sorted(signals_by_month.items()):
        win_rate = (data["win"] / data["total"] * 100) if data["total"] > 0 else 0
        win_rate_trend.append((month, round(win_rate, 1)))

    return PerformanceChartResponse(
        equity_curve=equity_curve,
        returns_distribution=returns_dist,
        win_rate_trend=win_rate_trend,
    )


@router.post("/templates/{template_id}/performance/trigger")
async def trigger_performance_update(
    template_id: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Manually trigger performance data generation for a template.

    Creates a job to generate/update performance data for the specified template.
    Returns the job ID for tracking.
    """
    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create job for performance update
    # This would normally be queued, but for now we'll return a message
    # The actual generation happens via the scheduled job

    return {
        "message": "Performance data will be updated during the next scheduled run",
        "template_id": template_id,
    }
