"""In-process background sync + RAG catch-up for the API process."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from tagsmith.config import Settings
from tagsmith.db.session import get_session
from tagsmith.gmail.auth import AuthError
from tagsmith.gmail.client import GmailClient
from tagsmith.scheduler import run_schedule_tick
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


def start_background_loop(settings: Settings) -> asyncio.Task[None] | None:
    if not settings.enable_background_sync:
        log.info("background.disabled")
        return None
    log.info(
        "background.start",
        interval_seconds=settings.schedule_interval_seconds,
        apply=settings.background_sync_apply,
        enable_rag=settings.enable_rag,
    )
    return asyncio.create_task(_background_loop(settings), name="tagsmith-background")


async def stop_background_loop(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    log.info("background.stopped")


async def _background_loop(settings: Settings) -> None:
    interval = max(5, settings.schedule_interval_seconds)
    while True:
        try:
            with get_session(settings) as session:
                gmail = None
                try:
                    gmail = GmailClient.from_settings(settings, interactive=False)
                except AuthError:
                    log.info("background.no_gmail", hint="run tagsmith auth for mailbox sync")
                result = await run_schedule_tick(
                    session,
                    gmail,
                    settings,
                    apply=settings.background_sync_apply,
                    incremental=True,
                )
                log.info("background.tick", **result.as_dict())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("background.tick_failed")
        await asyncio.sleep(interval)
