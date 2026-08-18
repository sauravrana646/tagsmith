"""SQLite-backed vector store of labeled email examples."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Session, SQLModel, select

from tagsmith.classify.schema import LabeledEmail
from tagsmith.rag.embedder import Embedder, cosine_similarity


def utcnow() -> datetime:
    return datetime.now(UTC)


class RagExample(SQLModel, table=True):
    """One labeled email embedding used as a few-shot example."""

    __tablename__ = "rag_examples"
    __table_args__ = (UniqueConstraint("gmail_id", name="uq_rag_gmail_id"),)

    id: int | None = Field(default=None, primary_key=True)
    gmail_id: str = Field(index=True)
    label_key: str = Field(index=True)
    sender: str = ""
    subject: str = ""
    body_excerpt: str = ""
    embedding: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    tenant_id: int = Field(default=1, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ExampleStore:
    def __init__(self, session: Session, embedder: Embedder) -> None:
        self.session = session
        self.embedder = embedder

    def count(self) -> int:
        return len(list(self.session.exec(select(RagExample.id)).all()))

    def upsert(
        self,
        *,
        gmail_id: str,
        label_key: str,
        sender: str,
        subject: str,
        body_excerpt: str,
    ) -> RagExample:
        text = self._example_text(sender=sender, subject=subject, body_excerpt=body_excerpt)
        embedding = self.embedder.embed(text)
        existing = self.session.exec(
            select(RagExample).where(RagExample.gmail_id == gmail_id)
        ).first()
        if existing is None:
            row = RagExample(
                gmail_id=gmail_id,
                label_key=label_key,
                sender=sender,
                subject=subject,
                body_excerpt=body_excerpt,
                embedding=embedding,
            )
            self.session.add(row)
        else:
            existing.label_key = label_key
            existing.sender = sender
            existing.subject = subject
            existing.body_excerpt = body_excerpt
            existing.embedding = embedding
            existing.updated_at = utcnow()
            row = existing
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, gmail_id: str) -> None:
        row = self.session.exec(select(RagExample).where(RagExample.gmail_id == gmail_id)).first()
        if row is not None:
            self.session.delete(row)
            self.session.commit()

    def clear(self) -> int:
        rows = list(self.session.exec(select(RagExample)).all())
        n = len(rows)
        for row in rows:
            self.session.delete(row)
        self.session.commit()
        return n

    def query_similar(
        self,
        text: str,
        *,
        k: int = 5,
        exclude_gmail_ids: set[str] | None = None,
    ) -> list[tuple[LabeledEmail, float]]:
        if k <= 0:
            return []
        exclude = exclude_gmail_ids or set()
        query_vec = self.embedder.embed(text)
        rows = list(self.session.exec(select(RagExample)).all())
        scored: list[tuple[RagExample, float]] = []
        for row in rows:
            if row.gmail_id in exclude:
                continue
            if not row.embedding:
                continue
            scored.append((row, cosine_similarity(query_vec, list(row.embedding))))
        scored.sort(key=lambda item: item[1], reverse=True)
        out: list[tuple[LabeledEmail, float]] = []
        for row, score in scored[:k]:
            out.append(
                (
                    LabeledEmail(
                        subject=row.subject,
                        sender=row.sender,
                        body_excerpt=row.body_excerpt,
                        label_key=row.label_key,
                    ),
                    score,
                )
            )
        return out

    @staticmethod
    def _example_text(*, sender: str, subject: str, body_excerpt: str) -> str:
        return f"From: {sender}\nSubject: {subject}\n{body_excerpt}"


def example_text_from_email(
    *,
    sender: str,
    subject: str,
    body_text: str,
    body_chars: int = 400,
) -> dict[str, Any]:
    excerpt = body_text[:body_chars]
    return {
        "sender": sender,
        "subject": subject,
        "body_excerpt": excerpt,
        "text": ExampleStore._example_text(sender=sender, subject=subject, body_excerpt=excerpt),
    }
