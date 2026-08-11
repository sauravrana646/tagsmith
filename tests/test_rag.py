"""Phase 3 RAG unit tests (offline hashing embedder)."""

from __future__ import annotations

from tagsmith.config import Settings
from tagsmith.db.session import init_db
from tagsmith.rag.embedder import HashingEmbedder, cosine_similarity
from tagsmith.rag.index import make_store
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
