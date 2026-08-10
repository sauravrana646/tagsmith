"""SQLModel tables for Tagsmith."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class CategoryStatus(StrEnum):
    ACTIVE = "active"
    PROPOSED = "proposed"
    REJECTED = "rejected"


class MessageState(StrEnum):
    PENDING = "pending"
    LABELED = "labeled"
    HELD = "held"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"
    USER_REMOVED = "user_removed"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ClassificationSource(StrEnum):
    RULE = "rule"
    LLM = "llm"
    RAG = "rag"
    HUMAN = "human"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHANGED = "changed"
    PROPOSED_NEW = "proposed_new"


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    key: str = Field(primary_key=True)
    gmail_label_id: str | None = Field(default=None, index=True)
    description: str
    exemplars: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: CategoryStatus = Field(default=CategoryStatus.ACTIVE, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    gmail_id: str = Field(primary_key=True)
    thread_id: str = Field(index=True)
    sender: str = ""
    subject: str = ""
    received_at: datetime | None = Field(default=None, index=True)
    body_hash: str = ""
    state: MessageState = Field(default=MessageState.PENDING, index=True)
    applied_label_key: str | None = Field(default=None, index=True)
    applied_label_id: str | None = Field(default=None)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ClassificationRecord(SQLModel, table=True):
    __tablename__ = "classifications"

    id: int | None = Field(default=None, primary_key=True)
    gmail_id: str = Field(index=True, foreign_key="messages.gmail_id")
    # Applied / current decision key (may differ from predicted after human review).
    label_key: str | None = Field(default=None, index=True)
    predicted_key: str | None = Field(default=None, index=True)
    final_key: str | None = Field(default=None, index=True)
    # NULL for rule hits — must not contaminate confidence calibration.
    confidence: float | None = Field(default=None)
    rationale: str = ""
    # LLM proposed_new payload when no existing label was confidently chosen.
    proposed_key: str | None = Field(default=None, index=True)
    proposed_description: str | None = None
    proposed_why: str | None = None
    source: ClassificationSource
    model: str | None = None
    prompt_version: str | None = None
    tokens: int | None = None
    applied_at: datetime | None = None
    needs_review: bool = False
    review_status: ReviewStatus | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Proposal(SQLModel, table=True):
    __tablename__ = "proposals"

    id: int | None = Field(default=None, primary_key=True)
    gmail_id: str = Field(index=True, foreign_key="messages.gmail_id")
    suggested_key: str = Field(index=True)
    description: str
    rationale: str = ""
    why_no_existing_fit: str = ""
    status: ProposalStatus = Field(default=ProposalStatus.PENDING, index=True)
    dedupe_key: str = Field(index=True, default="")
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None


class NegativeExample(SQLModel, table=True):
    """User removed a Tagsmith label — never re-apply that key to this message."""

    __tablename__ = "negative_examples"
    __table_args__ = (UniqueConstraint("gmail_id", "label_key", name="uq_neg_msg_label"),)

    id: int | None = Field(default=None, primary_key=True)
    gmail_id: str = Field(index=True, foreign_key="messages.gmail_id")
    label_key: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    counts_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    cost_estimate: float | None = None
    dry_run: bool = True
    notes: str = Field(default="", sa_column=Column(Text, default=""))
