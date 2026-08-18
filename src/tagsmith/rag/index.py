"""Helpers to index labeled messages into the RAG example store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlmodel import Session, col, select

from tagsmith.config import Settings
from tagsmith.db.models import ClassificationRecord, Message, MessageState, SyncState, utcnow
from tagsmith.gmail.parser import NormalizedEmail
from tagsmith.rag.embedder import build_embedder
from tagsmith.rag.store import ExampleStore, RagExample, example_text_from_email
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


@dataclass
class RagCatchupResult:
    indexed: int = 0
    removed: int = 0
    total: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"indexed": self.indexed, "removed": self.removed, "total": self.total}


def make_store(session: Session, settings: Settings) -> ExampleStore:
    return ExampleStore(session, build_embedder(dim=settings.rag_embedding_dim))


def index_normalized(
    store: ExampleStore,
    email: NormalizedEmail,
    *,
    label_key: str,
) -> None:
    meta = example_text_from_email(
        sender=email.sender,
        subject=email.subject,
        body_text=email.body_text,
    )
    store.upsert(
        gmail_id=email.gmail_id,
        label_key=label_key,
        sender=meta["sender"],
        subject=meta["subject"],
        body_excerpt=meta["body_excerpt"],
    )
    log.info("rag.index", gmail_id=email.gmail_id, label_key=label_key)


def unindex_gmail_id(session: Session, settings: Settings, gmail_id: str) -> None:
    """Drop a message from the few-shot store (user removed the label, etc.)."""
    if not settings.enable_rag:
        return
    make_store(session, settings).delete(gmail_id)
    log.info("rag.unindex", gmail_id=gmail_id)


def _label_for_message(session: Session, message: Message) -> str | None:
    label = message.applied_label_key
    if label:
        return label
    records = list(
        session.exec(
            select(ClassificationRecord).where(ClassificationRecord.gmail_id == message.gmail_id)
        ).all()
    )
    records.sort(key=lambda r: r.id or 0, reverse=True)
    rec = records[0] if records else None
    return rec.final_key if rec else None


def _upsert_message_example(
    session: Session,
    store: ExampleStore,
    message: Message,
    label: str,
) -> None:
    payload = dict(message.payload_json or {})
    meta = example_text_from_email(
        sender=str(payload.get("sender") or message.sender),
        subject=str(payload.get("subject") or message.subject),
        body_text=str(payload.get("body_text") or ""),
    )
    store.upsert(
        gmail_id=message.gmail_id,
        label_key=label,
        sender=meta["sender"],
        subject=meta["subject"],
        body_excerpt=meta["body_excerpt"],
    )


def reindex_from_db(session: Session, settings: Settings) -> int:
    """Rebuild RAG examples from labeled messages / final classifications."""
    store = make_store(session, settings)
    store.clear()
    indexed = 0
    labeled = list(
        session.exec(
            select(Message).where(
                Message.state == MessageState.LABELED,
                col(Message.applied_label_id).is_not(None),
            )
        ).all()
    )
    for message in labeled:
        label = _label_for_message(session, message)
        if not label:
            continue
        _upsert_message_example(session, store, message, label)
        indexed += 1
    log.info("rag.reindex_done", indexed=indexed)
    return indexed


def catchup_from_db(session: Session, settings: Settings) -> RagCatchupResult:
    """Index missing LABELED rows and drop examples that are no longer labeled.

    Incremental (does not wipe the store). Safe to run on every scheduler tick.
    """
    result = RagCatchupResult()
    if not settings.enable_rag:
        return result
    store = make_store(session, settings)
    labeled = list(
        session.exec(
            select(Message).where(
                Message.state == MessageState.LABELED,
                col(Message.applied_label_id).is_not(None),
            )
        ).all()
    )
    wanted: dict[str, tuple[Message, str]] = {}
    for message in labeled:
        label = _label_for_message(session, message)
        if label:
            wanted[message.gmail_id] = (message, label)

    existing = list(session.exec(select(RagExample)).all())
    existing_by_id = {row.gmail_id: row for row in existing}

    for gmail_id in existing_by_id:
        if gmail_id not in wanted:
            store.delete(gmail_id)
            result.removed += 1

    for gmail_id, (message, label) in wanted.items():
        row = existing_by_id.get(gmail_id)
        if row is not None and row.label_key == label:
            continue
        _upsert_message_example(session, store, message, label)
        result.indexed += 1

    result.total = store.count()
    persist_catchup(session, result)
    log.info("rag.catchup", **result.as_dict())
    return result


def persist_catchup(session: Session, result: RagCatchupResult) -> SyncState:
    state = session.get(SyncState, 1)
    if state is None:
        state = SyncState(id=1)
        session.add(state)
    state.last_rag_catchup_at = utcnow()
    state.last_rag_indexed = result.indexed
    state.last_rag_removed = result.removed
    state.updated_at = utcnow()
    session.commit()
    session.refresh(state)
    return state


def rag_status_payload(session: Session, settings: Settings) -> dict[str, Any]:
    count = make_store(session, settings).count() if settings.enable_rag else 0
    state = session.get(SyncState, 1)
    catchup_at: datetime | None = state.last_rag_catchup_at if state else None
    return {
        "enable_rag": settings.enable_rag,
        "rag_example_count": count,
        "rag_example_k": settings.rag_example_k,
        "last_rag_catchup_at": catchup_at.isoformat() if catchup_at else None,
        "last_rag_indexed": state.last_rag_indexed if state else None,
        "last_rag_removed": state.last_rag_removed if state else None,
        "background_sync": settings.enable_background_sync,
        "background_sync_apply": settings.background_sync_apply,
        "schedule_interval_seconds": settings.schedule_interval_seconds,
    }
