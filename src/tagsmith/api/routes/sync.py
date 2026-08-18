"""Sync API endpoints (Phase 5 wraps Phase 4 services)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from tagsmith.api.deps import gmail_dep, require_session, session_dep, settings_dep
from tagsmith.api.rate_limit import check_sync_rate
from tagsmith.config import Settings
from tagsmith.db.models import Tenant
from tagsmith.gmail.client import GmailClient
from tagsmith.services.sync import SyncService
from tagsmith.services.sync_lock import SyncInProgress, sync_flight
from tagsmith.services.watch_ops import WatchOps

router = APIRouter(
    prefix="/api/sync",
    tags=["sync"],
    dependencies=[Depends(require_session)],
)


class SyncBody(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    apply: bool = False
    reprocess: bool = False
    incremental: bool = True


@router.post("/run")
async def run_sync(
    body: SyncBody,
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
    gmail: GmailClient = Depends(gmail_dep),
    tenant: Tenant = Depends(require_session),
) -> dict[str, Any]:
    tenant_id = tenant.id or 1
    daily = 2000 if tenant.plan == "pro" else settings.default_sync_per_day
    if not check_sync_rate(tenant_id, limit_per_day=daily):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    service = SyncService(session, gmail, settings, tenant_id=tenant_id)
    try:
        with sync_flight(blocking=False):
            if body.incremental:
                result = await service.sync_incremental(
                    limit=body.limit,
                    apply=body.apply,
                    reprocess=body.reprocess,
                )
            else:
                result = await service.sync(
                    limit=body.limit,
                    apply=body.apply,
                    reprocess=body.reprocess,
                )
    except SyncInProgress as exc:
        raise HTTPException(status_code=409, detail="already_running") from exc
    return {
        "run_id": result.run_id,
        "dry_run": result.dry_run,
        "counts": result.counts.as_dict(),
        "decisions": result.decisions,
    }


@router.get("/state")
def sync_state(
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
    gmail: GmailClient = Depends(gmail_dep),
) -> dict[str, Any]:
    service = SyncService(session, gmail, settings)
    state = service.get_sync_state()
    return {
        "history_id": state.history_id,
        "last_incremental_at": (
            state.last_incremental_at.isoformat() if state.last_incremental_at else None
        ),
        "watch_expiration_ms": state.watch_expiration_ms,
        "pubsub_topic": state.pubsub_topic,
    }


class WatchBody(BaseModel):
    topic: str | None = None


@router.get("/watch")
def watch_status(
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
    gmail: GmailClient = Depends(gmail_dep),
) -> dict[str, Any]:
    return WatchOps(session, gmail, settings).status().as_dict()


@router.post("/watch/renew")
def watch_renew(
    body: WatchBody | None = None,
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
    gmail: GmailClient = Depends(gmail_dep),
) -> dict[str, Any]:
    configured = settings.pubsub_topic
    if body and body.topic and configured and body.topic != configured:
        raise HTTPException(status_code=400, detail="topic does not match configured pubsub_topic")
    topic = configured
    if not topic:
        raise HTTPException(status_code=400, detail="TAGSMITH_PUBSUB_TOPIC is not configured")
    return WatchOps(session, gmail, settings).start_or_renew(topic_name=topic).as_dict()
