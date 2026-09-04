"""Admin API endpoints for managing strategy templates.

This router provides CRUD operations for platform administrators to:
- Create new strategy templates
- Update template metadata and code
- Delete templates
- Manage template visibility and features
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from control_plane.models import StrategyTemplate
from control_plane.enums import StrategyTemplateType
from app.deps import get_db
from app.admin import require_admin as require_admin_with_db

router = APIRouter()


# ============== Admin Authentication ==============


def require_admin(request: Request, db: Session) -> None:
    """Require admin access (temporary allowlist by email or API key)."""
    require_admin_with_db(request, db=db)


# ============== Request/Response Schemas ==============


class TemplateCreateRequest(BaseModel):
    """Request to create a new template."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=2000)
    template_type: StrategyTemplateType = Field(default=StrategyTemplateType.BUILTIN)
    author: str | None = Field(None, max_length=200)
    tags: list[str] = Field(default_factory=list)
    risk_level: str | None = Field(None, pattern="^(low|medium|high)$")
    trading_frequency: str | None = Field(None, pattern="^(low_frequency|intraday|high_frequency)$")
    complexity_score: int | None = Field(None, ge=1, le=5)
    min_capital_usdt: float | None = Field(None, ge=10)
    supported_exchanges: list[str] | None = Field(default_factory=list)
    supported_symbols: list[str] | None = Field(default_factory=list)

    # Strategy content
    prompt: str | None = Field(None, max_length=10000)
    config_snapshot: dict[str, Any] | None = Field(None)
    code_snapshot: dict[str, Any] | None = Field(None)

    is_public: bool = Field(default=True)
    is_featured: bool = Field(default=False)


class TemplateUpdateRequest(BaseModel):
    """Request to update a template."""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    author: str | None = Field(None, max_length=200)
    tags: list[str] | None = Field(None)
    risk_level: str | None = Field(None, pattern="^(low|medium|high)$")
    trading_frequency: str | None = Field(None, pattern="^(low_frequency|intraday|high_frequency)$")
    complexity_score: int | None = Field(None, ge=1, le=5)
    min_capital_usdt: float | None = Field(None, ge=10)
    supported_exchanges: list[str] | None = Field(None)
    supported_symbols: list[str] | None = Field(None)

    # Strategy content
    prompt: str | None = Field(None, max_length=10000)
    config_snapshot: dict[str, Any] | None = Field(None)
    code_snapshot: dict[str, Any] | None = Field(None)

    # Visibility
    is_public: bool | None = Field(None)
    is_featured: bool | None = Field(None)

    # Performance
    backtest_summary: dict[str, Any] | None = Field(None)


class TemplateAdminResponse(BaseModel):
    """Full template details for admin."""
    id: str
    name: str
    description: str | None
    template_type: str
    author: str | None
    tags: list[str] | None
    risk_level: str | None
    trading_frequency: str | None
    complexity_score: int | None
    min_capital_usdt: float | None
    supported_exchanges: list[str] | None
    supported_symbols: list[str] | None
    config_snapshot: dict[str, Any] | None
    prompt: str | None
    code_snapshot: dict[str, Any] | None
    version: int
    is_public: bool
    is_featured: bool
    subscriber_count: int
    backtest_summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime | None


class TemplateListAdminResponse(BaseModel):
    """Response for listing templates (admin view)."""
    total: int
    templates: list[TemplateAdminResponse]


# ============== Helper Functions ==============


def _template_to_admin_response(template: StrategyTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "template_type": template.template_type,
        "author": template.author,
        "tags": template.tags or [],
        "risk_level": template.risk_level,
        "trading_frequency": template.trading_frequency,
        "complexity_score": template.complexity_score,
        "min_capital_usdt": float(template.min_capital_usdt) if template.min_capital_usdt else None,
        "supported_exchanges": template.supported_exchanges or [],
        "supported_symbols": template.supported_symbols or [],
        "config_snapshot": template.config_snapshot,
        "prompt": template.prompt,
        "code_snapshot": template.code_snapshot,
        "version": template.version,
        "is_public": template.is_public,
        "is_featured": template.is_featured,
        "subscriber_count": template.subscriber_count,
        "backtest_summary": template.backtest_summary,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "last_synced_at": template.last_synced_at,
    }


# ============== API Endpoints ==============


