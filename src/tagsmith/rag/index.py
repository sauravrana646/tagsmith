"""Helpers to index labeled messages into the RAG example store."""

from __future__ import annotations

from sqlmodel import Session, select

from tagsmith.config import Settings
from tagsmith.db.models import ClassificationRecord, Message, MessageState
from tagsmith.gmail.parser import NormalizedEmail
from tagsmith.rag.embedder import build_embedder
from tagsmith.rag.store import ExampleStore, example_text_from_email
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


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


def reindex_from_db(session: Session, settings: Settings) -> int:
    """Rebuild RAG examples from labeled messages / final classifications."""
    store = make_store(session, settings)
    store.clear()
    indexed = 0
    messages = list(
        session.exec(select(Message).where(Message.state == MessageState.LABELED)).all()
    )
    for message in messages:
        label = message.applied_label_key
        if not label:
            # Fall back to latest final_key on classifications.
            records = list(
                session.exec(
                    select(ClassificationRecord).where(
                        ClassificationRecord.gmail_id == message.gmail_id
                    )
                ).all()
            )
            records.sort(key=lambda r: r.id or 0, reverse=True)
            rec = records[0] if records else None
            label = rec.final_key if rec else None
        if not label:
            continue
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
        indexed += 1
    log.info("rag.reindex_done", indexed=indexed)
    return indexed
