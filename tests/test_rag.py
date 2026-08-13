"""Phase 3 RAG unit tests (offline hashing embedder)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tagsmith.config import Settings
from tagsmith.db.models import Message, MessageState, SyncState
from tagsmith.db.session import get_session, init_db, reset_engine
from tagsmith.rag.embedder import HashingEmbedder, cosine_similarity
from tagsmith.rag.index import catchup_from_db, make_store, rag_status_payload
from tagsmith.rag.retriever import Retriever, format_category_hints
from tagsmith.rag.store import example_text_from_email


def test_hashing_embedder_normalized_and_stable() -> None:
    emb = HashingEmbedder(dim=64)
    a = emb.embed("From: a@b.com Subject: OTP code 123")
    b = emb.embed("From: a@b.com Subject: OTP code 123")
    c = emb.embed("Flash sale 40% off ends tonight")
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_example_store_query_similar(settings: Settings, session) -> None:
    init_db(settings)
    store = make_store(session, settings)
    store.upsert(
        gmail_id="g1",
        label_key="otp-verification",
        sender="GitHub <noreply@github.com>",
        subject="Your verification code",
        body_excerpt="Your verification code is 482193",
    )
    store.upsert(
        gmail_id="g2",
        label_key="promotion",
        sender="Shop <deals@merchant.example>",
        subject="Flash sale 40% off",
        body_excerpt="Save with code SAVE40",
    )
    hits = store.query_similar(
        "From: GitHub\nSubject: authentication code\nUse 111222 to sign in",
        k=1,
    )
    assert len(hits) == 1
    assert hits[0][0].label_key == "otp-verification"


def test_retriever_category_hints(settings: Settings, session) -> None:
    init_db(settings)
    store = make_store(session, settings)
    retriever = Retriever(store, store.embedder, example_k=2, category_k=2)
    ctx = retriever.retrieve("Your W-2 wage and tax statement is ready")
    assert len(ctx.category_hints) == 2
    assert "tax-document" in "".join(ctx.category_hints)
    assert format_category_hints(ctx.category_hints).startswith("Closest taxonomy")


def test_example_text_from_email_truncates() -> None:
    meta = example_text_from_email(
        sender="a@b.com",
        subject="Hi",
        body_text="x" * 1000,
        body_chars=50,
    )
    assert len(meta["body_excerpt"]) == 50


def test_rag_eval_bootstrap_creates_table(settings: Settings, tmp_path: Path) -> None:
    """Regression: create_all must expose rag_examples before upsert."""
    reset_engine()
    db = tmp_path / "rag.db"
    s = settings.model_copy(update={"database_url": f"sqlite:///{db}"})
    init_db(s)
    with get_session(s) as session:
        store = make_store(session, s)
        store.upsert(
            gmail_id="x",
            label_key="otp-verification",
            sender="a",
            subject="code",
            body_excerpt="123",
        )
        assert store.count() == 1
    reset_engine()


def _labeled_message(
    session: Any,
    *,
    gmail_id: str,
    label_key: str,
    state: MessageState = MessageState.LABELED,
    subject: str = "Hello",
) -> Message:
    msg = Message(
        gmail_id=gmail_id,
        thread_id=f"t-{gmail_id}",
        sender="a@b.com",
        subject=subject,
        state=state,
        applied_label_key=label_key if state == MessageState.LABELED else None,
        payload_json={"sender": "a@b.com", "subject": subject, "body_text": "body"},
    )
    session.add(msg)
    session.commit()
    return msg


def test_catchup_indexes_labeled_and_drops_stale(settings: Settings, session: Any) -> None:
    keep = _labeled_message(session, gmail_id="keep-1", label_key="otp-verification")
    _labeled_message(
        session,
        gmail_id="held-1",
        label_key="promotion",
        state=MessageState.HELD,
        subject="held",
    )
    store = make_store(session, settings)
    store.upsert(
        gmail_id="stale-1",
        label_key="newsletter",
        sender="x@y.com",
        subject="old",
        body_excerpt="gone",
    )
    result = catchup_from_db(session, settings)
    assert result.indexed >= 1
    assert result.removed == 1
    assert result.total == 1
    remaining = make_store(session, settings)
    hits = remaining.query_similar("From: a@b.com Subject: Hello body", k=3)
    assert any(h[0].label_key == "otp-verification" for h in hits)
    assert remaining.count() == 1
    assert session.get(SyncState, 1) is not None
    assert session.get(SyncState, 1).last_rag_indexed == result.indexed
    assert keep.gmail_id == "keep-1"


def test_catchup_updates_changed_label(settings: Settings, session: Any) -> None:
    _labeled_message(session, gmail_id="m1", label_key="promotion")
    catchup_from_db(session, settings)
    msg = session.get(Message, "m1")
    assert msg is not None
    msg.applied_label_key = "newsletter"
    session.commit()
    result = catchup_from_db(session, settings)
    assert result.indexed == 1
    assert result.removed == 0
    store = make_store(session, settings)
    hits = store.query_similar("From: a@b.com Subject: Hello", k=1)
    assert hits[0][0].label_key == "newsletter"


def test_rag_status_payload(settings: Settings, session: Any) -> None:
    payload = rag_status_payload(session, settings)
    assert payload["enable_rag"] is True
    assert payload["rag_example_count"] == 0
    assert payload["background_sync"] is False
    assert payload["last_rag_catchup_at"] is None
