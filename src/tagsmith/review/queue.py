"""Proposal dedupe and needs-review / proposal decision helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from tagsmith.db.models import (
    Category,
    CategoryStatus,
    ClassificationRecord,
    Message,
    MessageState,
    Proposal,
    ProposalStatus,
    ReviewStatus,
)
from tagsmith.telemetry import get_logger

log = get_logger(__name__)

NON_ALNUM = re.compile(r"[^a-z0-9]+")


def proposal_dedupe_key(suggested_key: str, description: str) -> str:
    key = suggested_key.strip().lower()
    desc = NON_ALNUM.sub(" ", description.strip().lower()).strip()
    # Collapse near-identical proposals by key + first 8 tokens of description.
    tokens = " ".join(desc.split()[:8])
    return f"{key}|{tokens}"


class ReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_pending_proposals(self) -> list[Proposal]:
        stmt = (
            select(Proposal)
            .where(Proposal.status == ProposalStatus.PENDING)
            .order_by(col(Proposal.created_at))
        )
        return list(self.session.exec(stmt).all())

    def list_needs_review(self) -> list[tuple[Message, ClassificationRecord]]:
        messages = list(
            self.session.exec(
                select(Message)
                .where(Message.state == MessageState.NEEDS_REVIEW)
                .order_by(col(Message.received_at))
            ).all()
        )
        out: list[tuple[Message, ClassificationRecord]] = []
        for message in messages:
            record = self.session.exec(
                select(ClassificationRecord)
                .where(ClassificationRecord.gmail_id == message.gmail_id)
                .where(ClassificationRecord.needs_review == True)  # noqa: E712
                .where(
                    (ClassificationRecord.review_status == ReviewStatus.PENDING)
                    | (ClassificationRecord.review_status == None)  # noqa: E711
                )
                .order_by(col(ClassificationRecord.created_at).desc())
            ).first()
            if record is not None:
                out.append((message, record))
        return out

    def list_held(self) -> list[tuple[Message, ClassificationRecord | None]]:
        """Messages held for no-fit / proposal — includes those without a pending proposal.

        Sync applies the Gmail AI/needs-review label to holds for visibility, but they
        live in MessageState.HELD (not NEEDS_REVIEW). Proposal dedupe can also collapse
        several holds into one proposal; this list is per-message so none are orphaned.
        """
        messages = list(
            self.session.exec(
                select(Message)
                .where(Message.state == MessageState.HELD)
                .order_by(col(Message.received_at))
            ).all()
        )
        out: list[tuple[Message, ClassificationRecord | None]] = []
        for message in messages:
            record = self.session.exec(
                select(ClassificationRecord)
                .where(ClassificationRecord.gmail_id == message.gmail_id)
                .order_by(col(ClassificationRecord.created_at).desc())
            ).first()
            out.append((message, record))
        return out

    def enqueue_proposal(
        self,
        *,
        gmail_id: str,
        suggested_key: str,
        description: str,
        rationale: str,
        why_no_existing_fit: str,
    ) -> Proposal | None:
        dedupe = proposal_dedupe_key(suggested_key, description)
        existing = self.session.exec(
            select(Proposal).where(
                Proposal.status == ProposalStatus.PENDING,
                Proposal.dedupe_key == dedupe,
            )
        ).first()
        if existing:
            log.info(
                "proposal.deduped",
                gmail_id=gmail_id,
                existing_id=existing.id,
                suggested_key=suggested_key,
            )
            return None

        # Also mark category as proposed if absent.
        cat = self.session.get(Category, suggested_key)
        if cat is None:
            self.session.add(
                Category(
                    key=suggested_key,
                    description=description,
                    exemplars=[],
                    status=CategoryStatus.PROPOSED,
                )
            )

        proposal = Proposal(
            gmail_id=gmail_id,
            suggested_key=suggested_key,
            description=description,
            rationale=rationale,
            why_no_existing_fit=why_no_existing_fit,
            status=ProposalStatus.PENDING,
            dedupe_key=dedupe,
        )
        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def reject_proposal(self, proposal_id: int) -> Proposal:
        proposal = self.session.get(Proposal, proposal_id)
        if proposal is None:
            raise KeyError(f"proposal {proposal_id} not found")
        proposal.status = ProposalStatus.REJECTED
        proposal.decided_at = datetime.now(UTC)
        cat = self.session.get(Category, proposal.suggested_key)
        if cat is not None and cat.status == CategoryStatus.PROPOSED:
            cat.status = CategoryStatus.REJECTED
        self.session.commit()
        self.session.refresh(proposal)
        return proposal
