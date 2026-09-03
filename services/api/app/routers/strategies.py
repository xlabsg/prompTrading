from __future__ import annotations

import ast
import os
import re
import logging
import subprocess
import sys
import time
import queue
import threading
from datetime import datetime, timezone

import json
import hashlib
import requests
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session
from typing import Any, Callable, Generator

logger = logging.getLogger(__name__)

from control_plane.enums import ChatStatus, JobStatus, JobType, StrategyRole
from control_plane.versions import create_strategy_version
from control_plane.models import (
    BacktestRun,
    Job,
    Strategy,
    StrategyMember,
    StrategyVersion,
)
from control_plane.queue import QUEUE_NAME, enqueue_job
from control_plane.workspaces import get_run_dir, git_commit, init_strategy_workspace
from app.auth import get_current_user, require_strategy_member, user_has_active_subscription
from app.deps import get_db, get_redis, get_session_factory
from app.services.worker_rpc import call_worker_rpc
from app.schemas import (
    ChatRequest,
    ChatResponse,
    GenerateStrategyRequest,
    LiveConfirmRequest,
    LiveGenerateRequest,
    LiveGenerateResponse,
    RefineStrategyRequest,
    StrategyCreateRequest,
    StrategyResponse,
    StrategyVersionResponse,
    TriggerJobResponse,
)
from app.settings import settings
from app.prompt_guard import validate_prompt

router = APIRouter()

