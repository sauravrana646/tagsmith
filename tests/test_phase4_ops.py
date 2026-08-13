"""Phase 4 continuous sync / watch / scheduler tests."""

from __future__ import annotations

import pytest
from sqlmodel import Session
from tests.fixtures.messages import PAYMENT_ALERT, SECURITY_ALERT

from tagsmith.config import Settings
from tagsmith.db.models import SyncState
from tagsmith.gmail.fake import FakeGmail
from tagsmith.scheduler import run_schedule_tick
from tagsmith.services.sync import SyncService
from tagsmith.services.watch_ops import WatchOps


@pytest.mark.asyncio
async def test_sync_incremental_processes_history_ids(
    session: Session,
    settings: Settings,
) -> None:
    gmail = FakeGmail(messages=[PAYMENT_ALERT, SECURITY_ALERT])
    gmail.history_id = "10"
    # Bootstrap cursor, then queue a change after that cursor.
    service = SyncService(session, gmail, settings)
    state = service.ensure_history_cursor()
    assert state.history_id == "10"
    gmail.history_events["10"] = [str(PAYMENT_ALERT["id"])]

    result = await service.sync_incremental(limit=10, apply=False)
    assert result.counts.fetched == 1
    assert result.dry_run is True
    refreshed = session.get(SyncState, 1)
    assert refreshed is not None
    assert refreshed.history_id is not None
    assert refreshed.last_incremental_at is not None


@pytest.mark.asyncio
async def test_full_sync_anchors_history_cursor(
    session: Session,
    settings: Settings,
    fake_gmail: FakeGmail,
) -> None:
    service = SyncService(session, fake_gmail, settings)
    result = await service.sync(limit=5, apply=False)
    assert result.counts.fetched >= 1
    state = session.get(SyncState, 1)
    assert state is not None
    assert state.history_id == fake_gmail.history_id


def test_watch_start_and_stop(session: Session, settings: Settings) -> None:
    settings = settings.model_copy(update={"pubsub_topic": "projects/demo/topics/tagsmith"})
    gmail = FakeGmail()
    ops = WatchOps(session, gmail, settings)
    status = ops.start_or_renew()
    assert status.pubsub_topic == "projects/demo/topics/tagsmith"
    assert status.watch_expiration_ms is not None
    assert len(gmail.watch_calls) == 1
    stopped = ops.stop()
    assert gmail.stop_watch_calls == 1
    assert stopped.watch_expiration_ms is None


@pytest.mark.asyncio
async def test_schedule_tick_incremental(
    session: Session,
    settings: Settings,
) -> None:
    settings = settings.model_copy(update={"pubsub_topic": "projects/demo/topics/tagsmith"})
    gmail = FakeGmail(messages=[PAYMENT_ALERT])
    gmail.history_id = "1"
    gmail.history_events["1"] = [str(PAYMENT_ALERT["id"])]
    # Seed cursor
    SyncService(session, gmail, settings).ensure_history_cursor()
    tick = await run_schedule_tick(session, gmail, settings, apply=False, renew_watch=True)
    assert tick.sync is not None
    assert tick.watch is not None
    assert tick.rag is not None
    assert tick.errors == []


@pytest.mark.asyncio
async def test_schedule_tick_catchup_without_gmail(
    session: Session,
    settings: Settings,
) -> None:
    from tagsmith.db.models import Message, MessageState
    from tagsmith.rag.index import make_store

    session.add(
        Message(
            gmail_id="solo",
            thread_id="t-solo",
            sender="a@b.com",
            subject="OTP 123",
            state=MessageState.LABELED,
            applied_label_key="otp-verification",
            payload_json={"sender": "a@b.com", "subject": "OTP 123", "body_text": "code"},
        )
    )
    session.commit()
    tick = await run_schedule_tick(session, None, settings, apply=False, renew_watch=False)
    assert tick.sync is None
    assert tick.watch is None
    assert tick.rag is not None
    assert tick.rag.indexed == 1
    assert tick.errors == []
    assert make_store(session, settings).count() == 1
