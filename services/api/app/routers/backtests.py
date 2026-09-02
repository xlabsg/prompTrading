from __future__ import annotations

from collections import OrderedDict
import json
import math
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from control_plane.enums import JobStatus, JobType, StrategyRole
from control_plane.versions import create_strategy_version
from control_plane.models import BacktestRun, Dataset, Job, Strategy
from control_plane.queue import QUEUE_NAME
from control_plane.workspaces import get_run_dir, init_strategy_workspace
from app.auth import require_strategy_member
from app.deps import get_db, get_redis
from app.schemas import (
    BacktestCreateRequest,
    BacktestRunResponse,
    DatasetRequest,
    GenerateAndBacktestRequest,
    TriggerJobResponse,
)
from app.settings import settings
from app.prompt_guard import validate_prompt

router = APIRouter()

DEFAULT_US_STOCK_YEARS = 1
MAX_US_STOCK_YEARS = 5
DEFAULT_US_STOCK_MS = int(DEFAULT_US_STOCK_YEARS * 365 * 24 * 60 * 60 * 1000)
MAX_US_STOCK_MS = int(MAX_US_STOCK_YEARS * 365 * 24 * 60 * 60 * 1000)
CANDLES_CACHE_TTL_S = 30.0
CANDLES_CACHE_MAX_ENTRIES = 64
_candles_payload_cache: OrderedDict[str, dict[str, object]] = OrderedDict()


def _normalize_equity_curve_payload(base_dir: str, payload: dict) -> dict:
    """Normalize equity curve timestamps to milliseconds for frontend charting.

    Handles:
    - second-based timestamps (convert to ms)
    - legacy bad artifacts that used row index as timestamp (rebuild from equity.parquet if possible)
    """
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return payload

    timestamps: list[int] = []
    for point in data:
        if isinstance(point, dict):
            ts = point.get("timestamp")
            if isinstance(ts, (int, float)):
                timestamps.append(int(ts))

    if not timestamps:
        return payload

    max_ts = max(timestamps)

    # Legacy incorrect artifacts: timestamp was row index (very small values).
    if max_ts < 1_000_000_000:
        equity_parquet = os.path.join(base_dir, "equity.parquet")
        if os.path.isfile(equity_parquet):
            try:
                import pandas as pd

                df = pd.read_parquet(equity_parquet, columns=["timestamp", "equity", "drawdown"])
                rebuilt = [
                    {
                        "timestamp": int(row["timestamp"]),
                        "equity": round(float(row["equity"]), 2),
                        "drawdown": round(abs(float(row["drawdown"])) * 100, 2),
                    }
                    for _, row in df.iterrows()
                ]
                return {"data": rebuilt}
            except Exception:
                return payload
        return payload

    # Seconds-based timestamps -> milliseconds.
    if max_ts < 1_000_000_000_000:
        normalized = []
        for point in data:
            if not isinstance(point, dict):
                continue
            ts = point.get("timestamp")
            if isinstance(ts, (int, float)):
                next_point = dict(point)
                next_point["timestamp"] = int(ts * 1000)
                normalized.append(next_point)
            else:
                normalized.append(point)
        return {"data": normalized}

    return payload


def _normalize_ts_to_ms(raw_ts: object) -> int | None:
    if not isinstance(raw_ts, (int, float)):
        return None
    ts = int(raw_ts)
    if ts <= 0:
        return None
    if ts < 1_000_000_000:
        return None
    if ts < 1_000_000_000_000:
        return ts * 1000
    return ts


