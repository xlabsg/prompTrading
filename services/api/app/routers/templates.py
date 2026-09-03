"""Strategy Templates API endpoints

This router provides endpoints for:
- Listing public strategy templates (builtin, tradingview, community)
- Viewing template details
- Subscribing/copying a template to user's own strategy
- Managing subscriptions
- Syncing template updates to subscribed strategies
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from pydantic import BaseModel, Field
from sqlalchemy import Float, case, cast, select, func
from sqlalchemy.orm import Session

from control_plane.enums import (
    StrategyRole,
    StrategyTemplateType,
    SubscriptionStatus,
)
from control_plane.models import (
    Strategy,
    StrategyExchangeAccount,
    StrategyMember,
    StrategySubscription,
    StrategyTemplate,
    StrategyVersion,
    User,
)
from control_plane.templates import instantiate_strategy_from_template
from control_plane.workspaces import (
    init_strategy_workspace,
    snapshot_current_strategy_to_version,
)
from app.auth import get_current_user
from app.deps import get_db
from app.settings import settings

router = APIRouter()


# ============== Request/Response Schemas ==============


class TemplateListItem(BaseModel):
    """Summary of a strategy template for listing."""
    id: str
    name: str
    description: str | None
    template_type: str
    author: str | None
    tags: list[str] | None
    subscriber_count: int
    is_featured: bool
    stable5_qualifies: bool | None = None
    stable5_score: float | None = None
    risk_level: str | None
    trading_frequency: str | None
    complexity_score: int | None
    created_at: datetime


class TemplateDetailResponse(BaseModel):
    """Full template details including config snapshot."""
    id: str
    name: str
    description: str | None
    template_type: str
    author: str | None
    tags: list[str] | None
    config_snapshot: dict[str, Any] | None
    prompt: str | None
    version: int
    is_featured: bool
    subscriber_count: int
    risk_level: str | None
    trading_frequency: str | None
    complexity_score: int | None
    min_capital_usdt: float | None
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    """Response for listing templates."""
    total: int
    templates: list[TemplateListItem]


class ForkTemplateRequest(BaseModel):
    """Request to fork a strategy template into a personal strategy."""
    name: str = Field(..., min_length=1, max_length=200, description="Name for your strategy copy")
    description: Optional[str] = Field(None, max_length=1000, description="Optional strategy description")


class ForkTemplateResponse(BaseModel):
    """Response after forking a strategy template."""
    strategy_id: str
    strategy_name: str
    version_id: str
    message: str


class TelegramConfigRequest(BaseModel):
    """Telegram notification configuration."""
    bot_token_encrypted: str = Field(..., description="Encrypted Telegram bot token")
    chat_id: str = Field(..., description="Telegram chat/group ID")
    enabled: bool = Field(default=True, description="Whether notifications are enabled")
    notify_on_signal: bool = Field(default=True, description="Notify on trading signals")
    notify_on_execution: bool = Field(default=True, description="Notify on order execution")
    notify_on_error: bool = Field(default=True, description="Notify on errors")


class SubscribeRequest(BaseModel):
    """Request to subscribe/copy a template."""
    name: str = Field(..., min_length=1, max_length=200, description="Name for your copy")
    exchange: str = Field(..., description="Exchange: okx, binance")
    symbols: list[str] = Field(..., min_length=1, max_length=3, description="Trading symbols (max 3): BTC-USDT-SWAP, ETH-USDT-SWAP")
    api_key_encrypted: str = Field(..., description="Encrypted API key")
    api_secret_encrypted: str = Field(..., description="Encrypted API secret")
    api_passphrase_encrypted: Optional[str] = Field(None, description="API passphrase (OKX only)")
    max_position_pct: float = Field(default=10.0, ge=1.0, le=100.0)
    stop_loss_pct: float = Field(default=5.0, ge=0.1, le=50.0)
    custom_params: Optional[dict[str, Any]] = Field(None, description="Additional custom params")
    telegram_config: Optional[TelegramConfigRequest] = Field(None, description="Telegram notification config")


class SubscribeResponse(BaseModel):
    """Response after subscribing to a template."""
    subscription_id: str
    strategy_id: str
    strategy_name: str
    message: str


class SubscriptionResponse(BaseModel):
    """Response for a subscription."""
    id: str
    template_id: str
    template_name: str
    strategy_id: str
    strategy_name: str
    status: str
    subscribed_version: int
    template_version: int
    is_outdated: bool
    last_synced_at: datetime | None
    user_config: dict[str, Any] | None
    telegram_config: dict[str, Any] | None
    telegram_status: dict[str, Any] | None
    created_at: datetime


class SubscriptionListResponse(BaseModel):
    """Response for listing subscriptions."""
    total: int
    subscriptions: list[SubscriptionResponse]


class SyncResultResponse(BaseModel):
    """Response after syncing a subscription."""
    subscription_id: str
    strategy_id: str
    previous_version: int
    new_version: int
    message: str


class UserConfigUpdateRequest(BaseModel):
    """Request to update user configuration."""
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    max_position_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    custom_params: Optional[dict[str, Any]] = None


# ============== Helper Functions ==============


def template_to_list_item(template: StrategyTemplate) -> dict[str, Any]:
    stable5 = (template.backtest_summary or {}).get("stable5") if template.backtest_summary else None
    stable5_qualifies = None
    stable5_score = None
    if isinstance(stable5, dict):
        if "qualifies" in stable5:
            stable5_qualifies = bool(stable5.get("qualifies"))
        if "score" in stable5:
            try:
                stable5_score = float(stable5.get("score"))
            except Exception:
                stable5_score = None
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "template_type": template.template_type,
        "author": template.author,
        "tags": template.tags or [],
        "subscriber_count": template.subscriber_count,
        "is_featured": template.is_featured,
        "stable5_qualifies": stable5_qualifies,
        "stable5_score": stable5_score,
        "risk_level": template.risk_level,
        "trading_frequency": template.trading_frequency,
        "complexity_score": template.complexity_score,
        "created_at": template.created_at,
    }


def template_to_detail(template: StrategyTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "template_type": template.template_type,
        "author": template.author,
        "tags": template.tags or [],
        "config_snapshot": template.config_snapshot,
        "prompt": template.prompt,
        "version": template.version,
        "is_featured": template.is_featured,
        "subscriber_count": template.subscriber_count,
        "risk_level": template.risk_level,
        "trading_frequency": template.trading_frequency,
        "complexity_score": template.complexity_score,
        "min_capital_usdt": float(template.min_capital_usdt) if template.min_capital_usdt else None,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def subscription_to_response(sub: StrategySubscription, template: StrategyTemplate) -> SubscriptionResponse:
    # Build telegram config response (hide bot token)
    telegram_config = None
    if sub.telegram_config:
        cfg = sub.telegram_config.copy()
        if "bot_token" in cfg:
            cfg["bot_token"] = "***hidden***"
        telegram_config = cfg

    # Build telegram status
    telegram_status = None
    if sub.telegram_config and sub.telegram_config.get("enabled"):
        telegram_status = {
            "is_configured": True,
            "is_enabled": sub.telegram_config.get("enabled", False),
            "last_notification_at": sub.telegram_last_notification_at,
            "error": sub.telegram_notification_error,
        }
    else:
        telegram_status = {
            "is_configured": False,
            "is_enabled": False,
            "last_notification_at": None,
            "error": None,
        }

    return {
        "id": sub.id,
        "template_id": template.id,
        "template_name": template.name,
        "strategy_id": sub.strategy_id,
        "strategy_name": sub.strategy.name if sub.strategy else "",
        "status": sub.status,
        "subscribed_version": sub.subscribed_version,
        "template_version": template.version,
        "is_outdated": template.version > sub.subscribed_version,
        "last_synced_at": sub.last_synced_at,
        "user_config": sub.user_config,
        "telegram_config": telegram_config,
        "telegram_status": telegram_status,
        "created_at": sub.created_at,
    }


# ============== API Endpoints ==============


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    template_type: StrategyTemplateType | None = None,
    featured: bool | None = None,
    search: str | None = None,
    stable5_only: bool | None = None,
    sort: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> TemplateListResponse:
    """
    List available strategy templates.

    - template_type: Filter by type (builtin, tradingview, community)
    - featured: Only show featured templates
    - search: Search by name/description/tags
    - limit: Max results per page (max 50)
    - offset: Pagination offset
    """
    limit = min(limit, 50)

    query = db.query(StrategyTemplate).filter(StrategyTemplate.is_public == True)

    if template_type:
        query = query.filter(StrategyTemplate.template_type == template_type.value)

    if featured is True:
        query = query.filter(StrategyTemplate.is_featured == True)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (StrategyTemplate.name.ilike(search_term)) |
            (StrategyTemplate.description.ilike(search_term)) |
            (StrategyTemplate.tags.contains([search]))
        )

    if stable5_only is True:
        query = query.filter(StrategyTemplate.backtest_summary["stable5"]["qualifies"].as_string() == "true")

    total = query.count()
    sort_key = (sort or "").strip().lower()
    if sort_key == "stable5":
        stable5_score = cast(StrategyTemplate.backtest_summary["stable5"]["score"].as_string(), Float)
        stable5_qualifies = StrategyTemplate.backtest_summary["stable5"]["qualifies"].as_string() == "true"
        qualifies_rank = case((stable5_qualifies, 1), else_=0)
        templates = query.order_by(
            qualifies_rank.desc(),
            stable5_score.desc().nullslast(),
            StrategyTemplate.subscriber_count.desc(),
        ).offset(offset).limit(limit).all()
    else:
        # Default: popularity
        templates = query.order_by(
            StrategyTemplate.subscriber_count.desc(),
        ).offset(offset).limit(limit).all()

    return TemplateListResponse(
        total=total,
        templates=[TemplateListItem(**template_to_list_item(t)) for t in templates],
    )


@router.get("/templates/{template_id}", response_model=TemplateDetailResponse)
async def get_template(
    template_id: str,
    db: Session = Depends(get_db),
) -> TemplateDetailResponse:
    """Get detailed information about a template."""
    template = db.query(StrategyTemplate).filter_by(id=template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.is_public:
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateDetailResponse(**template_to_detail(template))


@router.post("/templates/{template_id}/fork", response_model=ForkTemplateResponse)
async def fork_template(
    template_id: str,
    req: ForkTemplateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ForkTemplateResponse:
    """
    Fork a strategy template - creates a real strategy for the user with template code.

    This will:
    1. Create a new Strategy record owned by the user
    2. Add StrategyMember with role ADMIN
    3. Create StrategyVersion with version 1
    4. Write real template code and spec into strategy workspace files & snapshot to version
    5. Initialize Git repository and commit
    """
    user = get_current_user(request, db)

    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    strategy_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    strategy = Strategy(
        id=strategy_id,
        name=req.name.strip(),
        chat_status="done",
        chat_config={"description": req.description or template.description, "source": "template_fork", "template_id": template.id},
    )
    db.add(strategy)

    member = StrategyMember(
        strategy_id=strategy_id,
        user_id=user.id,
        role=StrategyRole.ADMIN,
    )
    db.add(member)

    version = StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version=1,
        workspace_path=f"versions/{version_id}/",
        prompt=template.prompt,
        llm_meta={
            "source": "template_fork",
            "template_id": template.id,
            "template_name": template.name,
            "template_version": template.version,
        },
    )
    db.add(version)

    instantiate_strategy_from_template(
        settings.workspaces_dir,
        strategy_id=strategy_id,
        version_id=version_id,
        template=template,
    )

    template.subscriber_count += 1
    db.commit()

    return ForkTemplateResponse(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        version_id=version_id,
        message=f"Strategy '{strategy.name}' successfully created from template '{template.name}'.",
    )


@router.post("/templates/{template_id}/subscribe", response_model=SubscribeResponse)
async def subscribe_template(
    template_id: str,
    req: SubscribeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscribeResponse:
    """
    Subscribe to a template - creates a Strategy copy for the user.

    This will:
    1. Create a new Strategy record
    2. Add StrategyMember with role ADMIN
    3. Create a StrategyVersion with the template's code
    4. Write real template code and spec into strategy workspace files
    5. Create a StrategyExchangeAccount with provided credentials
    6. Create a TradingConfig with user's trading parameters
    7. Create a StrategySubscription linking everything
    """
    user = get_current_user(request, db)

    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Check if already subscribed
    existing = db.query(StrategySubscription).filter_by(
        template_id=template_id,
        user_id=user.id,
        status="active"
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Already subscribed to this template"
        )

    # Create new strategy
    strategy_id = str(uuid.uuid4())
    strategy = Strategy(
        id=strategy_id,
        name=req.name,
        chat_status="done",  # Template-based strategies are already complete
    )
    db.add(strategy)

    member = StrategyMember(
        strategy_id=strategy_id,
        user_id=user.id,
        role=StrategyRole.ADMIN,
    )
    db.add(member)

    # Create strategy version from template with actual code
    version_id = str(uuid.uuid4())
    workspace_path = f"versions/{version_id}/"
    instantiate_strategy_from_template(
        settings.workspaces_dir,
        strategy_id=strategy_id,
        version_id=version_id,
        template=template,
    )

    version = StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version=1,
        workspace_path=workspace_path,
        prompt=template.prompt,
        llm_meta={
            "source": "template",
            "template_id": template.id,
            "template_version": template.version,
        },
    )
    db.add(version)

    # Create exchange account
    from app.crypto import encrypt_credential
    exchange_account = StrategyExchangeAccount(
        strategy_id=strategy_id,
        name=f"{req.exchange} - {', '.join(req.symbols)}",
        exchange=req.exchange,
        api_key_encrypted=req.api_key_encrypted,
        api_secret_encrypted=req.api_secret_encrypted,
        api_passphrase_encrypted=req.api_passphrase_encrypted,
        is_connected=True,
    )
    db.add(exchange_account)

    # Create trading config
    from control_plane.models import TradingConfig
    config = TradingConfig(
        strategy_id=strategy_id,
        exchange=req.exchange,
        symbol=req.symbols[0],
        symbols=req.symbols,
        api_key_encrypted=req.api_key_encrypted,
        api_secret_encrypted=req.api_secret_encrypted,
        api_passphrase_encrypted=req.api_passphrase_encrypted,
        max_position_pct=req.max_position_pct,
        stop_loss_pct=req.stop_loss_pct,
        is_active=False,
    )
    db.add(config)

    # Merge custom params into user_config
    user_config = {
        "exchange": req.exchange,
        "symbols": req.symbols,
        "max_position_pct": req.max_position_pct,
        "stop_loss_pct": req.stop_loss_pct,
        "custom_params": req.custom_params or {},
        "risk_budget": {
            "profile": "conservative5",
            "max_daily_loss_pct": 0.8,
            "max_drawdown_pct": 5.0,
            "max_leverage": 2,
            "freeze_on_breach": True,
            "allow_reduce_only": True,
        },
    }

    # Prepare Telegram config
    telegram_config = None
    if req.telegram_config:
        telegram_config = {
            "bot_token": req.telegram_config.bot_token_encrypted,
            "chat_id": req.telegram_config.chat_id,
            "enabled": req.telegram_config.enabled,
            "notify_on_signal": req.telegram_config.notify_on_signal,
            "notify_on_execution": req.telegram_config.notify_on_execution,
            "notify_on_error": req.telegram_config.notify_on_error,
        }

    # Create subscription
    subscription = StrategySubscription(
        template_id=template_id,
        strategy_id=strategy_id,
        user_id=user.id,
        status="active",
        subscribed_version=template.version,
        last_synced_at=datetime.now(timezone.utc),
        user_config=user_config,
        telegram_config=telegram_config,
    )
    db.add(subscription)

    # Update subscriber count
    template.subscriber_count += 1

    db.commit()
    db.refresh(subscription)

    return SubscribeResponse(
        subscription_id=subscription.id,
        strategy_id=strategy_id,
        strategy_name=req.name,
        message=f"Successfully subscribed to template. Your strategy '{req.name}' is ready.",
    )


@router.delete("/templates/{template_id}/unsubscribe")
async def unsubscribe_template(
    template_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Unsubscribe from a template - deletes the subscribed strategy."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        template_id=template_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Get template for counter update
    strategy = db.query(Strategy).filter_by(id=subscription.strategy_id).first()

    # Delete the subscription and associated strategy
    db.delete(subscription)
    if strategy:
        db.delete(strategy)

    if template:
        template.subscriber_count = max(0, template.subscriber_count - 1)

    db.commit()

    return {"message": "Successfully unsubscribed from template"}


@router.get("/subscriptions", response_model=SubscriptionListResponse)
async def list_subscriptions(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionListResponse:
    """List all subscriptions for the current user."""
    user = get_current_user(request, db)

    subscriptions = db.query(StrategySubscription).filter_by(
        user_id=user.id,
    ).order_by(StrategySubscription.created_at.desc()).all()

    result = []
    for sub in subscriptions:
        template = db.query(StrategyTemplate).filter_by(id=sub.template_id).first()
        if template:
            result.append(SubscriptionResponse(**subscription_to_response(sub, template)))

    return SubscriptionListResponse(
        total=len(result),
        subscriptions=result,
    )


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    """Get details of a specific subscription."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    template = db.query(StrategyTemplate).filter_by(id=subscription.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return SubscriptionResponse(**subscription_to_response(subscription, template))


