from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.deps import get_db
from app.schemas import CheckoutSessionResponse, SubscriptionStatusResponse
from app.settings import settings
from control_plane.models import StrategyMember, User

router = APIRouter()


def _init_stripe() -> None:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="stripe_not_configured")
    stripe.api_key = settings.stripe_secret_key


def _strategy_count(db: Session, user: User) -> int:
    return (
        db.execute(
            select(func.count(StrategyMember.id)).where(StrategyMember.user_id == user.id)
        )
        .scalar_one()
    )


@router.post("/billing/checkout", response_model=CheckoutSessionResponse)
def create_checkout_session(
    request: Request,
    db: Session = Depends(get_db),
) -> CheckoutSessionResponse:
    user = get_current_user(request, db)
    _init_stripe()

    if not settings.stripe_price_id:
        raise HTTPException(status_code=500, detail="stripe_price_missing")

    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.name,
            metadata={"user_id": user.id},
        )
        customer_id = customer.id
        user.stripe_customer_id = customer_id
        db.commit()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=f"{settings.public_base_url}/?billing=success",
        cancel_url=f"{settings.public_base_url}/?billing=cancel",
        allow_promotion_codes=True,
        client_reference_id=user.id,
    )

    return CheckoutSessionResponse(url=session.url)


@router.get("/billing/status", response_model=SubscriptionStatusResponse)
def subscription_status(
    request: Request,
    db: Session = Depends(get_db),
) -> SubscriptionStatusResponse:
    user = get_current_user(request, db)
    strategies_used = _strategy_count(db, user)
    is_active = bool(user.subscription_status and user.subscription_status.lower() in {"active", "trialing"})
    if is_active and user.subscription_current_period_end:
        period_end = user.subscription_current_period_end
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        is_active = period_end > datetime.now(timezone.utc)

    return SubscriptionStatusResponse(
        is_active=is_active,
        status=user.subscription_status,
        plan_id=user.subscription_plan_id,
        current_period_end=user.subscription_current_period_end,
        free_strategy_limit=settings.free_strategy_limit,
        strategies_used=strategies_used,
    )


@router.post("/billing/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    _init_stripe()
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        if settings.stripe_webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
        else:
            import json
            event = stripe.Event.construct_from(json.loads(payload.decode("utf-8")), stripe.api_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"stripe_webhook_error:{exc}")

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        customer_id = data_object.get("customer")
        subscription_id = data_object.get("subscription")
        user_id = data_object.get("client_reference_id")
        user = None
        if user_id:
            user = db.get(User, user_id)
        if user is None and customer_id:
            user = db.execute(select(User).where(User.stripe_customer_id == customer_id)).scalar_one_or_none()
        if user:
            user.stripe_customer_id = customer_id
            user.stripe_subscription_id = subscription_id
            user.subscription_status = "active"
            db.commit()

    if event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription = data_object
        customer_id = subscription.get("customer")
        status = subscription.get("status")
        current_period_end = subscription.get("current_period_end")
        price_id: Optional[str] = None
        items = subscription.get("items", {}).get("data", []) if subscription else []
        if items:
            price_id = items[0].get("price", {}).get("id")

        user = db.execute(select(User).where(User.stripe_customer_id == customer_id)).scalar_one_or_none()
        if user:
            user.subscription_status = status
            user.subscription_plan_id = price_id
            if current_period_end:
                user.subscription_current_period_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
            if event_type == "customer.subscription.deleted":
                user.stripe_subscription_id = None
            db.commit()

    return {"ok": True}
