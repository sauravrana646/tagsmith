"""Sync API endpoints (Phase 5 wraps Phase 4 services)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from tagsmith.api.deps import gmail_dep, session_dep, settings_dep
from tagsmith.config import Settings
from tagsmith.gmail.client import GmailClient
from tagsmith.services.sync import SyncService
from tagsmith.services.watch_ops import WatchOps

router = APIRouter(prefix="/api/sync", tags=["sync"])


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
) -> dict[str, Any]:
    service = SyncService(session, gmail, settings)
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
    topic = body.topic if body else None
    return WatchOps(session, gmail, settings).start_or_renew(topic_name=topic).as_dict()
