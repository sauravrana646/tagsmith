"""Periodic sync + watch renewal + RAG catch-up (Phase 4)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from tagsmith.config import Settings
from tagsmith.db.models import utcnow
from tagsmith.gmail.protocol import GmailGateway
from tagsmith.rag.index import RagCatchupResult, catchup_from_db
from tagsmith.services.sync import SyncResult, SyncService
from tagsmith.services.watch_ops import WatchOps, WatchStatus
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


@dataclass
class ScheduleTickResult:
    sync: SyncResult | None
    watch: WatchStatus | None
    rag: RagCatchupResult | None
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sync": None
            if self.sync is None
            else {
                "run_id": self.sync.run_id,
                "dry_run": self.sync.dry_run,
                "counts": self.sync.counts.as_dict(),
            },
            "watch": None if self.watch is None else self.watch.as_dict(),
            "rag": None if self.rag is None else self.rag.as_dict(),
            "errors": list(self.errors),
        }


async def run_schedule_tick(
    session: Session,
    gmail: GmailGateway | None,
    settings: Settings,
    *,
    apply: bool = False,
    renew_watch: bool = True,
    incremental: bool = True,
    limit: int = 100,
) -> ScheduleTickResult:
    """One scheduler cycle: optional incremental sync, watch renew, RAG catch-up."""
    errors: list[str] = []
    sync_result: SyncResult | None = None
    watch_status: WatchStatus | None = None
    rag_result: RagCatchupResult | None = None

    if gmail is not None:
        sync = SyncService(session, gmail, settings)
        try:
            if incremental:
                sync_result = await sync.sync_incremental(limit=limit, apply=apply)
            else:
                sync_result = await sync.sync(limit=limit, apply=apply)
        except Exception as exc:
            log.exception("schedule.sync_failed", error=str(exc))
            errors.append(f"sync: {exc}")

        if renew_watch and settings.pubsub_topic:
            watch = WatchOps(session, gmail, settings)
            status = watch.status()
            should_renew = True
            if status.watch_expiration_ms is not None:
                remaining_ms = status.watch_expiration_ms - int(utcnow().timestamp() * 1000)
                should_renew = remaining_ms < settings.watch_renew_hours * 3600 * 1000
            if should_renew:
                try:
                    watch_status = watch.start_or_renew()
                except Exception as exc:
                    log.exception("schedule.watch_failed", error=str(exc))
                    errors.append(f"watch: {exc}")
            else:
                watch_status = status
    else:
        log.info("schedule.skip_sync", reason="gmail_unavailable")

    try:
        rag_result = catchup_from_db(session, settings)
    except Exception as exc:
        log.exception("schedule.rag_catchup_failed", error=str(exc))
        errors.append(f"rag: {exc}")

    return ScheduleTickResult(sync=sync_result, watch=watch_status, rag=rag_result, errors=errors)


async def run_scheduler_loop(
    session_factory: Any,
    gmail_factory: Any,
    settings: Settings,
    *,
    apply: bool = False,
    interval_seconds: int | None = None,
    once: bool = False,
    incremental: bool = True,
) -> None:
    """Run forever (or once). session_factory/gmail_factory are zero-arg callables."""
    interval = interval_seconds or settings.schedule_interval_seconds
    while True:
        with session_factory() as session:
            gmail = gmail_factory()
            result = await run_schedule_tick(
                session,
                gmail,
                settings,
                apply=apply,
                incremental=incremental,
            )
            log.info("schedule.tick", **result.as_dict())
        if once:
            return
        await asyncio.sleep(interval)
