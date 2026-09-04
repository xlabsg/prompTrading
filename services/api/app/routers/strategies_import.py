"""Strategy import endpoints for TradingView and YouTube."""

from __future__ import annotations

import logging
import sys
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from control_plane.enums import ChatStatus, JobStatus, JobType, StrategyRole
from control_plane.versions import create_strategy_version
from control_plane.models import Job, Strategy, StrategyMember
from control_plane.queue import enqueue_job
from control_plane.workspaces import init_strategy_workspace

from app.auth import get_current_user, user_has_active_subscription
from app.deps import get_db, get_redis
from app.schemas import ImportStrategyResponse, ImportTradingViewRequest, ImportYouTubeRequest
from app.settings import settings

# Add packages to path
TRADINGVIEW_SCRAPER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "..", "packages", "tradingview_scraper"
)
if TRADINGVIEW_SCRAPER_PATH not in sys.path:
    sys.path.insert(0, TRADINGVIEW_SCRAPER_PATH)

YOUTUBE_PROCESSOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "..", "packages", "youtube_processor"
)
if YOUTUBE_PROCESSOR_PATH not in sys.path:
    sys.path.insert(0, YOUTUBE_PROCESSOR_PATH)

logger = logging.getLogger(__name__)
router = APIRouter()




@router.post("/strategies/import/tradingview", response_model=ImportStrategyResponse)
async def import_from_tradingview(
    req: ImportTradingViewRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> ImportStrategyResponse:
    """Import strategy from TradingView PineScript URL.

    Workflow:
    1. Scrape PineScript source code from TradingView URL
    2. Create new strategy with auto-generated or custom name
    3. Generate prompt to convert PineScript to Python
    4. Submit async job for LLM conversion
    5. Return job and strategy info for frontend tracking
    """
    user = get_current_user(request, db)

    # Check subscription limits
    if not user_has_active_subscription(user):
        from sqlalchemy import func, select
        existing_count = db.execute(
            select(func.count(StrategyMember.id)).where(StrategyMember.user_id == user.id)
        ).scalar_one()
        if existing_count >= settings.free_strategy_limit:
            raise HTTPException(status_code=403, detail="strategy_limit_reached")

    # Validate and scrape TradingView URL
    try:
        from tradingview_scraper import get_pinescript

        logger.info(f"Scraping TradingView URL: {req.url}")
        script_data = get_pinescript(req.url)

        if not script_data.get("source"):
            error_msg = script_data.get("error", "Failed to fetch PineScript source code")
            raise HTTPException(
                status_code=400,
                detail=f"tradingview_scrape_failed: {error_msg}"
            )

        pinescript_source = script_data["source"]
        script_name = script_data.get("name", "")
        script_author = script_data.get("author", "")
        script_description = script_data.get("description", "")

        logger.info(f"Successfully scraped PineScript: {script_name} by {script_author}")

    except ImportError as e:
        logger.error(f"TradingView scraper not available: {e}")
        raise HTTPException(
            status_code=500,
            detail="tradingview_scraper_not_installed"
        )
    except Exception as e:
        logger.error(f"Failed to scrape TradingView URL: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"tradingview_scrape_error: {str(e)}"
        )

    # Create strategy with auto-generated or custom name
    strategy_name = req.strategy_name
    if not strategy_name or not strategy_name.strip():
        if script_name:
            strategy_name = f"{script_name} (from TradingView)"
        else:
            strategy_name = f"TradingView Import - {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    # Truncate name to avoid database overflow
    if len(strategy_name) > 100:
        strategy_name = strategy_name[:97] + "..."

    strategy = Strategy(name=strategy_name)
    db.add(strategy)
    db.flush()

    # Initialize workspace
    init_strategy_workspace(settings.workspaces_dir, strategy.id)

    # Create initial version
    version = create_strategy_version(
        db,
        strategy_id=strategy.id,
        version=1,
        prompt=f"Imported from TradingView: {req.url}",
        llm_meta={
            "source": "tradingview_import",
            "original_url": req.url,
            "script_name": script_name,
            "script_author": script_author,
        },
        snapshot=True,
        workspaces_dir=settings.workspaces_dir,
    )

    # Add user as admin
    member = StrategyMember(
        strategy_id=strategy.id,
        user_id=user.id,
        role=StrategyRole.ADMIN
    )
    db.add(member)

    # Generate conversion prompt
    conversion_prompt = _build_pinescript_conversion_prompt(
        pinescript_source=pinescript_source,
        script_name=script_name,
        script_description=script_description,
    )

    # Create job for LLM conversion
    job = Job(
        type=JobType.GENERATE_STRATEGY,
        status=JobStatus.QUEUED,
        payload={
            "strategy_id": strategy.id,
            "version_id": version.id,
            "prompt": conversion_prompt,
            "llm_meta": {
                "source": "tradingview_import",
                "original_url": req.url,
                "script_name": script_name,
            },
        },
    )
    db.add(job)

    # Set strategy status
    strategy.chat_status = ChatStatus.GENERATING
    strategy.updated_at = datetime.now(timezone.utc)
    db.flush()

    db.commit()

    # Queue job for worker
    enqueue_job(settings.workspaces_dir, job.id, job.type, job.payload, redis_client=rds)

    db.refresh(strategy)
    db.refresh(job)
    db.refresh(version)

    return ImportStrategyResponse(
        job=job,
        strategy=strategy,
        strategy_version=version,
        source_metadata={
            "source_type": "tradingview",
            "url": req.url,
            "script_name": script_name,
            "script_author": script_author,
            "script_description": script_description,
            "script_id": script_data.get("id", ""),
            "views": script_data.get("views", 0),
            "likes": script_data.get("likes", 0),
        }
    )


@router.post("/strategies/import/youtube", response_model=ImportStrategyResponse)
async def import_from_youtube(
    req: ImportYouTubeRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> ImportStrategyResponse:
    """Import strategy from YouTube video (audio transcription).

    NOTE: This feature is temporarily disabled due to YouTube's restrictions.
    """
    # Temporarily disabled - return error immediately
    raise HTTPException(
        status_code=503,
        detail="YouTube import is temporarily unavailable due to YouTube's bot detection restrictions. Please use TradingView import instead."
    )


def _build_pinescript_conversion_prompt(
    pinescript_source: str,
    script_name: str,
    script_description: str,
) -> str:
    """Build a detailed prompt for LLM to convert PineScript to Python.

    The prompt guides the LLM to:
    1. Understand the PineScript trading logic
    2. Extract key indicators and signals
    3. Convert to vectorized pandas/numpy implementation
    4. Maintain the same trading strategy essence
    """
    prompt = f"""Convert the following TradingView PineScript strategy to Python for backtesting.

**Original Script Information:**
- Name: {script_name}
- Description: {script_description}

**PineScript Source Code:**
```pinescript
{pinescript_source}
```

**Conversion Requirements:**

1. **Understand the Strategy Logic:**
   - Analyze what indicators are used (SMA, EMA, RSI, MACD, etc.)
   - Identify entry and exit conditions
   - Note any position sizing or risk management rules

2. **Convert to Python:**
   - Implement as vectorized pandas/numpy operations
   - Use available indicators from backtest.indicators module:
     - sma(x, window), ema(x, window), rsi(close, window=14)
     - cross_over(a, b), cross_under(a, b), zscore(x, window)
   - Define generate_signals(data: pd.DataFrame, params: dict) -> dict
   - Return {{target_weights: float_array}} with values in [-1, 1]
   - Include explainability fields:
     - ALSO return weight_reason as list[str] length n (empty string when no signal)
     - Include 2-6 helpful debug series (bar-aligned floats/bools) like rsi, fast_ma, slow_ma, regime_long, regime_short

3. **Maintain Strategy Essence:**
   - Keep the same core trading logic and signals
   - Preserve indicator parameters (can make them configurable via params)
   - Match the entry/exit conditions as closely as possible

4. **Best Practices:**
   - Use params.get(key, default) for all parameters
   - Handle edge cases (NaN values, insufficient data)
   - Add comments explaining key logic from PineScript
   - Ensure deterministic and reproducible results

**Output Format:**
Generate a complete Python strategy file with:
- Necessary imports
- generate_signals() function with vectorized logic
- Optional: LiveStrategy class for live trading hooks
- Clear comments mapping to PineScript logic

Focus on accurately translating the trading rules while adapting to Python's pandas-based backtesting framework.
"""

    return prompt.strip()