def _build_candles_payload_from_parquet(path: str) -> dict:
    import pandas as pd

    df = pd.read_parquet(path)
    required = ("timestamp", "open", "high", "low", "close")
    for col in required:
        if col not in df.columns:
            raise ValueError(f"candles_missing_column:{col}")
    df = df.sort_values("timestamp")
    volume_col = "volume" if "volume" in df.columns else ("vol" if "vol" in df.columns else None)

    data: list[dict[str, float | int]] = []
    for row in df.itertuples(index=False):
        ts = _normalize_ts_to_ms(getattr(row, "timestamp", None))
        if ts is None:
            continue
        open_v = float(getattr(row, "open"))
        high_v = float(getattr(row, "high"))
        low_v = float(getattr(row, "low"))
        close_v = float(getattr(row, "close"))
        if not all(math.isfinite(v) for v in (open_v, high_v, low_v, close_v)):
            continue
        item: dict[str, float | int] = {
            "timestamp": ts,
            "open": open_v,
            "high": high_v,
            "low": low_v,
            "close": close_v,
        }
        if volume_col:
            volume_raw = float(getattr(row, volume_col))
            if math.isfinite(volume_raw):
                item["volume"] = volume_raw
                item["vol"] = volume_raw
        data.append(item)
    return {"data": data}


def _get_cached_candles_payload(path: str) -> dict:
    now = time.time()
    mtime = os.path.getmtime(path)
    cache_key = os.path.abspath(path)
    cached = _candles_payload_cache.get(cache_key)
    if cached is not None:
        cached_mtime = float(cached.get("mtime", -1))
        cached_at = float(cached.get("loaded_at", 0))
        if cached_mtime == mtime and (now - cached_at) <= CANDLES_CACHE_TTL_S:
            _candles_payload_cache.move_to_end(cache_key)
            return cached["payload"]  # type: ignore[return-value]

    payload = _build_candles_payload_from_parquet(path)
    _candles_payload_cache[cache_key] = {"mtime": mtime, "loaded_at": now, "payload": payload}
    _candles_payload_cache.move_to_end(cache_key)
    while len(_candles_payload_cache) > CANDLES_CACHE_MAX_ENTRIES:
        _candles_payload_cache.popitem(last=False)
    return payload




def _check_no_running_job(db: Session, job_types: list[JobType], *, strategy_id: str) -> None:
    """Raise HTTPException if there's already a queued or running job for this strategy."""
    active_job = db.execute(
        select(Job)
        .where(Job.type.in_(job_types))
        .where(or_(Job.status == JobStatus.QUEUED, Job.status == JobStatus.RUNNING))
        .where(Job.payload["strategy_id"].astext == strategy_id)
        .limit(1)
    ).scalar_one_or_none()
    if active_job:
        raise HTTPException(
            status_code=409,
            detail=f"job_already_running:{active_job.id}:{active_job.type}"
        )


def _normalize_us_stock_range(dataset: DatasetRequest) -> DatasetRequest:
    if dataset.exchange != "us_stock":
        return dataset
    now_ms = int(time.time() * 1000)
    end_ms = dataset.end_ms or now_ms
    if dataset.start_ms is None:
        dataset.start_ms = end_ms - DEFAULT_US_STOCK_MS
        return dataset
    if dataset.end_ms is None:
        if (now_ms - dataset.start_ms) > MAX_US_STOCK_MS:
            dataset.end_ms = dataset.start_ms + MAX_US_STOCK_MS
        return dataset
    if end_ms < dataset.start_ms:
        raise HTTPException(status_code=400, detail="invalid_date_range")
    if (end_ms - dataset.start_ms) > MAX_US_STOCK_MS:
        raise HTTPException(status_code=400, detail="us_stock_max_duration_exceeded")
    return dataset


def _normalize_crypto_range(dataset: DatasetRequest) -> DatasetRequest:
    if dataset.exchange == "us_stock":
        return dataset
    if dataset.start_ms is not None and dataset.end_ms is None:
        dataset.end_ms = int(time.time() * 1000)
    if dataset.start_ms is not None and dataset.end_ms is not None and dataset.end_ms < dataset.start_ms:
        raise HTTPException(status_code=400, detail="invalid_date_range")
    return dataset