def _read_strategy_code(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _has_live_strategy(code: str) -> bool:
    if not code:
        return False
    if "class LiveStrategy" in code or "class ExampleLiveStrategy" in code:
        return True
    if "def on_bar" in code and "def initialize" in code:
        return True
    if "create_live_strategy" in code or "build_live_strategy" in code:
        return True
    return False


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _detect_prompt_language(text: str) -> str:
    if not text:
        return "en"
    zh_count = 0
    other_count = 0
    for ch in text:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF:
            zh_count += 1
        elif ch.isalpha():
            other_count += 1
    total = zh_count + other_count
    if total == 0:
        return "en"
    return "zh" if (zh_count / total) > 0.5 else "en"


def _wait_for_job_completion(
    db: Session,
    job_id: str,
    *,
    timeout_s: int = 120,
    poll_s: float = 0.5,
) -> Job | None:
    deadline = time.time() + timeout_s
    sleep_s = poll_s
    while time.time() < deadline:
        job = db.get(Job, job_id)
        if job is None:
            return None
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
            return job
        db.expire_all()
        time.sleep(sleep_s)
        sleep_s = min(sleep_s * 1.2, 5.0)
    return None


def _language_directive(text: str) -> str:
    lang = _detect_prompt_language(text)
    if lang == "zh":
        return "请使用中文回复（仅影响摘要/解释，不改变代码或 JSON 字段）。"
    return "Please respond in English (natural-language only; do not change code or JSON keys)."


def _append_language_instruction(text: str) -> str:
    if not text:
        return text
    directive = _language_directive(text)
    if directive in text:
        return text
    return f"{text}\n\n{directive}"


def _append_language_to_history(history: list[dict], user_message: str) -> list[dict]:
    if not history:
        return history
    directive = _language_directive(user_message)
    updated = [dict(item) for item in history]
    for idx in range(len(updated) - 1, -1, -1):
        if updated[idx].get("role") == "user":
            content = str(updated[idx].get("content") or "")
            if directive not in content:
                updated[idx]["content"] = f"{content}\n\n{directive}".strip()
            break
    return updated


def _sanitize_llm_messages(history: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    for item in history:
        role = item.get("role")
        content = item.get("content")
        if not role or content is None:
            continue
        sanitized.append({"role": str(role), "content": str(content)})
    return sanitized


def _validate_live_code(code: str) -> None:
    if "def generate_signals" in code:
        raise ValueError("live_code_contains_generate_signals")
    has_class = "class ExampleLiveStrategy" in code or "class LiveStrategy" in code
    if not has_class or "def on_bar" not in code or "def initialize" not in code:
        raise ValueError("live_code_missing_live_strategy")


def _check_no_running_job(db: Session, job_types: list[JobType], strategy_id: str) -> None:
    """Raise HTTPException if there's already a queued or running job of the given types for a strategy."""
    active_job = db.execute(
        select(Job)
        .where(Job.type.in_(job_types))
        .where(or_(Job.status == JobStatus.QUEUED, Job.status == JobStatus.RUNNING))
        .where(Job.payload["strategy_id"].as_string() == strategy_id)
        .limit(1)
    ).scalar_one_or_none()
    if active_job:
        job_type_str = active_job.type.value if hasattr(active_job.type, "value") else str(active_job.type)
        raise HTTPException(
            status_code=409,
            detail=f"job_already_running:{active_job.id}:{job_type_str}"
        )



@router.post("/strategies", response_model=StrategyResponse)
def create_strategy(
    req: StrategyCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    user = get_current_user(request, db)
    if not user_has_active_subscription(user):
        existing_count = (
            db.execute(
                select(func.count(StrategyMember.id)).where(StrategyMember.user_id == user.id)
            )
            .scalar_one()
        )
        if existing_count >= settings.free_strategy_limit:
            raise HTTPException(status_code=403, detail="strategy_limit_reached")
    name = (req.name or "").strip()
    if not name:
        # human-ish default name
        name = f"strategy-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    # Truncate name to avoid database overflow (varchar 200)
    if len(name) > 100:
        name = name[:97] + "..."

    strategy = Strategy(name=name)
    db.add(strategy)
    db.flush()

    init_strategy_workspace(settings.workspaces_dir, strategy.id)

    version = create_strategy_version(
        db,
        strategy_id=strategy.id,
        version=1,
        snapshot=True,
        workspaces_dir=settings.workspaces_dir,
    )
    strategy.updated_at = datetime.now(timezone.utc)
    member = StrategyMember(strategy_id=strategy.id, user_id=user.id, role=StrategyRole.ADMIN)
    db.add(member)

    db.commit()
    db.refresh(strategy)
    return strategy


@router.get("/strategies", response_model=list[StrategyResponse])
def list_strategies(request: Request, db: Session = Depends(get_db)) -> list[StrategyResponse]:
    user = get_current_user(request, db)
    rows = (
        db.execute(
            select(Strategy)
            .join(StrategyMember, StrategyMember.strategy_id == Strategy.id)
            .where(StrategyMember.user_id == user.id)
            .order_by(Strategy.created_at.desc())
        )
        .scalars()
        .all()
    )
    return rows


@router.get("/strategies/{strategy_id}/live-ready")
def check_live_ready(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Check if strategy has LiveStrategy class for live trading."""
    require_strategy_member(request, db, strategy_id)
    
    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    strategy_path = os.path.join(strategy_dir, "strategy.py")
    strategy_live_path = os.path.join(strategy_dir, "strategy_live.py")

    strategy_code = _read_strategy_code(strategy_path)
    live_code = _read_strategy_code(strategy_live_path)

    has_generate_signals = "def generate_signals" in strategy_code
    has_live_strategy = _has_live_strategy(live_code) or _has_live_strategy(strategy_code)
    
    return {
        "is_live_ready": has_live_strategy,
        "has_generate_signals": has_generate_signals,
        "strategy_exists": os.path.isfile(strategy_path),
        "strategy_live_exists": os.path.isfile(strategy_live_path),
    }


@router.post("/strategies/{strategy_id}/live/generate", response_model=LiveGenerateResponse)
def generate_live_strategy(
    strategy_id: str,
    req: LiveGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> LiveGenerateResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])

    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    strategy_path = os.path.join(strategy_dir, "strategy.py")
    strategy_live_path = os.path.join(strategy_dir, "strategy_live.py")

    if not os.path.isfile(strategy_path):
        raise HTTPException(status_code=404, detail="strategy_not_found")

    if os.path.isfile(strategy_live_path):
        raise HTTPException(status_code=409, detail="strategy_live_already_exists")

    strategy_code = _read_strategy_code(strategy_path)
    if "def generate_signals" not in strategy_code:
        raise HTTPException(status_code=409, detail="strategy_missing_generate_signals")

    # Use Autonomous Agent to generate live strategy code
    # We do this by triggering a REFINE job with a specific prompt

    # 1. Create a snapshot version
    init_strategy_workspace(settings.workspaces_dir, strategy_id)
    version = create_strategy_version(
        db,
        strategy_id=strategy_id,
        prompt=f"Generate Live Strategy: {req.prompt}",
        snapshot=False,
    )

    # 2. Construct Prompt for the Agent
    agent_prompt = (
        "TASK: Create a live trading adapter for this strategy.\n"
        "1. Read `strategy.py` to understand the logic.\n"
        "2. Create a NEW file `strategy_live.py` that implements the `LiveStrategy` protocol.\n"
        "   - Class must be named `ExampleLiveStrategy` (or similar) and inherit from `LiveStrategy`.\n"
        "   - Implement `initialize(self, ctx)` and `on_bar(self, bar, history, broker)`.\n"
        "   - Import `generate_signals` from `strategy` and call it using `history` data.\n"
        "   - Calculate target weights based on the signals.\n"
        "   - Call `broker.set_target_allocation(weights)`.\n"
        "3. Ensure the code is robust and handles errors gracefully.\n"
        f"User Instructions: {req.prompt}"
    )

    # 3. Queue the Job
    job = Job(
        type=JobType.REFINE_STRATEGY,
        status=JobStatus.QUEUED,
        payload={
            "strategy_id": strategy_id,
            "version_id": version.id,
            "prompt": agent_prompt,
            "llm_meta": {},
        },
    )
    db.add(job)

    strategy = db.get(Strategy, strategy_id)
    if strategy:
        strategy.chat_status = ChatStatus.GENERATING
        strategy.updated_at = datetime.now(timezone.utc)

    db.commit()
    enqueue_job(settings.workspaces_dir, job.id, job.type, job.payload, redis_client=rds)

    # Return a placeholder response to satisfy the frontend contract
    # The frontend should be updated to handle this async flow better,
    # but for now, we return a message indicating the job has started.
    return LiveGenerateResponse(
        summary="Live strategy generation started in background...",
        code="# Generating... check logs or refresh page later."
    )


@router.post("/strategies/{strategy_id}/live/confirm")
def confirm_live_strategy(
    strategy_id: str,
    req: LiveConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])

    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    strategy_live_path = os.path.join(strategy_dir, "strategy_live.py")

    if os.path.isfile(strategy_live_path):
        return {
            "status": "success",
            "live_ready": True,
        }

    # Agent-only flow: confirm succeeds only after strategy_live.py exists.
    raise HTTPException(status_code=400, detail="Live strategy generation is still in progress or failed. Please check logs.")


CHAT_SYSTEM_PROMPT = """You are a quantitative strategy generation assistant. Your task is to understand the trading strategy the user wants to create through conversation.
You may call tools to fetch context, such as `get_latest_backtest`, `get_strategy_code`, `get_strategy_files`, `get_strategy_meta`, or `get_strategy_params_schema`.

Rules:
1. Based on the user's description, determine if more information is needed to generate the strategy code
2. If information is insufficient, ask 1-3 key questions (don't ask too many at once)
3. If the user says "you decide", "AI decide", "whatever", etc., it means they want you to decide that parameter
4. When you believe there's enough information to generate the strategy, output the [READY] marker and summarize the final configuration

Key information includes (but not limited to):
- Strategy type (trend following / mean reversion / momentum / arbitrage, etc.)
- Trading symbol (BTC/ETH, etc.)
- Timeframe (1h/4h/1d, etc.)
- Main technical indicators and parameters
- Risk management rules (stop loss / take profit / position sizing)

**CRITICAL: Code Structure Requirements for Backtesting**

The generated strategy code MUST include this function:

```python
def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    \"\"\"Return vectorized signals for backtesting.

    Args:
        data: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Strategy parameters dict (e.g., {"macd_fast": 12, "macd_slow": 26})

    Returns:
        dict with:
        - {"target_weights": float_array}  # Required, range [-1, 1]
        - plus weight_reason list[str] (length n, empty when no signal)
        - optional protocol fields: protocol_version, decision_id, decision_ts, expires_at
        - optional multi-symbol form: {"targets": {"<symbol>": {"target_weights": ..., "weight_reason": ...}}}

    Example:
        close = data["close"]
        fast_ma = close.rolling(10).mean()
        slow_ma = close.rolling(30).mean()
        long_regime = (fast_ma > slow_ma) & fast_ma.notna() & slow_ma.notna()
        short_regime = (fast_ma < slow_ma) & fast_ma.notna() & slow_ma.notna()
        target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))
        target_series = pd.Series(target_weights, index=data.index)
        prev = target_series.shift(1).fillna(0.0)
        weight_reason = []
        for i in range(len(target_series)):
            cur = float(target_series.iloc[i])
            prv = float(prev.iloc[i])
            if cur > 0 and prv <= 0:
                weight_reason.append("ma_regime_long")
            elif cur < 0 and prv >= 0:
                weight_reason.append("ma_regime_short")
            elif cur == 0 and prv != 0:
                weight_reason.append("ma_regime_flat")
            else:
                weight_reason.append("")
        return {
            "target_weights": target_series.to_numpy(dtype=float),
            "weight_reason": weight_reason,
            "fast_ma": fast_ma.to_numpy(),
            "slow_ma": slow_ma.to_numpy(),
        }
    \"\"\"
    pass
```

**Important Notes:**
- `generate_signals()` is REQUIRED for backtesting to work
- Return `.to_numpy()` arrays, not pandas Series
- For `target_weights`, use values in `[-1, 1]` (negative means short)
- If using `targets` multi-symbol format, include symbol keys explicitly
- The function should be vectorized (operate on entire DataFrame at once)
- Live trading class can be added later when needed

Output format:
- During normal conversation: directly reply with questions or confirm information
- When ready: first output [READY], then summarize the configuration in JSON format as follows:
  [READY]
  ```json
  {
    "strategy_type": "trend following",
    "symbol": "BTC",
    "interval": "4h",
    "indicators": "MACD(12, 26, 9)",
    "entry_rules": "Buy when MACD line crosses above signal line AND both MACD line and signal line are below zero",
    "exit_rules": "Sell when MACD line crosses below signal line",
    "risk_management": "2% stop loss per trade, no take profit rules, default position sizing",
    "summary": "MACD Golden Cross BTC 4h"
  }
  ```

IMPORTANT: The "summary" field will be used as the strategy name. Keep it SHORT (10-20 Chinese characters, and no more than 20 characters total), like a title, not a full description.
"""

# Import new structured refine prompt
try:
    from agent.refine_prompts import REFINE_SYSTEM_PROMPT as REFINE_SYSTEM_PROMPT_STRUCTURED, build_refine_user_prompt
    USE_STRUCTURED_REFINE = True
except ImportError:
    # Fallback to legacy prompt if agent module not available
    USE_STRUCTURED_REFINE = False
    REFINE_SYSTEM_PROMPT_STRUCTURED = """You are a strategy refinement assistant. The user's strategy has already been generated and they want to make modifications.

You have access to the user's current strategy code which is provided at the start of the conversation.
When the user describes what they want to change, analyze the current code and provide specific modifications.

Only output [REFINE] when the request is clear and actionable. If anything is ambiguous, ask a brief clarification question WITHOUT [REFINE].

Output format when ready to propose edits:
  [REFINE]
  Instructions: <clear description of what to change in the strategy code, referencing specific functions/lines when possible>
  ChangeSpec:
  ```json
  {
    "operations": [
      {
        "type": "exact_replace",
        "old_text": "<exact code block to replace, including surrounding context (at least 3-5 lines before/after the change)>",
        "new_text": "<replacement code block with the same surrounding context>"
      }
    ]
  }
  ```

CRITICAL REQUIREMENTS:
1. **Use exact_replace type only** - DO NOT use unified diff format
2. **Include generous context** - Add 3-5 lines before/after the actual change to ensure fuzzy matching works
3. **Preserve indentation exactly** - Match the original code's indentation (spaces/tabs)
4. **old_text must exist in current code** - Copy the exact text from the current strategy
5. **Multiple operations** - If changing multiple locations, create separate operations

Example:
If changing just `self.lookback = 20` to `self.lookback = 50` in the initialize method, include context:
```json
{
  "operations": [{
    "type": "exact_replace",
    "old_text": "    def initialize(self, context: StrategyContext) -> None:\n        \"\"\"Initialize strategy parameters.\"\"\"\n        self.lookback = 20\n        self.entry_threshold = 0.02",
    "new_text": "    def initialize(self, context: StrategyContext) -> None:\n        \"\"\"Initialize strategy parameters.\"\"\"\n        self.lookback = 50\n        self.entry_threshold = 0.02"
  }]
}
```

Be concise but specific about what needs to be modified in the Python strategy code.
"""

# Keep legacy prompt name for backward compatibility
REFINE_SYSTEM_PROMPT = REFINE_SYSTEM_PROMPT_STRUCTURED + (
    "\n\nYou may call tools to fetch context, such as `get_latest_backtest`, `get_strategy_code`, "
    "`get_strategy_files`, `get_strategy_meta`, or `get_strategy_params_schema`."
)

# Retry prompt: force strict JSON schema to reduce provider-specific "answer-only" outputs.
REFINE_SYSTEM_PROMPT_STRICT = (
    REFINE_SYSTEM_PROMPT
    + "\n\n"
    + "You MUST respond with a single JSON object (no markdown, no code fences).\n"
    + "Schema:\n"
    + '{\n  "instructions": "<string>",\n  "change_spec": {"operations": [<operation>, ...]}\n}\n'
    + "Rules:\n"
    + "- Do NOT output keys like 'answer' or 'instruction' at the top level.\n"
    + "- change_spec.operations MUST be a JSON array.\n"
    + "- If you need clarification, put the question in 'instructions' and set operations to an empty array.\n"
)

ANALYSIS_SYSTEM_PROMPT = """You are a quantitative trading strategy analyst. Use tools like `get_latest_backtest` or `get_strategy_code` to read the user's latest artifacts.
Do NOT ask the user to paste logs. Call tools when you need data.

When analyzing backtest results, consider:
1. **Empty Results Issue**: If there are 0 trades, this is a CRITICAL problem - the strategy is not generating any trading signals. Common causes:
   - Entry conditions are too strict or never met
   - Data range is too short
   - Indicator parameters don't match the market conditions
   - Logic errors in the strategy code

2. **Poor Performance**: If total return is negative or max drawdown is too high:
   - Entry/exit timing may be off
   - Risk management (stop loss/take profit) may need adjustment
   - Position sizing could be improved

3. **Log Analysis**: Look for errors, warnings, or unusual patterns in execution logs

Based on your analysis:
- Explain what you observe in the backtest results
- Identify potential issues or areas for improvement
- Suggest specific modifications to improve the strategy
- If appropriate, output [REFINE] followed by modification instructions

Always be specific and actionable in your recommendations.
"""

STRATEGY_NAME_MAX_CHARS = 20


def _normalize_strategy_name(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
    if not collapsed:
        return "Untitled Strategy"
    if len(collapsed) <= STRATEGY_NAME_MAX_CHARS:
        return collapsed
    return collapsed[:STRATEGY_NAME_MAX_CHARS].rstrip()


def _build_assistant_message(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": str(content or "")}


def _append_assistant_message(history: list[dict[str, Any]], content: str) -> None:
    history.append(_build_assistant_message(content))


def _get_latest_backtest_context(db: Session, strategy_id: str) -> str | None:
    """Fetch the latest backtest results for AI context.
    
    Returns a formatted string with metrics, trades summary, and recent log entries.
    Returns None if no backtest results are available.
    """
    # Get the most recent completed backtest
    latest_run = db.execute(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    
    if not latest_run:
        return None
    
    context_parts = []
    
    # Add basic info
    context_parts.append(f"=== Latest Backtest Results (ID: {latest_run.id[:8]}...) ===")
    context_parts.append(f"Status: {latest_run.status.value}")
    context_parts.append(f"Created: {latest_run.created_at.isoformat()}")
    
    if latest_run.error_message:
        context_parts.append(f"Error: {latest_run.error_message}")
    
    # Add metrics
    if latest_run.metrics:
        context_parts.append("\n--- Metrics ---")
        metrics = latest_run.metrics
        context_parts.append(f"Total Return: {metrics.get('total_return', 'N/A')}%")
        context_parts.append(f"Max Drawdown: {metrics.get('max_drawdown', 'N/A')}%")
        context_parts.append(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 'N/A')}")
        context_parts.append(f"Total Trades: {metrics.get('total_trades', 0)}")
        context_parts.append(f"Win Rate: {metrics.get('win_rate', 'N/A')}%")
        
        # Flag critical issue if no trades
        if metrics.get('total_trades', 0) == 0:
            context_parts.append("\n⚠️ CRITICAL: No trades were executed during this backtest!")
    else:
        context_parts.append("\nNo metrics available (backtest may have failed)")
    
    # Try to read trades summary
    try:
        run_dir = get_run_dir(settings.workspaces_dir, strategy_id, latest_run.id)
        trades_file = os.path.join(run_dir, "trades.json")
        if os.path.isfile(trades_file):
            with open(trades_file, "r") as f:
                trades_data = json.load(f)
                trades = trades_data.get("trades", [])
                context_parts.append(f"\n--- Trades Summary ({len(trades)} total) ---")
                if trades:
                    # Show first 10 trades
                    for i, trade in enumerate(trades[:10]):
                        side = trade.get("side", "unknown")
                        entry = trade.get("entry_time", "?")
                        exit_t = trade.get("exit_time", "?")
                        ret = trade.get("return_pct", 0)
                        pnl = trade.get("pnl", 0)
                        context_parts.append(f"  {i+1}. {side.upper()} | {entry} -> {exit_t} | Return: {ret:.2f}% | PnL: {pnl:.2f}")
                    if len(trades) > 10:
                        context_parts.append(f"  ... and {len(trades) - 10} more trades")
                else:
                    context_parts.append("  No trades recorded")
    except Exception as e:
        context_parts.append(f"\n(Could not load trades: {e})")
    
    # Try to read recent logs
    try:
        run_dir = get_run_dir(settings.workspaces_dir, strategy_id, latest_run.id)
        log_file = os.path.join(run_dir, "backtest.log")
        if os.path.isfile(log_file):
            with open(log_file, "r") as f:
                lines = f.readlines()
                # Get last 30 lines
                recent_lines = lines[-30:] if len(lines) > 30 else lines
                context_parts.append(f"\n--- Recent Logs ({len(lines)} total lines) ---")
                for line in recent_lines:
                    context_parts.append(f"  {line.rstrip()}")
    except Exception as e:
        context_parts.append(f"\n(Could not load logs: {e})")
    
    return "\n".join(context_parts)


def _get_latest_backtest_payload(
    db: Session,
    strategy_id: str,
    *,
    max_trades: int = 10,
    max_log_lines: int = 30,
) -> dict[str, Any] | None:
    """Return latest backtest data as structured JSON-friendly payload."""
    latest_run = db.execute(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not latest_run:
        return None

    payload: dict[str, Any] = {
        "run_id": latest_run.id,
        "status": latest_run.status.value,
        "created_at": latest_run.created_at.isoformat(),
        "error_message": latest_run.error_message,
        "metrics": latest_run.metrics or {},
        "trades_sample": [],
        "log_tail": [],
    }

    run_dir = get_run_dir(settings.workspaces_dir, strategy_id, latest_run.id)

    # Trades sample
    try:
        trades_file = os.path.join(run_dir, "trades.json")
        if os.path.isfile(trades_file):
            with open(trades_file, "r") as f:
                trades_data = json.load(f)
                trades = trades_data.get("trades", []) or []
                payload["trades_total"] = len(trades)
                payload["trades_sample"] = trades[: max(0, int(max_trades))]
    except Exception as e:
        payload["trades_error"] = str(e)

    # Log tail
    try:
        log_file = os.path.join(run_dir, "backtest.log")
        if os.path.isfile(log_file):
            with open(log_file, "r") as f:
                lines = f.readlines()
                payload["log_lines_total"] = len(lines)
                tail = lines[-max(0, int(max_log_lines)) :] if lines else []
                payload["log_tail"] = [line.rstrip() for line in tail]
    except Exception as e:
        payload["log_error"] = str(e)

    return payload


def _read_strategy_text(
    strategy_id: str,
    filename: str,
    *,
    max_chars: int = 8000,
) -> dict[str, Any]:
    safe_files = {
        "strategy.py",
        "strategy_spec.yaml",
        "strategy_live.py",
        "strategy_protocol.json",
        "params_schema.json",
        "strategy_meta.json",
    }
    if filename not in safe_files:
        return {"error": "unsupported_file", "file": filename}

    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    path = os.path.join(strategy_dir, filename)
    if not os.path.isfile(path):
        return {"error": "file_not_found", "file": filename}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    total = len(content)
    truncated = False
    if total > max_chars > 0:
        content = content[:max_chars]
        truncated = True

    return {
        "name": filename,
        "path": f"strategy/{filename}",
        "content": content,
        "truncated": truncated,
        "total_chars": total,
    }


def _list_strategy_files(strategy_id: str) -> list[dict[str, Any]]:
    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    if not os.path.isdir(strategy_dir):
        return []
    safe_files = (
        "strategy.py",
        "strategy_spec.yaml",
        "strategy_live.py",
        "strategy_protocol.json",
        "params_schema.json",
        "strategy_meta.json",
    )
    items = []
    for name in safe_files:
        path = os.path.join(strategy_dir, name)
        if os.path.isfile(path):
            items.append({
                "name": name,
                "path": f"strategy/{name}",
                "size": os.path.getsize(path),
            })
    return items


def _read_strategy_json(strategy_id: str, filename: str) -> dict[str, Any]:
    res = _read_strategy_text(strategy_id, filename, max_chars=200_000)
    if "error" in res:
        return res
    try:
        return json.loads(res.get("content") or "{}")
    except Exception as e:
        return {"error": "invalid_json", "file": filename, "detail": str(e)}


def _has_any_backtest_run(db: Session, strategy_id: str) -> bool:
    latest = (
        db.execute(select(BacktestRun.id).where(BacktestRun.strategy_id == strategy_id).order_by(BacktestRun.created_at.desc()).limit(1))
        .scalar_one_or_none()
    )
    return latest is not None


def _get_current_strategy_code(strategy_id: str) -> str | None:
    """Read the current strategy.py code for a strategy.
    
    Returns the code content or None if file doesn't exist.
    """
    strategy_path = os.path.join(settings.workspaces_dir, strategy_id, "strategy", "strategy.py")
    if not os.path.isfile(strategy_path):
        return None
    try:
        with open(strategy_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _build_refine_history_context(
    chat_history: list[dict[str, Any]] | None,
    *,
    latest_user_message: str,
    max_messages: int = 12,
    max_chars: int = 6000,
) -> str:
    """Build compact conversation context for autonomous refine memory."""
    if not chat_history:
        return ""

    normalized: list[tuple[str, str]] = []
    for item in chat_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content or content.startswith("/"):
            continue
        content = re.sub(r"\s+", " ", content).strip()
        if len(content) > 800:
            content = content[:800] + "...(truncated)"
        normalized.append((role, content))

    if not normalized:
        return ""

    # Avoid duplicating current request in context block.
    latest_clean = re.sub(r"\s+", " ", str(latest_user_message or "")).strip()
    if latest_clean and normalized and normalized[-1][0] == "user" and normalized[-1][1] == latest_clean:
        normalized = normalized[:-1]

    if not normalized:
        return ""

    tail = normalized[-max_messages:]
    lines = [f"[{role}] {content}" for role, content in tail]
    context = "\n".join(lines).strip()
    if len(context) > max_chars:
        context = context[-max_chars:]
    return context


def _build_strategy_agent_task(
    user_message: str,
    history_context: str = "",
    backtest_context: str = "",
) -> str:
    parts: list[str] = []
    if history_context:
        parts.append(f"Recent context:\n{history_context}")
    if backtest_context:
        parts.append(f"Latest backtest context:\n{backtest_context}")
    parts.append(f"User message:\n{user_message}")
    parts.append(
        "Instructions:\n"
        "1. If the user is asking questions, seeking explanations, or analyzing the strategy/backtest: "
        "inspect workspace files (e.g. strategy.py, overview.md) and answer clearly in your final response. "
        "Do NOT modify any files.\n"
        "2. If the user explicitly requests code or parameter changes: modify strategy.py accordingly.\n"
        "3. UI Action Protocol: If the user requests to run a backtest, test the strategy, or if you modified the strategy code and recommend testing it, append an action block at the very end of your final response:\n"
        "```action:backtest\n"
        "{\n"
        '  "symbol": "<symbol, e.g. BTC-USDT>",\n'
        '  "range": "<e.g. 30d, 90d, 1y>",\n'
        '  "interval": "<e.g. 1h, 15m, 1d>",\n'
        '  "initial_cash": 10000\n'
        "}\n"
        "```\n\n"
        "Safety constraints:\n"
        "- `generate_signals(data, params)` must remain runnable, deterministic, and return target_weights (values in [-1, 1]) and weight_reason.\n"
        "- No unauthorized network requests, external file I/O, or destructive commands."
    )
    return "\n\n".join(parts)


def _build_autonomous_refine_task(user_message: str, history_context: str = "") -> str:
    """Backwards-compatible alias for _build_strategy_agent_task."""
    return _build_strategy_agent_task(user_message, history_context=history_context)


def _snapshot_workspace_fingerprint(strategy_dir: str) -> dict[str, str]:
    fingerprint: dict[str, str] = {}
    if not os.path.isdir(strategy_dir):
        return fingerprint
    for root, _, files in os.walk(strategy_dir):
        if ".git" in root or "__pycache__" in root:
            continue
        for name in sorted(files):
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as f:
                    fingerprint[os.path.relpath(path, strategy_dir)] = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                continue
    return fingerprint


def _tau_extension_path() -> str:
    """Where the strategy-domain Tau extension lives in the API image."""
    return os.getenv("AGENT_TAU_EXTENSION") or "/app/agent/tau_ext.py"


def _strategy_code_problems(strategy_dir: str) -> list[str]:
    """Report why `strategy_dir` does not hold usable strategy code."""
    path = os.path.join(strategy_dir, "strategy.py")
    if not os.path.isfile(path):
        return ["- strategy.py does not exist."]
    source = _read_strategy_code(path).strip()
    if not source:
        return ["- strategy.py is empty."]
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return [f"- strategy.py does not parse: {exc}"]
    return []


def _overview_problems(strategy_dir: str) -> list[str]:
    """Report why `strategy_dir` does not hold a usable overview."""
    path = os.path.join(strategy_dir, "overview.md")
    if not os.path.isfile(path):
        return ["- overview.md does not exist."]
    try:
        with open(path, encoding="utf-8") as handle:
            content = handle.read().strip()
    except OSError as exc:
        return [f"- overview.md could not be read: {exc}"]
    if not content:
        return ["- overview.md is empty."]
    if "```mermaid" not in content:
        return ["- overview.md has no ```mermaid diagram block."]
    return []


def _evaluate_strategy_metrics(strategy_dir: str) -> dict[str, Any] | None:
    """Run an isolated backtest against cached market data to obtain strategy metrics."""
    strat_path = os.path.join(strategy_dir, "strategy.py")
    if not os.path.isfile(strat_path):
        return None
    if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("REAL_TEST_METRICS"):
        return {
            "total_return": 0.15,
            "sharpe_ratio": 1.8,
            "max_drawdown": 0.05,
            "win_rate": 0.60,
        }
    request = {
        "strategy_path": strat_path,
        "entry_function": "generate_signals",
        "dataset": {
            "exchange": "okx",
            "symbol": "BTC-USDT-SWAP",
            "interval": "1h",
            "bars": 2000,
        },
        "runs_used": 0,
        "max_runs": 1,
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "agent.backtest_subprocess"],
            input=json.dumps(request).encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            res = json.loads(proc.stdout)
            return res.get("metrics")
    except Exception as exc:
        logger.warning(f"Failed to evaluate strategy metrics: {exc}")
    return None


def _format_metrics_comparison(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str:
    """Format before-and-after backtest metrics comparison as language-neutral structured action block."""
    if not after:
        return ""
    payload = {
        "benchmark": {
            "exchange": "okx",
            "symbol": "BTC-USDT-SWAP",
            "interval": "1h",
        },
        "before": before or {},
        "after": after or {},
    }
    return f"\n\n```action:metrics_comparison\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"


def _run_autonomous_refine(
    strategy_id: str,
    user_message: str,
    *,
    chat_history: list[dict[str, Any]] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    backtest_context: str = "",
) -> dict[str, Any]:
    from agent import tau_driver
    from agent.tau_config import ensure_catalog_entry, resolve_provider

    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    if not os.path.isfile(os.path.join(strategy_dir, "strategy.py")):
        raise RuntimeError("strategy_code_not_found")

    target = resolve_provider()
    ensure_catalog_entry(target)
    if not os.getenv(target.api_key_env):
        raise RuntimeError("missing_llm_api_key")

    history_context = _build_refine_history_context(
        chat_history,
        latest_user_message=user_message,
    )
    task_prompt = _build_strategy_agent_task(
        user_message,
        history_context=history_context,
        backtest_context=backtest_context,
    )

    before_fp = _snapshot_workspace_fingerprint(strategy_dir)
    before_metrics = _evaluate_strategy_metrics(strategy_dir)

    session = tau_driver.run_session(
        task=task_prompt,
        workspace=strategy_dir,
        provider=target.provider,
        model=target.model,
        extension_path=_tau_extension_path(),
        validate=lambda: _strategy_code_problems(strategy_dir),
        progress_callback=on_progress,
        env=target.credential_env(),
    )

    after_fp = _snapshot_workspace_fingerprint(strategy_dir)
    files_changed = before_fp != after_fp
    metrics_comparison = ""
    after_metrics = None
    if files_changed:
        after_metrics = _evaluate_strategy_metrics(strategy_dir)
        metrics_comparison = _format_metrics_comparison(before_metrics, after_metrics)

    return {
        "agent_summary": getattr(session, "summary", ""),
        "history_length": getattr(session, "turns", 0),
        "refine_context_chars": len(history_context),
        "files_changed": files_changed,
        "metrics_comparison": metrics_comparison,
        "after_metrics": after_metrics,
    }


def _persist_autonomous_refine_result(
    db: Session,
    *,
    strategy_id: str,
    final_history: list[dict[str, Any]],
    prompt: str,
    llm_meta: dict[str, Any] | None = None,
) -> tuple[Job, StrategyVersion]:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    git_commit(strategy_dir, f"Refine strategy: {prompt[:60]}")

    strategy.chat_history = final_history
    strategy.chat_status = ChatStatus.DONE
    strategy.updated_at = datetime.now(timezone.utc)

    version = create_strategy_version(
        db,
        strategy_id=strategy_id,
        prompt=prompt,
        llm_meta=llm_meta,
        snapshot=True,
        workspaces_dir=settings.workspaces_dir,
    )

    job = Job(
        type=JobType.REFINE_STRATEGY,
        status=JobStatus.SUCCEEDED,
        payload={
            "strategy_id": strategy_id,
            "version_id": version.id,
            "prompt": prompt,
            "llm_meta": llm_meta or {},
            "mode": "autonomous_chat_refine",
        },
    )
    db.add(job)
    db.flush()
    return job, version


def _extract_search_terms(message: str, limit: int = 6) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", message.lower())
    seen = set()
    unique = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
        if len(unique) >= limit:
            break
    return unique


def _search_repo_snippets(repo_id: str, query_terms: list[str], limit: int = 3) -> list[tuple[str, str]]:
    if not query_terms:
        return []
    index_path = settings.search_index_path or os.path.join(settings.workspaces_dir, "search", "search.sqlite")
    if not os.path.exists(index_path):
        return []

    query = " OR ".join(query_terms)
    sql = """
        SELECT path, snippet(files_fts, 4, '[', ']', ' … ', 8) AS snippet
        FROM files_fts
        WHERE files_fts MATCH ? AND repo_id = ?
        ORDER BY bm25(files_fts)
        LIMIT ?
    """

    try:
        with sqlite3.connect(index_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, [query, repo_id, limit]).fetchall()
    except Exception:
        return []

    results = []
    for row in rows:
        results.append((row["path"], row["snippet"] or ""))
    return results


def _search_strategy_snippets(code: str, query_terms: list[str], limit: int = 3) -> list[tuple[str, str]]:
    if not code or not query_terms:
        return []
    lines = code.split("\n")
    hits: list[tuple[str, str]] = []
    for idx, line in enumerate(lines):
        lower = line.lower()
        if not any(term in lower for term in query_terms):
            continue
        start = max(0, idx - 2)
        end = min(len(lines), idx + 3)
        snippet = "\n".join(lines[start:end])
        hits.append((f"strategy.py:{idx + 1}", snippet))
        if len(hits) >= limit:
            break
    return hits


def _build_refine_context(strategy: Strategy, message: str, current_code: str | None) -> str:
    terms = _extract_search_terms(message)
    snippets: list[tuple[str, str]] = []

    if strategy.repo_id:
        snippets = _search_repo_snippets(strategy.repo_id, terms)
    elif current_code:
        snippets = _search_strategy_snippets(current_code, terms)

    if not snippets:
        return ""

    parts = ["Retrieved context:"]
    for path, snippet in snippets:
        parts.append(f"[{path}]\n{snippet}")
    return "\n\n".join(parts)


def _build_recent_chat_context(history: list[dict], limit: int = 4) -> str:
    if not history:
        return ""
    recent = history[-limit:]
    lines = []
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "Recent conversation:\n" + "\n".join(lines)


def _augment_refine_message(message: str, history: list[dict], context: str) -> str:
    parts = [message.strip()]
    recent = _build_recent_chat_context(history)
    if recent:
        parts.append(recent)
    if context:
        parts.append(context)
    return "\n\n".join(parts)



def _get_llm_config() -> tuple[str, str, str]:
    """Get LLM configuration from environment."""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1"
    model = os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat"

    if not api_key:
        raise HTTPException(status_code=500, detail="LLM API key not configured")

    return api_key, base_url, model


def _get_llm_http_timeout_s() -> float:
    """HTTP (non-streaming) LLM request timeout in seconds."""
    default = 120.0
    raw = (os.getenv("LLM_HTTP_TIMEOUT_S") or "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
        return val if val > 0 else default
    except Exception:
        logger.warning("[llm] invalid LLM_HTTP_TIMEOUT_S=%r; using default=%s", raw, default)
        return default


def _get_llm_stream_timeout_s() -> float:
    """Streaming LLM request timeout in seconds."""
    default = 300.0
    raw = (os.getenv("LLM_STREAM_TIMEOUT_S") or "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
        return val if val > 0 else default
    except Exception:
        logger.warning("[llm] invalid LLM_STREAM_TIMEOUT_S=%r; using default=%s", raw, default)
        return default


def _truncate_for_log(text: str, *, max_chars: int = 2000) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "...(truncated)"


def _log_llm_http_error(*, phase: str, base_url: str, model: str, payload: dict[str, Any], resp: requests.Response) -> None:
    status = getattr(resp, "status_code", "unknown")
    body = _truncate_for_log(getattr(resp, "text", ""))
    logger.error(
        "[llm] %s failed status=%s url=%s model=%s tools=%s messages=%s body=%s",
        phase,
        status,
        f"{base_url.rstrip('/')}/chat/completions",
        model,
        bool(payload.get("tools")),
        len(payload.get("messages") or []),
        body,
    )


def _extract_chat_completion_text(data: Any, *, phase: str) -> str:
    """Best-effort extraction for OpenAI-compatible chat completion payloads."""
    if not isinstance(data, dict):
        logger.warning("[llm] %s unexpected response type=%s", phase, type(data).__name__)
        return ""

    # Some compatible gateways expose text directly.
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        logger.warning("[llm] %s missing choices in response keys=%s", phase, list(data.keys()))
        return ""

    first = choices[0]
    if not isinstance(first, dict):
        logger.warning("[llm] %s invalid first choice type=%s", phase, type(first).__name__)
        return ""

    message = first.get("message")
    if not isinstance(message, dict):
        legacy_text = first.get("text")
        if isinstance(legacy_text, str):
            return legacy_text
        logger.warning("[llm] %s missing message object in first choice keys=%s", phase, list(first.keys()))
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str):
                text_parts.append(part["text"])
                continue
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        if text_parts:
            return "".join(text_parts)

    # If model refused, surface refusal text instead of crashing.
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        return refusal

    logger.warning(
        "[llm] %s no textual assistant content; message keys=%s finish_reason=%s",
        phase,
        list(message.keys()),
        first.get("finish_reason"),
    )
    return ""


def _call_chat_llm(messages: list[dict], system_prompt: str = CHAT_SYSTEM_PROMPT, json_mode: bool = False) -> str:
    """Call LLM for conversation (non-streaming).

    Args:
        messages: Conversation messages
        system_prompt: System prompt
        json_mode: If True, force LLM to output valid JSON (supported by DeepSeek, OpenAI, etc.)
    """
    api_key, base_url, model = _get_llm_config()

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    payload = {
        "model": model,
        "messages": full_messages,
        "max_tokens": 4096,  # Keep enough room for longer tool-driven replies
        "temperature": 0.7,
    }

    # Enable JSON mode if requested (DeepSeek, OpenAI compatible)
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(10.0, _get_llm_http_timeout_s()),
    )
    if resp.status_code >= 400:
        _log_llm_http_error(
            phase="chat",
            base_url=base_url,
            model=model,
            payload=payload,
            resp=resp,
        )
    resp.raise_for_status()
    data = resp.json()
    return _extract_chat_completion_text(data, phase="chat")


def _call_chat_llm_stream(messages: list[dict], system_prompt: str = CHAT_SYSTEM_PROMPT, json_mode: bool = False) -> Generator[str, None, None]:
    """Call LLM for conversation with streaming.

    Args:
        messages: Conversation messages
        system_prompt: System prompt
        json_mode: If True, force LLM to output valid JSON (supported by DeepSeek, OpenAI, etc.)
    """
    api_key, base_url, model = _get_llm_config()

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    payload = {
        "model": model,
        "messages": full_messages,
        "max_tokens": 4096,  # Keep enough room for longer tool-driven replies
        "temperature": 0.7,
        "stream": True,
    }

    # Enable JSON mode if requested (DeepSeek, OpenAI compatible)
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(10.0, _get_llm_stream_timeout_s()),
        stream=True,
    )
    resp.raise_for_status()
    
    for line in resp.iter_lines():
        if line:
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    pass


def _parse_chat_response(reply: str) -> tuple[ChatStatus, str, dict | None]:
    """Parse LLM response to determine status and extract config if ready."""
    if "[READY]" in reply:
        # Extract JSON config
        config = None
        clean_reply = reply
        try:
            # Find JSON block
            json_start = reply.find("```json")
            json_end = reply.find("```", json_start + 7)
            if json_start != -1 and json_end != -1:
                json_str = reply[json_start + 7:json_end].strip()
                config = json.loads(json_str)
                # Remove JSON block from display
                clean_reply = reply[:json_start] + reply[json_end + 3:]
            elif "{" in reply:
                # Fallback: parse first JSON object when model does not use fenced code.
                candidate = _extract_first_json_object(reply)
                if candidate.startswith("{"):
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        # Some providers wrap the actual config in an "answer" string.
                        nested = _maybe_parse_json_object(parsed.get("answer"))
                        config = nested if nested else parsed
                        # Remove parsed JSON object from display text.
                        idx = clean_reply.find(candidate)
                        if idx != -1:
                            clean_reply = clean_reply[:idx] + clean_reply[idx + len(candidate):]
        except Exception:
            pass
        
        # Clean reply (remove [READY] marker and extra whitespace)
        clean_reply = clean_reply.replace("[READY]", "").strip()
        clean_reply = _strip_ready_protocol_noise(clean_reply)
        # Remove any leftover empty lines
        clean_reply = "\n".join(line for line in clean_reply.split("\n") if line.strip())
        
        # If clean_reply is empty, provide a default message
        if not clean_reply:
            clean_reply = "I've gathered all the information needed. Here's the strategy configuration for your review:"

        # Only set status to READY if a non-empty dict config was successfully extracted
        if config and isinstance(config, dict) and len(config) > 0:
            return ChatStatus.READY, clean_reply, config

        # Otherwise, the model did not output a valid JSON config (e.g. still clarifying with user)
        return ChatStatus.CHATTING, clean_reply, None

    return ChatStatus.CHATTING, reply, None


def _extract_balanced_json(text: str) -> str | None:
    """
    Extract a balanced JSON object from text starting with '{'.

    Uses brace counting to handle nested objects correctly.
    """
    if not text or text[0] != '{':
        return None

    brace_count = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text):
        if escape_next:
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    # Found the closing brace
                    return text[:i+1]

    return None


def _strip_ready_protocol_noise(text: str) -> str:
    """
    Remove provider-style protocol preambles from READY messages.

    These lines are implementation noise and can mislead end users.
    """
    if not text:
        return ""

    noise_patterns = (
        r"^\s*(here|below)\s+is\s+(the\s+)?json(\s+you\s+requested|\s+requested)?\s*:?\s*$",
        r"^\s*(sure[,!]?\s*)?(here|below)\s+is\s+(the\s+)?requested\s+json\s*:?\s*$",
    )

    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if any(re.match(pattern, stripped, flags=re.IGNORECASE) for pattern in noise_patterns):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _clean_summary_source_text(raw: str) -> str:
    """Clean markdown and protocol noise to prepare text for summary."""
    text = (raw or "").replace("[READY]", "")
    json_start = text.find("```json")
    if json_start != -1:
        json_end = text.find("```", json_start + 7)
        if json_end != -1:
            text = text[:json_start] + text[json_end + 3:]
    text = _strip_ready_protocol_noise(text)
    lines = []
    for line in text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            continue
        if "```" in trimmed:
            continue
        if trimmed:
            lines.append(trimmed)
    return "\n".join(lines).strip()


def _is_summary_noise(text: str) -> bool:
    """Check if summary text contains protocol noise or raw JSON."""
    if not text:
        return True
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        return True
    if "here is the json requested" in s.lower() or "below is the json" in s.lower():
        return True
    if '"summary"' in s:
        return True
    return False


def _summarize_chat_reply(text: str) -> str:
    """Summarize chat reply with retry, falling back to cleaned source."""
    cleaned = _clean_summary_source_text(text)
    api_key, base_url, model = _get_llm_config()
    timeout_s = _get_llm_http_timeout_s()

    if not api_key:
        return cleaned or "已完成参数整理，请确认后生成策略。"

    for _ in range(2):
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a concise summarizer. Output only a short summary in JSON format: {\"summary\": \"...\"}"},
                        {"role": "user", "content": f"Summarize this strategy reply briefly in Chinese: {cleaned}"},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            summary = str(parsed.get("summary") or "").strip()
            if summary and not _is_summary_noise(summary):
                return summary
        except Exception:
            pass

    return cleaned or "已完成参数整理，请确认后生成策略。"


def _extract_first_json_object(text: str) -> str:
    raw = (text or "").strip()
    start_idx = raw.find("{")
    if start_idx == -1:
        return raw
    return _extract_balanced_json(raw[start_idx:]) or raw


def _maybe_parse_json_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if "{" not in raw:
        return None
    candidate = _extract_first_json_object(raw)
    if not candidate.startswith("{"):
        return None
    try:
        obj = json.loads(candidate)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _collect_user_messages(history: Any) -> list[str]:
    """Collect user-authored messages from chat history for prompt reconstruction."""
    if not isinstance(history, list):
        return []

    messages: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        content = str(item.get("content") or "").strip()
        if not content or content.startswith("/"):
            continue
        messages.append(content)
    return messages


def _build_generation_prompt(*, strategy: Strategy, request_prompt: str) -> tuple[str, str]:
    """
    Build generation prompt with first-principles priority:
    1) original user messages
    2) structured chat_config as supplemental reference
    3) request prompt as fallback
    """
    user_messages = _collect_user_messages(strategy.chat_history)
    if user_messages:
        source = "chat_history"
        base_prompt = "\n\n".join(user_messages).strip()
    else:
        source = "request_prompt"
        base_prompt = str(request_prompt or "").strip()

    chat_config = strategy.chat_config if isinstance(strategy.chat_config, dict) else None
    if chat_config:
        try:
            config_json = json.dumps(chat_config, ensure_ascii=False, indent=2)
        except Exception:
            config_json = str(chat_config)

        config_hint = (
            "Supplemental structured summary (reference only; user requirements above take precedence):\n"
            f"{config_json}"
        )
        if base_prompt:
            base_prompt = f"{base_prompt}\n\n{config_hint}"
        else:
            base_prompt = config_hint
            source = "chat_config_only"

    final_prompt = base_prompt.strip()
    if not final_prompt:
        return "Generate a strategy based on user requirements.", "fallback_default"
    return final_prompt, source


@router.post("/strategies/{strategy_id}/chat", response_model=ChatResponse)
def chat_with_strategy(
    strategy_id: str,
    req: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> ChatResponse:
    """Chat with AI to define strategy requirements or refine existing strategy."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    
    # Initialize chat history if needed
    if strategy.chat_history is None:
        strategy.chat_history = []
    
    # If strategy code has already been generated, all interaction is handled by Tau.
    is_done_mode = strategy.chat_status == ChatStatus.DONE

    user_message = req.message

    # Add user message
    history = list(strategy.chat_history)
    history.append({"role": "user", "content": user_message})

    # Call LLM with appropriate prompt
    try:
        if is_done_mode:
            strategy_code_path = os.path.join(settings.workspaces_dir, strategy_id, "strategy", "strategy.py")
            has_code = os.path.isfile(strategy_code_path)
            if not has_code:
                clean_reply = "当前策略代码不存在，先生成策略代码或恢复一个版本后再改。"
                _append_assistant_message(history, clean_reply)
                strategy.chat_history = history
                strategy.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(strategy)
                return ChatResponse(
                    reply=clean_reply,
                    status=ChatStatus.DONE,
                    chat_history=history,
                    config=strategy.chat_config,
                    refine_proposal=None,
                )
            backtest_context = _get_latest_backtest_context(db, strategy_id) or ""
            try:
                refine_meta = _run_autonomous_refine(
                    strategy_id,
                    user_message,
                    chat_history=history,
                    backtest_context=backtest_context,
                )
            except Exception as exc:
                clean_reply = f"Agent 处理失败：{exc}"
                _append_assistant_message(history, clean_reply)
                strategy.chat_history = history
                strategy.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(strategy)
                return ChatResponse(
                    reply=clean_reply,
                    status=ChatStatus.DONE,
                    chat_history=history,
                    config=strategy.chat_config,
                    refine_proposal=None,
                )

            files_changed = bool(refine_meta.get("files_changed"))
            agent_summary = str(refine_meta.get("agent_summary") or "").strip()
            if files_changed:
                clean_reply = (
                    "Agent 已完成本次修改，并已写入策略工作区。\n\n"
                    f"{agent_summary or '修改已应用。'}"
                )
                final_history = history + [{"role": "assistant", "content": clean_reply}]
                _persist_autonomous_refine_result(
                    db,
                    strategy_id=strategy_id,
                    final_history=final_history,
                    prompt=user_message,
                    llm_meta={
                        "mode": "autonomous_refine",
                        **refine_meta,
                    },
                )
            else:
                clean_reply = agent_summary or "已为您分析完毕。"
                final_history = history + [{"role": "assistant", "content": clean_reply}]
                strategy.chat_history = final_history
                strategy.updated_at = datetime.now(timezone.utc)
                db.commit()

            db.refresh(strategy)
            return ChatResponse(
                reply=clean_reply,
                status=ChatStatus.DONE,
                chat_history=final_history,
                config=strategy.chat_config,
                refine_proposal=None,
            )
        else:
            llm_history = _append_language_to_history(history, user_message)
            llm_history = _sanitize_llm_messages(llm_history)
            reply = _call_chat_llm(
                llm_history,
                system_prompt=CHAT_SYSTEM_PROMPT,
                json_mode=False,
            )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

    # Parse response for initial chat
    new_status, clean_reply, config = _parse_chat_response(reply)
    
    # Add assistant message
    _append_assistant_message(history, clean_reply)
    
    # Update strategy
    strategy.chat_history = history
    strategy.chat_status = new_status
    # Update config: set new config if ready, clear if back to chatting
    if new_status == ChatStatus.READY and config:
        strategy.chat_config = config
    elif new_status == ChatStatus.CHATTING:
        strategy.chat_config = None  # Clear config when going back to chatting
    strategy.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(strategy)
    
    return ChatResponse(
        reply=clean_reply,
        status=new_status,
        chat_history=history,
        config=config,
    )


@router.post("/strategies/{strategy_id}/chat/stream")
def chat_with_strategy_stream(
    strategy_id: str,
    req: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
    session_factory = Depends(get_session_factory),
) -> StreamingResponse:
    """Chat with AI using Server-Sent Events for streaming response."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    
    # Initialize chat history if needed
    if strategy.chat_history is None:
        strategy.chat_history = []
    
    # If strategy code has already been generated, all interaction is handled by Tau.
    is_done_mode = strategy.chat_status == ChatStatus.DONE

    user_message = req.message

    # Build history with new user message (store cleaned message to keep LLM context clean)
    history = list(strategy.chat_history)
    history.append({"role": "user", "content": user_message})
    llm_history = _append_language_to_history(history, user_message)
    llm_history = _sanitize_llm_messages(llm_history)

    early_reply: str | None = None

    if is_done_mode:
        strategy_code_path = os.path.join(settings.workspaces_dir, strategy_id, "strategy", "strategy.py")
        has_code = os.path.isfile(strategy_code_path)
        if not has_code:
            early_reply = "当前策略代码不存在，先生成策略代码或恢复一个版本后再改。"

    # Determine which system prompt and history to use
    if early_reply:
        chat_history = [{"role": "user", "content": _append_language_instruction(user_message)}]
        system_prompt = CHAT_SYSTEM_PROMPT
    elif user_message.strip() == "/generate_overview":
        pass
    else:
        chat_history = llm_history
        system_prompt = CHAT_SYSTEM_PROMPT

    def generate_sse():
        def _persist_chat(clean_reply: str) -> None:
            session = session_factory()
            try:
                strat = session.get(Strategy, strategy_id)
                if strat:
                    updated_history = list(strat.chat_history or [])
                    # Only append user message if it's not a hidden system command
                    if user_message != "/generate_overview":
                        updated_history.append({"role": "user", "content": user_message})
                    updated_history.append(_build_assistant_message(clean_reply))
                    strat.chat_history = updated_history
                    strat.updated_at = datetime.now(timezone.utc)
                    session.commit()
            finally:
                session.close()

        if user_message.strip() == "/generate_overview":
            from agent import tau_driver
            from agent.tau_config import ensure_catalog_entry, resolve_provider

            yield f"data: {json.dumps({'type': 'token', 'content': 'Starting autonomous agent to generate overview...\n'})}\n\n"

            try:
                strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
                target = resolve_provider()
                ensure_catalog_entry(target)

                task_prompt = (
                    "Analyze `strategy.py` and create/update `overview.md`.\n\n"
                    "Required format:\n"
                    "1. A `# Summary` section describing strategy logic.\n"
                    "2. A `# Trading Board` section describing K-line and PnL dashboard focus.\n"
                    "3. A `# Flow Animation` section that includes a ```mermaid flowchart.\n"
                    "4. Optionally include a ```g6 JSON graph with weighted edges for state transitions.\n"
                    "5. Save the final result to `overview.md`.\n"
                    "6. Verify the file before completing."
                )

                tau_driver.run_session(
                    task=task_prompt,
                    workspace=strategy_dir,
                    provider=target.provider,
                    model=target.model,
                    validate=lambda: _overview_problems(strategy_dir),
                    env=target.credential_env(),
                )
                clean_reply = "Overview generated successfully and saved to `overview.md`."

                _persist_chat(clean_reply)

                # Send final done message
                yield (
                    f"data: {json.dumps({'type': 'done', 'status': ChatStatus.DONE.value, 'clean_reply': clean_reply, 'config': None, 'chat_history': history + [{'role': 'assistant', 'content': clean_reply}], 'refine_proposal': None})}\n\n"
                )
            except Exception as e:
                logger.error(f"Overview generation failed: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        if early_reply:
            clean_reply = early_reply
            _persist_chat(clean_reply)
            final_history = history + [_build_assistant_message(clean_reply)]
            yield (
                f"data: {json.dumps({'type': 'done', 'status': ChatStatus.DONE.value, 'clean_reply': clean_reply, 'config': None, 'chat_history': final_history, 'refine_proposal': None})}\n\n"
            )
            return

        if is_done_mode:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'thinking', 'message': 'Agent 正在思考与处理...'}, ensure_ascii=False)}\n\n"
            progress_queue: queue.Queue[dict[str, Any]] = queue.Queue()

            def _push_progress(event: dict[str, Any]) -> None:
                progress_queue.put({"kind": "progress", "payload": event})

            backtest_context = _get_latest_backtest_context(db, strategy_id) or ""

            def _run_refine_worker() -> None:
                try:
                    refine_meta_result = _run_autonomous_refine(
                        strategy_id,
                        user_message,
                        chat_history=history,
                        on_progress=_push_progress,
                        backtest_context=backtest_context,
                    )
                    progress_queue.put({"kind": "result", "payload": refine_meta_result})
                except Exception as worker_error:
                    progress_queue.put({"kind": "error", "payload": str(worker_error)})
                finally:
                    progress_queue.put({"kind": "finished"})

            worker = threading.Thread(target=_run_refine_worker, daemon=True)
            worker.start()

            refine_meta: dict[str, Any] | None = None
            refine_error: str | None = None
            while True:
                event = progress_queue.get()
                kind = str(event.get("kind") or "")
                if kind == "progress":
                    payload = event.get("payload") or {}
                    tool = str(payload.get("tool") or "")
                    path = str(payload.get("path") or "")
                    phase = str(payload.get("phase") or "")
                    args = payload.get("args")
                    if not path and isinstance(args, dict):
                        path = str(args.get("path") or "")
                    if tool in {"edit_file", "write_file", "edit", "write", "read_file", "read"} and path:
                        file_name = os.path.basename(path)
                        action_text = "修改" if tool in {"edit_file", "write_file", "edit", "write"} else "阅读"
                        yield (
                            f"data: {json.dumps({'type': 'progress', 'tool': tool, 'path': file_name, 'message': f'正在{action_text} {file_name}...', 'phase': phase})}\n\n"
                        )
                elif kind == "result":
                    refine_meta = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                elif kind == "error":
                    refine_error = str(event.get("payload") or "unknown_error")
                elif kind == "finished":
                    break

            if refine_meta is not None and refine_error is None:
                files_changed = bool(refine_meta.get("files_changed"))
                agent_summary = str(refine_meta.get("agent_summary") or "").strip()
                if files_changed:
                    metrics_comp = str(refine_meta.get("metrics_comparison") or "")
                    clean_reply = (
                        "Agent 已完成本次修改，并已写入策略工作区。\n\n"
                        f"{agent_summary or '修改已应用。'}"
                        f"{metrics_comp}"
                    )
                    final_history = history + [{"role": "assistant", "content": clean_reply}]

                    session = session_factory()
                    try:
                        _persist_autonomous_refine_result(
                            session,
                            strategy_id=strategy_id,
                            final_history=final_history,
                            prompt=user_message,
                            llm_meta={
                                "mode": "autonomous_refine",
                                **refine_meta,
                            },
                        )
                        session.commit()
                    finally:
                        session.close()
                else:
                    clean_reply = agent_summary or "已为您分析完毕。"
                    final_history = history + [{"role": "assistant", "content": clean_reply}]

                    session = session_factory()
                    try:
                        strat = session.get(Strategy, strategy_id)
                        if strat:
                            strat.chat_history = final_history
                            strat.updated_at = datetime.now(timezone.utc)
                            session.commit()
                    finally:
                        session.close()
            else:
                clean_reply = f"Agent 处理失败：{refine_error or 'unknown_error'}"
                _persist_chat(clean_reply)
                final_history = history + [{"role": "assistant", "content": clean_reply}]

            chunk_size = 12
            for i in range(0, len(clean_reply), chunk_size):
                chunk = clean_reply[i : i + chunk_size]
                yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            yield (
                f"data: {json.dumps({'type': 'done', 'status': ChatStatus.DONE.value, 'clean_reply': clean_reply, 'config': None, 'chat_history': final_history, 'refine_proposal': None}, ensure_ascii=False)}\n\n"
            )
            return

        yield f"data: {json.dumps({'type': 'progress', 'stage': 'thinking', 'message': '正在分析策略需求与交易逻辑...'}, ensure_ascii=False)}\n\n"

        try:
            full_reply = _call_chat_llm(
                chat_history,
                system_prompt=system_prompt,
                json_mode=False,
            )
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        # Parse full response (normal chat flow)
        new_status, clean_reply, config = _parse_chat_response(full_reply)

        if new_status == ChatStatus.READY and config:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'ready', 'path': 'strategy.py', 'message': '正在生成 strategy.py 策略配置...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'replying', 'message': '正在组织回复内容...'}, ensure_ascii=False)}\n\n"

        # Stream the reply content in smooth chunks for SSE typewriter effect
        chunk_size = 12
        for i in range(0, len(clean_reply), chunk_size):
            chunk = clean_reply[i : i + chunk_size]
            yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

        session = session_factory()
        try:
            strat = session.get(Strategy, strategy_id)
            if strat:
                updated_history = list(strat.chat_history or [])
                updated_history.append({"role": "user", "content": user_message})
                updated_history.append(_build_assistant_message(clean_reply))

                strat.chat_history = updated_history
                strat.chat_status = new_status
                if new_status == ChatStatus.READY and config:
                    strat.chat_config = config
                elif new_status == ChatStatus.CHATTING:
                    strat.chat_config = None

                strat.updated_at = datetime.now(timezone.utc)
                session.commit()
        finally:
            session.close()

        final_history = history + [_build_assistant_message(clean_reply)]
        yield f"data: {json.dumps({'type': 'done', 'status': new_status.value, 'clean_reply': clean_reply, 'config': config, 'chat_history': final_history, 'refine_proposal': None}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/strategies/{strategy_id}/chat/confirm", response_model=StrategyResponse)
def confirm_strategy_chat(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    """Confirm the chat configuration and mark strategy ready for generation.
    
    Note: This endpoint only updates the strategy name from config but does NOT
    change chat_status. The status transition to GENERATING happens atomically
    in /generate when the job is actually created, preventing stuck states.
    """
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    
    if strategy.chat_status != ChatStatus.READY:
        raise HTTPException(status_code=400, detail="strategy_not_ready_for_confirmation")
    
    if not strategy.chat_config:
        raise HTTPException(status_code=400, detail="no_config_to_confirm")
    
    # Update strategy name from config summary if available (but keep status as READY)
    # The status will be set to GENERATING atomically in /generate endpoint
    strategy.updated_at = datetime.now(timezone.utc)
    if strategy.chat_config.get("summary"):
        strategy.name = _normalize_strategy_name(str(strategy.chat_config["summary"]))
    
    db.commit()
    db.refresh(strategy)
    
    return strategy


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
def get_strategy(strategy_id: str, request: Request, db: Session = Depends(get_db)) -> StrategyResponse:
    require_strategy_member(request, db, strategy_id)
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    return strategy


@router.get("/strategies/{strategy_id}/versions", response_model=list[StrategyVersionResponse])
def list_strategy_versions(strategy_id: str, request: Request, db: Session = Depends(get_db)) -> list[StrategyVersionResponse]:
    require_strategy_member(request, db, strategy_id)
    rows = (
        db.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version.desc())
        )
        .scalars()
        .all()
    )
    return rows


@router.post("/strategies/{strategy_id}/generate", response_model=TriggerJobResponse)
def generate_strategy(
    strategy_id: str,
    req: GenerateStrategyRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> TriggerJobResponse:
    """Generate strategy code from a prompt (no backtest). Also generates AI summary for strategy name.
    
    This endpoint atomically sets chat_status to GENERATING when the job is created,
    ensuring the strategy won't be stuck if the API call fails partway through.
    """
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    # Concurrency check: only one LLM job at a time
    _check_no_running_job(
        db,
        [JobType.GENERATE_STRATEGY, JobType.REFINE_STRATEGY, JobType.GENERATE_AND_BACKTEST],
        strategy_id,
    )

    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    final_prompt, prompt_source = _build_generation_prompt(strategy=strategy, request_prompt=req.prompt)
    validate_prompt(final_prompt)
    
    # Allow generation from READY status (fresh) or GENERATING (retry after failure)
    if strategy.chat_status not in (ChatStatus.READY, ChatStatus.GENERATING):
        raise HTTPException(status_code=400, detail="strategy_not_ready_for_generation")

    init_strategy_workspace(settings.workspaces_dir, strategy_id)

    version = create_strategy_version(
        db,
        strategy_id=strategy_id,
        prompt=final_prompt,
        llm_meta={
            **(req.llm_meta or {}),
            "prompt_source": prompt_source,
        },
        snapshot=False,
    )

    job = Job(
        type=JobType.GENERATE_STRATEGY,
        status=JobStatus.QUEUED,
        payload={
            "strategy_id": strategy_id,
            "version_id": version.id,
            "prompt": final_prompt,
            "llm_meta": {
                **(req.llm_meta or {}),
                "prompt_source": prompt_source,
            },
        },
    )
    db.add(job)
    
    # Atomically set status to GENERATING when job is created
    # This prevents stuck state if previous /generate call failed
    strategy.chat_status = ChatStatus.GENERATING
    strategy.updated_at = datetime.now(timezone.utc)
    db.flush()

    db.commit()
    enqueue_job(settings.workspaces_dir, job.id, job.type, job.payload, redis_client=rds)

    db.refresh(job)
    db.refresh(version)
    return TriggerJobResponse(job=job, strategy_version=version)


@router.post("/strategies/{strategy_id}/refine", response_model=TriggerJobResponse)
def refine_strategy(
    strategy_id: str,
    req: RefineStrategyRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> TriggerJobResponse:
    """Apply a prompt to refine the current working strategy (no backtest by default)."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])

    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    if req.patch or req.change_spec:
        raise HTTPException(
            status_code=400,
            detail="patch_or_change_spec_mode_removed_use_prompt_only",
        )

    # Concurrency check: only one LLM job at a time
    _check_no_running_job(
        db,
        [JobType.GENERATE_STRATEGY, JobType.REFINE_STRATEGY, JobType.GENERATE_AND_BACKTEST],
        strategy_id,
    )

    init_strategy_workspace(settings.workspaces_dir, strategy_id)

    version = create_strategy_version(
        db,
        strategy_id=strategy_id,
        prompt=req.prompt,
        llm_meta=req.llm_meta or {},
        snapshot=False,
    )

    job = Job(
        type=JobType.REFINE_STRATEGY,
        status=JobStatus.QUEUED,
        payload={
            "strategy_id": strategy_id,
            "version_id": version.id,
            "prompt": req.prompt,
            "llm_meta": req.llm_meta or {},
        },
    )
    db.add(job)
    strategy.updated_at = datetime.now(timezone.utc)
    db.flush()

    db.commit()
    enqueue_job(settings.workspaces_dir, job.id, job.type, job.payload, redis_client=rds)

    db.refresh(job)
    db.refresh(version)
    return TriggerJobResponse(job=job, strategy_version=version)


@router.post("/strategies/{strategy_id}/versions/{version_id}/restore", response_model=StrategyResponse)
def restore_strategy_version(
    strategy_id: str,
    version_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    """Restore a historical version snapshot to become the current working strategy.

    Safety: creates a backup snapshot of the current working copy first.
    """
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    version = db.get(StrategyVersion, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="strategy_version_not_found")

    init_strategy_workspace(settings.workspaces_dir, strategy_id)

    # Backup current working copy so restore is always reversible.
    backup = create_strategy_version(
        db,
        strategy_id=strategy_id,
        prompt=f"[auto] backup_before_restore:{version_id}",
        llm_meta={"source": "backup_before_restore", "restore_target": version_id},
        snapshot=True,
        workspaces_dir=settings.workspaces_dir,
    )

    # Restore selected version into working copy (delegated to worker RPC).
    call_worker_rpc(
        "/internal/strategies/versions/restore",
        {
            "strategy_id": strategy_id,
            "version_id": version_id,
            "prompt": f"restore:{version_id}",
        },
    )

    strategy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(strategy)
    return strategy