@router.post("/admin/templates", response_model=TemplateAdminResponse)
async def create_template(
    req: TemplateCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TemplateAdminResponse:
    """Create a new strategy template (admin only)."""
    require_admin(request, db)

    # Check for duplicate name
    existing = db.query(StrategyTemplate).filter_by(name=req.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Template with this name already exists")

    template = StrategyTemplate(
        id=str(uuid.uuid4()),
        name=req.name,
        description=req.description,
        template_type=req.template_type.value,
        author=req.author,
        tags=req.tags,
        risk_level=req.risk_level,
        trading_frequency=req.trading_frequency,
        complexity_score=req.complexity_score,
        min_capital_usdt=req.min_capital_usdt,
        supported_exchanges=req.supported_exchanges,
        supported_symbols=req.supported_symbols,
        prompt=req.prompt,
        config_snapshot=req.config_snapshot,
        code_snapshot=req.code_snapshot,
        is_public=req.is_public,
        is_featured=req.is_featured,
        version=1,
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return TemplateAdminResponse(**_template_to_admin_response(template))


@router.get("/admin/templates", response_model=TemplateListAdminResponse)
async def list_templates_admin(
    template_type: StrategyTemplateType | None = None,
    is_public: bool | None = None,
    is_featured: bool | None = None,
    risk_level: str | None = None,
    trading_frequency: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    request: Request = None,
    db: Session = Depends(get_db),
) -> TemplateListAdminResponse:
    """List all templates (admin view, includes private templates)."""
    require_admin(request, db)

    limit = min(limit, 100)

    query = db.query(StrategyTemplate)

    # Filters
    if template_type:
        query = query.filter(StrategyTemplate.template_type == template_type.value)
    if is_public is not None:
        query = query.filter(StrategyTemplate.is_public == is_public)
    if is_featured is not None:
        query = query.filter(StrategyTemplate.is_featured == is_featured)
    if risk_level:
        query = query.filter(StrategyTemplate.risk_level == risk_level)
    if trading_frequency:
        query = query.filter(StrategyTemplate.trading_frequency == trading_frequency)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (StrategyTemplate.name.ilike(search_term)) |
            (StrategyTemplate.description.ilike(search_term))
        )

    total = query.count()
    templates = query.order_by(
        StrategyTemplate.created_at.desc()
    ).offset(offset).limit(limit).all()

    return TemplateListAdminResponse(
        total=total,
        templates=[TemplateAdminResponse(**_template_to_admin_response(t)) for t in templates],
    )


@router.get("/admin/templates/{template_id}", response_model=TemplateAdminResponse)
async def get_template_admin(
    template_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TemplateAdminResponse:
    """Get template details (admin view, includes private templates)."""
    require_admin(request, db)

    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateAdminResponse(**_template_to_admin_response(template))


@router.patch("/admin/templates/{template_id}", response_model=TemplateAdminResponse)
async def update_template(
    template_id: str,
    req: TemplateUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TemplateAdminResponse:
    """Update a template (admin only)."""
    require_admin(request, db)

    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Update fields
    if req.name is not None:
        template.name = req.name
    if req.description is not None:
        template.description = req.description
    if req.author is not None:
        template.author = req.author
    if req.tags is not None:
        template.tags = req.tags
    if req.risk_level is not None:
        template.risk_level = req.risk_level
    if req.trading_frequency is not None:
        template.trading_frequency = req.trading_frequency
    if req.complexity_score is not None:
        template.complexity_score = req.complexity_score
    if req.min_capital_usdt is not None:
        template.min_capital_usdt = req.min_capital_usdt
    if req.supported_exchanges is not None:
        template.supported_exchanges = req.supported_exchanges
    if req.supported_symbols is not None:
        template.supported_symbols = req.supported_symbols
    if req.prompt is not None:
        template.prompt = req.prompt
    if req.config_snapshot is not None:
        template.config_snapshot = req.config_snapshot
    if req.code_snapshot is not None:
        template.code_snapshot = req.code_snapshot
    if req.is_public is not None:
        template.is_public = req.is_public
    if req.is_featured is not None:
        template.is_featured = req.is_featured
    if req.backtest_summary is not None:
        template.backtest_summary = req.backtest_summary

    # Increment version on content changes
    if any([req.prompt is not None, req.code_snapshot is not None]):
        template.version += 1
        template.last_synced_at = datetime.now(timezone.utc)

    template.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(template)

    return TemplateAdminResponse(**_template_to_admin_response(template))


@router.delete("/admin/templates/{template_id}")
async def delete_template(
    template_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Delete a template (admin only).

    This will also delete all subscriptions to this template.
    """
    require_admin(request, db)

    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    db.delete(template)
    db.commit()

    return {"message": f"Template '{template.name}' has been deleted"}