def _create_dataset(db: Session, dataset: DatasetRequest) -> Dataset:
    exchange = (dataset.exchange or "").strip().lower()
    if exchange not in ("binance", "okx", "us_stock"):
        raise HTTPException(status_code=400, detail="unsupported_exchange")
    symbol = (dataset.symbol or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="missing_symbol")
    interval = (dataset.interval or "").strip()
    if not interval:
        raise HTTPException(status_code=400, detail="missing_interval")
    if exchange == "us_stock" and interval != "1d":
        raise HTTPException(status_code=400, detail="us_stock_only_supports_1d")
    dataset.exchange = exchange
    dataset = _normalize_us_stock_range(dataset)
    dataset = _normalize_crypto_range(dataset)
    ds = Dataset(
        exchange=dataset.exchange,
        symbol=symbol,
        interval=interval,
        start_ms=dataset.start_ms,
        end_ms=dataset.end_ms,
    )
    db.add(ds)
    db.flush()
    return ds




@router.post("/strategies/{strategy_id}/backtests", response_model=TriggerJobResponse)
def create_backtest(
    strategy_id: str,
    req: BacktestCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> TriggerJobResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    # Concurrency check: only one backtest job at a time
    _check_no_running_job(db, [JobType.BACKTEST, JobType.GENERATE_AND_BACKTEST], strategy_id=strategy_id)

    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    init_strategy_workspace(settings.workspaces_dir, strategy_id)

    version = create_strategy_version(
        db,
        strategy_id=strategy_id,
        snapshot=True,
        workspaces_dir=settings.workspaces_dir,
    )

    ds = _create_dataset(db, req.dataset)

    run = BacktestRun(
        strategy_id=strategy_id,
        strategy_version_id=version.id,
        dataset_id=ds.id,
        job_id=None,
        run_path="",
        params=req.params or {},
    )
    db.add(run)
    db.flush()
    run.run_path = f"runs/{run.id}"

    job = Job(
        type=JobType.BACKTEST,
        status=JobStatus.QUEUED,
        payload={"strategy_id": strategy_id, "version_id": version.id, "run_id": run.id, "dataset_id": ds.id},
    )
    db.add(job)
    db.flush()
    run.job_id = job.id

    db.commit()
    rds.rpush(QUEUE_NAME, json.dumps({"job_id": job.id}))

    db.refresh(job)
    db.refresh(run)
    return TriggerJobResponse(job=job, backtest_run=run)


@router.get("/strategies/{strategy_id}/backtests", response_model=list[BacktestRunResponse])
def list_backtests(strategy_id: str, request: Request, db: Session = Depends(get_db)) -> list[BacktestRunResponse]:
    require_strategy_member(request, db, strategy_id)
    rows = (
        db.execute(select(BacktestRun).where(BacktestRun.strategy_id == strategy_id).order_by(BacktestRun.created_at.desc()))
        .scalars()
        .all()
    )
    return rows


@router.post("/strategies/{strategy_id}/generate_and_backtest", response_model=TriggerJobResponse)
def generate_and_backtest(
    strategy_id: str,
    req: GenerateAndBacktestRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> TriggerJobResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    validate_prompt(req.prompt)
    # Concurrency check: only one LLM/backtest job at a time
    _check_no_running_job(
        db,
        [JobType.BACKTEST, JobType.GENERATE_AND_BACKTEST, JobType.REFINE_STRATEGY],
        strategy_id=strategy_id,
    )

    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    init_strategy_workspace(settings.workspaces_dir, strategy_id)

    # The agent container populates versions/<id>/, so no snapshot here.
    version = create_strategy_version(
        db,
        strategy_id=strategy_id,
        prompt=req.prompt,
        llm_meta=req.llm_meta or {},
        snapshot=False,
    )

    ds = _create_dataset(db, req.dataset)

    run = BacktestRun(
        strategy_id=strategy_id,
        strategy_version_id=version.id,
        dataset_id=ds.id,
        job_id=None,
        run_path="",
        params=req.params or {},
    )
    db.add(run)
    db.flush()
    run.run_path = f"runs/{run.id}"

    job = Job(
        type=JobType.GENERATE_AND_BACKTEST,
        status=JobStatus.QUEUED,
        payload={
            "strategy_id": strategy_id,
            "version_id": version.id,
            "run_id": run.id,
            "dataset_id": ds.id,
            "prompt": req.prompt,
            "llm_meta": req.llm_meta or {},
            "params": req.params or {},
        },
    )
    db.add(job)
    db.flush()
    run.job_id = job.id

    db.commit()
    rds.rpush(QUEUE_NAME, json.dumps({"job_id": job.id}))

    db.refresh(job)
    db.refresh(run)
    return TriggerJobResponse(job=job, backtest_run=run)


@router.get("/backtests/{run_id}", response_model=BacktestRunResponse)
def get_backtest_run(run_id: str, request: Request, db: Session = Depends(get_db)) -> BacktestRunResponse:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")
    require_strategy_member(request, db, run.strategy_id)
    return run


@router.get("/strategies/{strategy_id}/backtests", response_model=list[BacktestRunResponse])
def list_backtests_for_strategy(strategy_id: str, request: Request, db: Session = Depends(get_db)) -> list[BacktestRunResponse]:
    require_strategy_member(request, db, strategy_id)
    rows = (
        db.execute(select(BacktestRun).where(BacktestRun.strategy_id == strategy_id).order_by(BacktestRun.created_at.desc()))
        .scalars()
        .all()
    )
    return rows


@router.get("/backtests/{run_id}/artifacts", response_model=list[str])
def list_backtest_artifacts(run_id: str, db: Session = Depends(get_db)) -> list[str]:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    artifacts_dir = base_dir
    try:
        return sorted([name for name in os.listdir(artifacts_dir) if not name.startswith(".")])
    except FileNotFoundError:
        return []


@router.get("/backtests/{run_id}/artifacts/{artifact_name}")
def download_backtest_artifact(run_id: str, artifact_name: str, db: Session = Depends(get_db)) -> FileResponse:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, artifact_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return FileResponse(path)


@router.get("/backtests/{run_id}/equity_curve")
def get_equity_curve(run_id: str, db: Session = Depends(get_db)):
    """Get equity curve data as JSON for interactive charting."""
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")

    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    equity_file = os.path.join(base_dir, "equity_curve.json")

    # Read the JSON file generated by the backtest worker
    if not os.path.isfile(equity_file):
        raise HTTPException(status_code=404, detail="equity_curve_not_found")

    with open(equity_file, "r") as f:
        payload = json.load(f)
    return _normalize_equity_curve_payload(base_dir, payload)


@router.get("/backtests/{run_id}/trades")
def get_trades(run_id: str, db: Session = Depends(get_db)):
    """Get trade history as JSON."""
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")

    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    trades_file = os.path.join(base_dir, "trades.json")

    # Read the JSON file generated by the backtest worker
    if not os.path.isfile(trades_file):
        raise HTTPException(status_code=404, detail="trades_not_found")

    with open(trades_file, "r") as f:
        return json.load(f)


@router.get("/backtests/{run_id}/candles")
def get_candles(run_id: str, db: Session = Depends(get_db)):
    """Get full OHLC(V) candles from backtest artifacts for board charting."""
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")

    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "candles.parquet")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="candles_not_found")

    try:
        return _get_cached_candles_payload(path)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtests/{run_id}/orders")
def get_orders(run_id: str, db: Session = Depends(get_db)):
    """Get synthesized rebalance orders as JSON.

    The vectorized engine models target weights. Orders are derived from weight transitions.
    """
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")

    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "orders.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="orders_not_found")
    with open(path, "r") as f:
        return json.load(f)


@router.get("/backtests/{run_id}/positions")
def get_positions(run_id: str, db: Session = Depends(get_db)):
    """Get position (holding period) summaries as JSON."""
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")

    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "positions.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="positions_not_found")
    with open(path, "r") as f:
        return json.load(f)


@router.get("/backtests/{run_id}/signals")
def get_signals(run_id: str, db: Session = Depends(get_db)):
    """Get serialized `generate_signals` output (bar-aligned series) as JSON."""
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")

    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "signals.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="signals_not_found")
    with open(path, "r") as f:
        return json.load(f)


@router.get("/backtests/{run_id}/signals/events")
def get_signal_events(run_id: str, db: Session = Depends(get_db)):
    """Get compact signal event list (entry/exit/rebalance/flip) as JSON."""
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")

    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "signal_events.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="signal_events_not_found")
    with open(path, "r") as f:
        return json.load(f)
