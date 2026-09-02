"""Membership endpoints for a strategy."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.enums import StrategyRole
from control_plane.models import StrategyMember, User

from app.auth import require_strategy_member
from app.deps import get_db
from app.schemas import StrategyMemberCreateRequest, StrategyMemberResponse

router = APIRouter()


@router.get("/strategies/{strategy_id}/members", response_model=list[StrategyMemberResponse])
def list_strategy_members(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> list[StrategyMemberResponse]:
    require_strategy_member(request, db, strategy_id)
    members = (
        db.execute(
            select(StrategyMember)
            .where(StrategyMember.strategy_id == strategy_id)
            .order_by(StrategyMember.created_at.asc())
        )
        .scalars()
        .all()
    )
    return members


@router.post("/strategies/{strategy_id}/members", response_model=StrategyMemberResponse)
def add_strategy_member(
    strategy_id: str,
    req: StrategyMemberCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> StrategyMemberResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN])

    target_user = None
    if req.user_id:
        target_user = db.get(User, req.user_id)
    elif req.email:
        target_user = db.execute(select(User).where(User.email == req.email)).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    existing = db.execute(
        select(StrategyMember)
        .where(StrategyMember.strategy_id == strategy_id)
        .where(StrategyMember.user_id == target_user.id)
    ).scalar_one_or_none()
    if existing:
        return existing

    member = StrategyMember(strategy_id=strategy_id, user_id=target_user.id, role=req.role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/strategies/{strategy_id}/members/{member_id}")
def remove_strategy_member(
    strategy_id: str,
    member_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN])

    member = db.get(StrategyMember, member_id)
    if member is None or member.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="member_not_found")

    db.delete(member)
    db.commit()
    return {"ok": True}
