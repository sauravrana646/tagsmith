"""Billing hooks (Phase 5). Stripe webhook receiver; checkout deferred to dashboard UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from tagsmith.api.deps import session_dep, settings_dep
from tagsmith.config import Settings
from tagsmith.db.models import BillingEvent, Tenant, utcnow
from tagsmith.telemetry import get_logger

router = APIRouter(prefix="/api/billing", tags=["billing"])
log = get_logger(__name__)


@router.get("/plans")
def list_plans() -> list[dict[str, Any]]:
    return [
        {
            "id": "free",
            "name": "Free",
            "price_usd": 0,
            "limits": {"sync_per_day": 50},
        },
        {
            "id": "pro",
            "name": "Pro",
            "price_usd": 12,
            "limits": {"sync_per_day": 2000},
        },
    ]


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, str]:
    """Accept Stripe events when TAGSMITH_STRIPE_WEBHOOK_SECRET is configured.

    Verifies signature when the Stripe SDK + secret are present; otherwise rejects.
    """
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe webhook not configured")
    payload = await request.body()
    try:
        import stripe
    except ImportError as exc:
        raise HTTPException(503, "stripe package not installed") from exc

    stripe.api_key = settings.stripe_api_key or None
    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.stripe_webhook_secret,
        )
    except Exception as exc:
        raise HTTPException(400, f"invalid stripe signature: {exc}") from exc

    event_id = str(event.get("id") or "")
    if event_id:
        existing = session.get(BillingEvent, event_id)
        if existing is not None:
            return {"status": "ok"}
        session.add(BillingEvent(event_id=event_id))

    event_type = event.get("type")
    data_object = (event.get("data") or {}).get("object") or {}
    customer_id = data_object.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    customer_id = str(customer_id or "") or None
    customer_email = data_object.get("customer_email") or data_object.get("receipt_email")

    tenant = None
    if customer_id:
        tenant = session.exec(
            select(Tenant).where(Tenant.stripe_customer_id == customer_id)
        ).first()
    if tenant is None and customer_email:
        tenant = session.exec(select(Tenant).where(Tenant.email == customer_email)).first()
        if tenant is not None and customer_id:
            tenant.stripe_customer_id = customer_id

    if event_type in {"checkout.session.completed", "customer.subscription.updated"}:
        if tenant:
            tenant.plan = "pro"
            tenant.updated_at = utcnow()
            session.commit()
            log.info("billing.plan_updated", tenant_id=tenant.id, plan="pro")
    elif event_type in {"customer.subscription.deleted"}:
        if tenant:
            tenant.plan = "free"
            tenant.updated_at = utcnow()
            session.commit()
    else:
        session.commit()
    return {"status": "ok"}