@router.post("/subscriptions/{subscription_id}/sync", response_model=SyncResultResponse)
async def sync_subscription(
    subscription_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SyncResultResponse:
    """
    Sync subscription with latest template updates.

    This will:
    1. Check if template has newer version
    2. If yes, create a new StrategyVersion with updated code
    3. Update subscription's subscribed_version
    """
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    template = db.query(StrategyTemplate).filter_by(id=subscription.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    previous_version = subscription.subscribed_version

    if template.version <= previous_version:
        return SyncResultResponse(
            subscription_id=subscription.id,
            strategy_id=subscription.strategy_id,
            previous_version=previous_version,
            new_version=previous_version,
            message="Already at latest version",
        )

    # Create new version with template's code
    strategy = db.query(Strategy).filter_by(id=subscription.strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    new_version_num = _next_version_number(db, subscription.strategy_id)
    version_id = str(uuid.uuid4())
    workspace_path = f"versions/{version_id}/"
    instantiate_strategy_from_template(
        settings.workspaces_dir,
        strategy_id=subscription.strategy_id,
        version_id=version_id,
        template=template,
    )

    version = StrategyVersion(
        id=version_id,
        strategy_id=subscription.strategy_id,
        version=new_version_num,
        workspace_path=workspace_path,
        prompt=template.prompt,
        llm_meta={
            "source": "template_sync",
            "template_id": template.id,
            "template_version": template.version,
            "previous_version": previous_version,
        },
    )
    db.add(version)

    # Update subscription
    subscription.subscribed_version = template.version
    subscription.last_synced_at = datetime.now(timezone.utc)
    subscription.sync_error = None

    db.commit()
    db.refresh(subscription)

    return SyncResultResponse(
        subscription_id=subscription.id,
        strategy_id=subscription.strategy_id,
        previous_version=previous_version,
        new_version=template.version,
        message=f"Successfully synced from version {previous_version} to {template.version}",
    )


@router.patch("/subscriptions/{subscription_id}/config")
async def update_subscription_config(
    subscription_id: str,
    req: UserConfigUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    """Update user configuration for a subscription."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Update user_config
    if subscription.user_config is None:
        subscription.user_config = {}

    if req.exchange is not None:
        subscription.user_config["exchange"] = req.exchange
    if req.symbol is not None:
        subscription.user_config["symbol"] = req.symbol
    if req.max_position_pct is not None:
        subscription.user_config["max_position_pct"] = req.max_position_pct
    if req.stop_loss_pct is not None:
        subscription.user_config["stop_loss_pct"] = req.stop_loss_pct
    if req.custom_params is not None:
        subscription.user_config["custom_params"] = req.custom_params

    # Also update TradingConfig if exists
    from control_plane.models import TradingConfig
    config = db.query(TradingConfig).filter_by(strategy_id=subscription.strategy_id).first()
    if config:
        if req.exchange is not None:
            config.exchange = req.exchange
        if req.symbol is not None:
            config.symbol = req.symbol
        if req.max_position_pct is not None:
            config.max_position_pct = req.max_position_pct
        if req.stop_loss_pct is not None:
            config.stop_loss_pct = req.stop_loss_pct

    db.commit()

    template = db.query(StrategyTemplate).filter_by(id=subscription.template_id).first()
    return SubscriptionResponse(**subscription_to_response(subscription, template))


@router.post("/subscriptions/{subscription_id}/pause")
async def pause_subscription(
    subscription_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    """Pause a subscription (stop syncing and trading)."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    subscription.status = "paused"

    # Also pause trading config
    from control_plane.models import TradingConfig
    config = db.query(TradingConfig).filter_by(strategy_id=subscription.strategy_id).first()
    if config:
        config.is_active = False

    db.commit()

    template = db.query(StrategyTemplate).filter_by(id=subscription.template_id).first()
    return SubscriptionResponse(**subscription_to_response(subscription, template))


@router.post("/subscriptions/{subscription_id}/resume")
async def resume_subscription(
    subscription_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    """Resume a paused subscription."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    subscription.status = "active"

    # Also resume trading config
    from control_plane.models import TradingConfig
    config = db.query(TradingConfig).filter_by(strategy_id=subscription.strategy_id).first()
    if config:
        config.is_active = True

    db.commit()

    template = db.query(StrategyTemplate).filter_by(id=subscription.template_id).first()
    return SubscriptionResponse(**subscription_to_response(subscription, template))


def _next_version_number(db: Session, strategy_id: str) -> int:
    """Get the next version number for a strategy."""
    cur = db.execute(
        select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_id == strategy_id)
    ).scalar()
    return int(cur or 0) + 1


# ============== Telegram Configuration Endpoints ==============


class TelegramTestRequest(BaseModel):
    """Request to test Telegram connection."""
    bot_token_encrypted: str = Field(..., description="Encrypted bot token")
    chat_id: str = Field(..., description="Telegram chat/group ID")


class TelegramTestResponse(BaseModel):
    """Response for Telegram connection test."""
    success: bool
    message: str
    bot_username: str | None = None


class TelegramConfigUpdateRequest(BaseModel):
    """Request to update Telegram configuration."""
    bot_token_encrypted: str | None = Field(None, description="Encrypted bot token (required to update)")
    chat_id: str | None = Field(None, description="Telegram chat/group ID")
    enabled: bool | None = Field(None, description="Enable/disable notifications")
    notify_on_signal: bool | None = Field(None)
    notify_on_execution: bool | None = Field(None)
    notify_on_error: bool | None = Field(None)


@router.post("/subscriptions/{subscription_id}/telegram/test", response_model=TelegramTestResponse)
async def test_telegram_connection(
    subscription_id: str,
    req: TelegramTestRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TelegramTestResponse:
    """Test Telegram bot connection and chat access."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    try:
        from app.crypto import decrypt_credential
        from app.services.telegram import TelegramNotificationService

        bot_token = decrypt_credential(req.bot_token_encrypted)
        service = TelegramNotificationService(bot_token, req.chat_id)
        success, message = await service.test_connection()

        return TelegramTestResponse(
            success=success,
            message=message,
            bot_username=message.split("@")[-1].split()[0] if "@" in message else None if success else None,
        )
    except Exception as e:
        return TelegramTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}",
        )


@router.patch("/subscriptions/{subscription_id}/telegram/config")
async def update_telegram_config(
    subscription_id: str,
    req: TelegramConfigUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    """Update Telegram notification configuration."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Initialize telegram_config if not exists
    if subscription.telegram_config is None:
        subscription.telegram_config = {}

    # Update fields
    if req.bot_token_encrypted is not None:
        subscription.telegram_config["bot_token"] = req.bot_token_encrypted
    if req.chat_id is not None:
        subscription.telegram_config["chat_id"] = req.chat_id
    if req.enabled is not None:
        subscription.telegram_config["enabled"] = req.enabled
    if req.notify_on_signal is not None:
        subscription.telegram_config["notify_on_signal"] = req.notify_on_signal
    if req.notify_on_execution is not None:
        subscription.telegram_config["notify_on_execution"] = req.notify_on_execution
    if req.notify_on_error is not None:
        subscription.telegram_config["notify_on_error"] = req.notify_on_error

    # Clear error on update
    subscription.telegram_notification_error = None

    db.commit()

    template = db.query(StrategyTemplate).filter_by(id=subscription.template_id).first()
    return SubscriptionResponse(**subscription_to_response(subscription, template))


@router.delete("/subscriptions/{subscription_id}/telegram/config")
async def delete_telegram_config(
    subscription_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    """Delete Telegram notification configuration."""
    user = get_current_user(request, db)

    subscription = db.query(StrategySubscription).filter_by(
        id=subscription_id,
        user_id=user.id,
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    subscription.telegram_config = None
    subscription.telegram_notification_error = None

    db.commit()

    template = db.query(StrategyTemplate).filter_by(id=subscription.template_id).first()
    return SubscriptionResponse(**subscription_to_response(subscription, template))
