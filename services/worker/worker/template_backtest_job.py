"""
Template backtest runner

Converts builtin templates to generate_signals format and runs backtests.
"""
import os
import uuid
import shutil
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func
import redis
import docker

from control_plane.models import (
    StrategyTemplate,
    Strategy,
    StrategyVersion,
    Job,
    BacktestRun,
    Dataset,
    TemplatePerformanceRun,
    TemplateSignal,
)
from control_plane.enums import JobStatus, JobType, BacktestStatus
from worker.settings import settings

TEMPLATE_BACKTEST_MAX_RUNS = 10
TEMPLATE_BACKTEST_MAX_VERSIONS = 10

# Pre-defined generate_signals functions for builtin templates
TEMPLATE_STRATEGIES = {
    "tmpl-moving-average-crossover": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Moving Average Crossover Strategy"""
    close = data["close"]

    # Get parameters
    short_window = int(params.get("short_window", 20))
    long_window = int(params.get("long_window", 50))

    # Calculate moving averages
    short_ma = close.rolling(short_window).mean()
    long_ma = close.rolling(long_window).mean()

    long_regime = (short_ma > long_ma) & short_ma.notna() & long_ma.notna()
    short_regime = (short_ma < long_ma) & short_ma.notna() & long_ma.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))
    return {
        "target_weights": target_weights,
        "short_ma": short_ma.to_numpy(),
        "long_ma": long_ma.to_numpy(),
        "long_regime": long_regime.fillna(False).to_numpy(),
        "short_regime": short_regime.fillna(False).to_numpy(),
    }
''',

    "tmpl-rsi-oversold": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """RSI Mean Reversion Strategy"""
    close = data["close"]

    # Get parameters
    rsi_period = int(params.get("rsi_period", 14))
    oversold = float(params.get("oversold", 30))
    overbought = float(params.get("overbought", 70))

    # Calculate RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    long_regime = (rsi <= oversold) & rsi.notna()
    short_regime = (rsi >= overbought) & rsi.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))

    return {
        "target_weights": target_weights,
        "rsi": rsi.to_numpy(),
        "long_regime": long_regime.fillna(False).to_numpy(),
        "short_regime": short_regime.fillna(False).to_numpy(),
    }
''',

    "tmpl-price-breakout": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Price Breakout Strategy"""
    close = data["close"]
    high = data["high"]
    volume = data["volume"]

    lookback = int(params.get("lookback", 20))
    volume_mult = float(params.get("volume_mult", 2.0))
    trail_stop_pct = float(params.get("trail_stop_pct", 0.03))

    high_lookback = high.rolling(lookback).max()
    avg_volume = volume.rolling(lookback).mean()

    low_lookback = data["low"].rolling(lookback).min()
    breakout_up = (close > high_lookback.shift(1)) & (volume > avg_volume * volume_mult)
    breakout_down = (close < low_lookback.shift(1)) & (volume > avg_volume * volume_mult)

    target_weights = np.where(breakout_up.fillna(False), 1.0, np.where(breakout_down.fillna(False), -1.0, 0.0))
    return {
        "target_weights": target_weights,
        "breakout_up": breakout_up.fillna(False).to_numpy(),
        "breakout_down": breakout_down.fillna(False).to_numpy(),
        "high_lookback": high_lookback.to_numpy(),
        "low_lookback": low_lookback.to_numpy(),
    }
''',
    "tmpl-trend-following": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Trend Following Strategy"""
    close = data["close"]

    fast = int(params.get("fast", 50))
    slow = int(params.get("slow", 100))

    fast_ma = close.ewm(span=fast, adjust=False).mean()
    slow_ma = close.ewm(span=slow, adjust=False).mean()

    long_regime = (close > slow_ma) & (fast_ma > slow_ma) & fast_ma.notna() & slow_ma.notna()
    short_regime = (close < slow_ma) & (fast_ma < slow_ma) & fast_ma.notna() & slow_ma.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))

    return {
        "target_weights": target_weights,
        "fast_ma": fast_ma.to_numpy(),
        "slow_ma": slow_ma.to_numpy(),
        "long_regime": long_regime.fillna(False).to_numpy(),
        "short_regime": short_regime.fillna(False).to_numpy(),
    }
''',
    "tmpl-grid-trading": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Grid Trading (Range Mean Reversion)"""
    close = data["close"]

    lookback = int(params.get("lookback", 100))
    lower_pct = float(params.get("lower_pct", 0.02))
    upper_pct = float(params.get("upper_pct", 0.02))

    mid = close.rolling(lookback).mean()
    lower = mid * (1 - lower_pct)
    upper = mid * (1 + upper_pct)

    long_regime = (close <= lower) & lower.notna()
    short_regime = (close >= upper) & upper.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))

    return {
        "target_weights": target_weights,
        "mid": mid.to_numpy(),
        "lower": lower.to_numpy(),
        "upper": upper.to_numpy(),
    }
'''
,
    "tmpl-divergence": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Simplified divergence-style mean reversion with EMA + RSI guard."""
    close = data["close"]

    # Parameters with safe defaults
    ema_fast_window = int(params.get("ema_fast_window", 20))
    ema_slow_window = int(params.get("ema_slow_window", 50))
    rsi_window = int(params.get("rsi_window", 14))
    rsi_overbought_threshold = float(params.get("rsi_overbought_threshold", 70))
    stop_loss_pct = float(params.get("stop_loss_pct", 2.5))
    take_profit_pct = float(params.get("take_profit_pct", 5.0))
    trailing_stop_pct = float(params.get("trailing_stop_pct", 1.5))

    # Indicators
    ema_fast = close.ewm(span=ema_fast_window, adjust=False).mean()
    ema_slow = close.ewm(span=ema_slow_window, adjust=False).mean()

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Entry/exit base signals
    ema_cross_up = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    rsi_not_overbought = rsi < rsi_overbought_threshold
    entries = ema_cross_up & rsi_not_overbought
    exits = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

    # Convert to boolean series early for safe access
    entries_b = entries.fillna(False)

    # Risk management triggers
    stop_loss_triggers = pd.Series(False, index=close.index)
    take_profit_triggers = pd.Series(False, index=close.index)
    trailing_stop_triggers = pd.Series(False, index=close.index)
    highest_since_entry = pd.Series(np.nan, index=close.index)

    in_position = False
    entry_price = 0.0
    current_highest = 0.0

    for i in range(len(close)):
        if entries_b.iloc[i] and not in_position:
            in_position = True
            entry_price = close.iloc[i]
            current_highest = entry_price
            highest_since_entry.iloc[i] = current_highest
            continue

        if not in_position:
            highest_since_entry.iloc[i] = np.nan
            continue

        current_highest = max(current_highest, close.iloc[i])
        highest_since_entry.iloc[i] = current_highest

        stop_loss_level = entry_price * (1 - stop_loss_pct / 100)
        take_profit_level = entry_price * (1 + take_profit_pct / 100)
        trailing_stop_level = current_highest * (1 - trailing_stop_pct / 100)

        if close.iloc[i] <= stop_loss_level:
            stop_loss_triggers.iloc[i] = True
            in_position = False
        elif close.iloc[i] >= take_profit_level:
            take_profit_triggers.iloc[i] = True
            in_position = False
        elif close.iloc[i] <= trailing_stop_level:
            trailing_stop_triggers.iloc[i] = True
            in_position = False
        elif exits.iloc[i]:
            in_position = False

    all_exits = exits | stop_loss_triggers | take_profit_triggers | trailing_stop_triggers
    exits_b = all_exits.fillna(False)

    entry_reasons = []
    for entry, cross, rsi_val in zip(entries_b, ema_cross_up, rsi):
        if entry:
            entry_reasons.append(f"ema_cross_up ({ema_fast_window}/{ema_slow_window}) & rsi_{rsi_val:.1f}<{rsi_overbought_threshold}")
        else:
            entry_reasons.append("")

    exit_reasons = []
    for i, exit_signal in enumerate(exits_b):
        if exit_signal:
            if stop_loss_triggers.iloc[i]:
                exit_reasons.append(f"stop_loss_{stop_loss_pct}%")
            elif take_profit_triggers.iloc[i]:
                exit_reasons.append(f"take_profit_{take_profit_pct}%")
            elif trailing_stop_triggers.iloc[i]:
                exit_reasons.append(f"trailing_stop_{trailing_stop_pct}%")
            else:
                exit_reasons.append(f"ema_cross_down ({ema_fast_window}/{ema_slow_window})")
        else:
            exit_reasons.append("")

    target_weights = np.zeros(len(close), dtype=float)
    weight_reason = []
    position = 0.0
    for i in range(len(close)):
        reason = ""
        if bool(entries_b.iloc[i]) and position == 0.0:
            position = 1.0
            reason = entry_reasons[i]
        elif bool(exits_b.iloc[i]) and position != 0.0:
            position = 0.0
            reason = exit_reasons[i]
        target_weights[i] = position
        weight_reason.append(reason)

    return {
        "target_weights": target_weights,
        "weight_reason": weight_reason,
        "ema_fast": ema_fast.to_numpy(),
        "ema_slow": ema_slow.to_numpy(),
        "rsi": rsi.to_numpy(),
        "ema_cross_up": ema_cross_up.to_numpy(),
        "rsi_not_overbought": rsi_not_overbought.to_numpy(),
        "stop_loss_triggers": stop_loss_triggers.to_numpy(),
        "take_profit_triggers": take_profit_triggers.to_numpy(),
        "trailing_stop_triggers": trailing_stop_triggers.to_numpy(),
        "highest_since_entry": highest_since_entry.to_numpy(),
    }
'''
}


def handle_template_backtest(
    db: Session,
    rds: redis.Redis,
    docker_client: docker.DockerClient,
    job: Job,
) -> None:
    """Handle TEMPLATE_BACKTEST job."""
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"[TEMPLATE_BACKTEST] Starting job {job.id}")

    template_id = job.payload["template_id"]
    days = job.payload.get("days", 30)

    template = db.get(StrategyTemplate, template_id)
    if not template:
        raise RuntimeError(f"template_not_found: {template_id}")

    logger.info(f"[TEMPLATE_BACKTEST] Template: {template.name}, Days: {days}")

    # Get strategy code for this template
    strategy_code = TEMPLATE_STRATEGIES.get(template_id)
    if not strategy_code:
        raise RuntimeError(f"template_not_supported: {template_id}")

    logger.info(f"[TEMPLATE_BACKTEST] Using predefined strategy code")

    # Calculate date range (end 1 day ago to ensure data is available)
    end_time = datetime.now(timezone.utc) - timedelta(days=1)
    start_time = end_time - timedelta(days=days)
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    # Get trading parameters
    config = template.config_snapshot or {}
    symbol = config.get("symbols", ["BTCUSDT"])[0] if config.get("symbols") else "BTCUSDT"
    exchange = config.get("exchange", "okx")
    interval = config.get("intervals", ["1h"])[0] if config.get("intervals") else "1h"

    # Convert symbol format for OKX (BTCUSDT -> BTC-USDT)
    if exchange == "okx" and "USDT" in symbol and "-" not in symbol:
        # Convert BTCUSDT -> BTC-USDT for spot trading
        base = symbol.replace("USDT", "")
        symbol = f"{base}-USDT"
        logger.info(f"[TEMPLATE_BACKTEST] Converted symbol to OKX format: {symbol}")

    logger.info(f"[TEMPLATE_BACKTEST] Config: {exchange} {symbol} {interval}")

    # Create or reuse a persistent template backtest strategy (not user-owned)
    temp_strategy = _get_or_create_template_strategy(db, template)
    if not temp_strategy:
        raise RuntimeError(f"failed_to_create_template_strategy: {template_id}")

    logger.info(f"[TEMPLATE_BACKTEST] Template strategy: {temp_strategy.id}")

    version = _create_template_version(db, temp_strategy, template, strategy_code)
    if not version:
        raise RuntimeError(f"failed_to_create_template_version: {template_id}")

    try:
        # Run backtest
        logger.info(f"[TEMPLATE_BACKTEST] Starting backtest...")
        backtest_run = _run_backtest(
            db=db,
            rds=rds,
            docker_client=docker_client,
            job=job,
            strategy=temp_strategy,
            strategy_version_id=version.id,
            template_id=template_id,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
        )

        logger.info(f"[TEMPLATE_BACKTEST] Backtest: {backtest_run.status}")

        if backtest_run.status == BacktestStatus.SUCCEEDED:
            # Store results
            logger.info(f"[TEMPLATE_BACKTEST] Storing results...")
            _store_performance_run(
                db=db,
                template_id=template_id,
                backtest_run=backtest_run,
                exchange=exchange,
                symbol=symbol,
                interval=interval,
            )

            # Extract and store signals
            logger.info(f"[TEMPLATE_BACKTEST] Extracting signals...")
            _extract_and_store_signals(
                db=db,
                template_id=template_id,
                backtest_run=backtest_run,
            )

            logger.info("[TEMPLATE_BACKTEST] Cleaning up old template runs/versions...")
            _cleanup_template_history(
                db=db,
                template_id=template_id,
                strategy_id=temp_strategy.id,
            )

            logger.info(f"[TEMPLATE_BACKTEST] Completed successfully")

            template.updated_at = datetime.now(timezone.utc)
            db.commit()

    finally:
        logger.info(f"[TEMPLATE_BACKTEST] Finished")


def _get_or_create_template_strategy(
    db: Session,
    template: StrategyTemplate,
) -> Strategy:
    """Create or reuse a persistent strategy container for template backtests."""
    config = template.config_snapshot or {}
    if not isinstance(config, dict):
        config = {}

    strategy_id = config.get("backtest_strategy_id")
    strategy = db.get(Strategy, strategy_id) if strategy_id else None
    if strategy:
        return strategy

    strategy_id = str(uuid.uuid4())
    strategy = Strategy(
        id=strategy_id,
        name=f"[TEMPLATE-BT] {template.name}",
        chat_status="done",
    )
    db.add(strategy)
    db.flush()

    config = dict(config)
    config["backtest_strategy_id"] = strategy_id
    template.config_snapshot = config
    db.commit()

    return strategy


def _create_template_version(
    db: Session,
    strategy: Strategy,
    template: StrategyTemplate,
    code: str,
) -> StrategyVersion:
    """Create a new strategy version for template backtests."""
    cur = db.execute(
        select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_id == strategy.id)
    ).scalar()
    next_version = int(cur or 0) + 1
    version_id = str(uuid.uuid4())
    version_path = f"versions/{version_id}"

    full_version_path = os.path.join(settings.app_workspaces_dir, strategy.id, version_path)
    os.makedirs(full_version_path, exist_ok=True)

    strategy_file = os.path.join(full_version_path, "strategy.py")
    with open(strategy_file, "w") as f:
        f.write(code)

    spec_file = os.path.join(full_version_path, "strategy_spec.yaml")
    with open(spec_file, "w") as f:
        f.write(f"name: {template.name}\n")
        f.write("description: Template backtest strategy\n")

    version = StrategyVersion(
        id=version_id,
        strategy_id=strategy.id,
        version=next_version,
        workspace_path=version_path,
        prompt=template.prompt,
        llm_meta={
            "source": "template_backtest",
            "template_id": template.id,
        },
    )
    db.add(version)
    db.commit()
    return version


def _run_backtest(
    db: Session,
    rds: redis.Redis,
    docker_client: docker.DockerClient,
    job: Job,
    strategy: Strategy,
    strategy_version_id: str,
    template_id: str,
    exchange: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> BacktestRun:
    """Run backtest using existing worker infrastructure."""
    from worker.main import _run_container_and_stream_logs, _safe_mkdir, _utcnow

    # Create dataset
    dataset = Dataset(
        exchange=exchange,
        symbol=symbol,
        interval=interval,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    db.add(dataset)
    db.flush()

    # Create backtest run
    backtest_run = BacktestRun(
        strategy_id=strategy.id,
        strategy_version_id=strategy_version_id,
        dataset_id=dataset.id,
        status=BacktestStatus.QUEUED,
        run_path="",
        params={
            "template_id": template_id,
            "dataset": {
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
        },
    )
    db.add(backtest_run)
    db.flush()
    backtest_run.run_path = f"runs/{backtest_run.id}"

    # Prepare run directory
    run_dir = os.path.join(settings.app_workspaces_dir, strategy.id, "runs", backtest_run.id)
    _safe_mkdir(run_dir)

    backtest_log_path = os.path.join(run_dir, "backtest.log")

    backtest_run.status = BacktestStatus.RUNNING
    backtest_run.started_at = _utcnow()
    db.flush()

    # Run backtest container
    exit_code, tail = _run_container_and_stream_logs(
        docker_client,
        job_id=job.id,
        rds=rds,
        image=settings.worker_backtest_image,
        name=f"template-bt-{job.id}",
        command=None,
        environment={
            "STRATEGY_ID": strategy.id,
            "VERSION_ID": strategy_version_id,
            "RUN_ID": backtest_run.id,
            "WORKSPACES_DIR": "/workspaces",
            "RUN_PARAMS_JSON": "{}",
            "EXCHANGE": exchange,
            "SYMBOL": symbol,
            "INTERVAL": interval,
            "START_MS": str(start_ms),
            "END_MS": str(end_ms),
        },
        volumes={
            settings.worker_workspaces_volume: {"bind": "/workspaces", "mode": "rw"},
        },
        network=settings.worker_docker_network,
        log_file_path=backtest_log_path,
    )

    if exit_code != 0:
        backtest_run.status = BacktestStatus.FAILED
        backtest_run.finished_at = _utcnow()
        error_msg = f"exit_code={exit_code}\n--- backtest.log tail ---\n{_tail_excerpt(tail)}"
        backtest_run.error_message = error_msg
        db.flush()
        raise RuntimeError(f"backtest_failed: {error_msg}")

    # Read metrics and trades
    import json
    try:
        metrics_path = os.path.join(settings.app_workspaces_dir, strategy.id, "runs", backtest_run.id, "metrics.json")
        if os.path.isfile(metrics_path):
            with open(metrics_path, "r") as f:
                backtest_run.metrics = json.load(f)
    except Exception:
        backtest_run.metrics = {}

    # Read trades from trades.json and add to metrics
    try:
        trades_path = os.path.join(settings.app_workspaces_dir, strategy.id, "runs", backtest_run.id, "trades.json")
        if os.path.isfile(trades_path):
            with open(trades_path, "r") as f:
                trades_data = json.load(f)
                # trades.json format: {"trades": [...]}
                if "trades" in trades_data:
                    backtest_run.metrics["trades"] = trades_data["trades"]
    except Exception:
        pass  # Trades are optional

    backtest_run.status = BacktestStatus.SUCCEEDED
    backtest_run.finished_at = _utcnow()
    db.flush()

    return backtest_run


def _cleanup_template_history(
    db: Session,
    template_id: str,
    strategy_id: str,
    keep_runs: int = TEMPLATE_BACKTEST_MAX_RUNS,
    keep_versions: int = TEMPLATE_BACKTEST_MAX_VERSIONS,
) -> None:
    """Remove old template backtest runs and unused versions to limit disk/db growth."""
    runs = (
        db.execute(
            select(BacktestRun)
            .where(BacktestRun.params["template_id"].as_string() == template_id)
            .order_by(BacktestRun.created_at.desc())
        )
        .scalars()
        .all()
    )

    keep_runs = max(1, int(keep_runs))
    to_keep = runs[:keep_runs]
    to_delete = runs[keep_runs:]

    for run in to_delete:
        run_dir = os.path.join(settings.app_workspaces_dir, run.strategy_id, "runs", run.id)
        if os.path.isdir(run_dir):
            shutil.rmtree(run_dir, ignore_errors=True)
        db.delete(run)

    kept_version_ids = {r.strategy_version_id for r in to_keep if r.strategy_version_id}
    if keep_versions and len(kept_version_ids) > keep_versions:
        kept_version_ids = set(list(kept_version_ids)[:keep_versions])

    versions = (
        db.execute(select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id))
        .scalars()
        .all()
    )
    for version in versions:
        if version.id in kept_version_ids:
            continue
        version_dir = os.path.join(settings.app_workspaces_dir, strategy_id, version.workspace_path or "")
        if version_dir and os.path.isdir(version_dir):
            shutil.rmtree(version_dir, ignore_errors=True)
        db.delete(version)

    db.commit()


def _tail_excerpt(logs, max_lines: int = 50) -> str:
    """Extract tail of logs."""
    if isinstance(logs, list):
        logs = "\n".join(logs)

    if not isinstance(logs, str):
        logs = str(logs)

    lines = logs.strip().split("\n")
    if len(lines) > max_lines:
        return "... " + "\n".join(lines[-max_lines:])
    return logs


def _store_performance_run(
    db: Session,
    template_id: str,
    backtest_run: BacktestRun,
    exchange: str,
    symbol: str,
    interval: str,
):
    """Store backtest results."""
    performance_run = TemplatePerformanceRun(
        id=str(uuid.uuid4()),
        template_id=template_id,
        run_date=datetime.now(timezone.utc),
        exchange=exchange,
        symbol=symbol,
        interval=interval,
        start_ms=backtest_run.params.get("dataset", {}).get("start_ms"),
        end_ms=backtest_run.params.get("dataset", {}).get("end_ms"),
        metrics=backtest_run.metrics or {},
        status="succeeded",
    )
    db.add(performance_run)
    db.commit()


def _extract_and_store_signals(
    db: Session,
    template_id: str,
    backtest_run: BacktestRun,
):
    """Extract signals from backtest trades."""
    import logging
    logger = logging.getLogger(__name__)

    metrics = backtest_run.metrics or {}
    trades = metrics.get("trades", [])

    logger.info(f"[TEMPLATE_BACKTEST] Extracting signals: {len(trades)} trades found")
    logger.info(f"[TEMPLATE_BACKTEST] Metrics keys: {list(metrics.keys())}")

    if not trades:
        logger.info(f"[TEMPLATE_BACKTEST] No trades to extract signals from")
        return

    # Get symbol from backtest params
    symbol = backtest_run.params.get("dataset", {}).get("symbol", "BTC-USDT")

    MAX_SIGNALS = 100

    # Count existing
    existing_count = db.execute(
        select(func.count(TemplateSignal.id)).where(TemplateSignal.template_id == template_id)
    ).scalar() or 0

    slots_available = MAX_SIGNALS - existing_count

    logger.info(f"[TEMPLATE_BACKTEST] Existing signals: {existing_count}, slots available: {slots_available}")

    # Delete old signals if needed
    if slots_available < len(trades) and existing_count > 0:
        to_delete = min(existing_count, len(trades) - slots_available)
        old_signals = db.execute(
            select(TemplateSignal)
            .where(TemplateSignal.template_id == template_id)
            .order_by(TemplateSignal.created_at.asc())
            .limit(to_delete)
        ).scalars().all()
        for sig in old_signals:
            db.delete(sig)

    # Add new signals
    signals_added = 0
    trades_to_add = trades[-slots_available:] if slots_available > 0 else []

    logger.info(f"[TEMPLATE_BACKTEST] Preparing to add {len(trades_to_add)} signals")
    if trades_to_add:
        logger.info(f"[TEMPLATE_BACKTEST] First trade sample: {trades_to_add[0]}")

    try:
        for trade in trades_to_add:
            # Parse duration string (e.g., "5h", "90m", "2d") to hours
            duration_str = trade.get("duration", "0h")
            if "h" in duration_str:
                hold_duration_hours = float(duration_str.replace("h", ""))
            elif "m" in duration_str:
                hold_duration_hours = float(duration_str.replace("m", "")) / 60
            elif "d" in duration_str:
                hold_duration_hours = float(duration_str.replace("d", "")) * 24
            else:
                hold_duration_hours = 0

            # Normalize side to lowercase and ensure it's valid
            side = str(trade.get("side", "buy")).lower()
            if side not in ["buy", "sell"]:
                logger.warning(f"[TEMPLATE_BACKTEST] Invalid side '{side}', defaulting to 'buy'")
                side = "buy"

            signal = TemplateSignal(
                id=str(uuid.uuid4()),
                template_id=template_id,
                symbol=symbol,
                side=side,
                price=trade.get("entry_price", 0),
                confidence=0.75,
                status="executed",
                entry_price=trade.get("entry_price"),
                exit_price=trade.get("exit_price"),
                pnl=trade.get("return_pct"),
                hold_duration_hours=hold_duration_hours,
                created_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
            )
            db.add(signal)
            signals_added += 1

        db.commit()
        logger.info(f"[TEMPLATE_BACKTEST] Added {signals_added} signals to database")
    except Exception as e:
        logger.error(f"[TEMPLATE_BACKTEST] Error adding signals: {e}")
        db.rollback()
        raise


def _cleanup_temp_strategy(db: Session, strategy_id: str):
    """Cleanup temp strategy."""
    strategy = db.get(Strategy, strategy_id)
    if not strategy:
        return

    versions = db.execute(
        select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
    ).scalars().all()

    # Delete files
    for version in versions:
        workspace_path = os.path.join(settings.app_workspaces_dir, strategy_id)
        if os.path.exists(workspace_path):
            shutil.rmtree(workspace_path, ignore_errors=True)

    # Delete DB records
    db.delete(strategy)
    db.commit()
