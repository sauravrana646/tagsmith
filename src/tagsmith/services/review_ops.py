"""Human review operations for proposals and medium-confidence needs-review."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from tagsmith.config import Settings
from tagsmith.db.models import (
    ClassificationRecord,
    ClassificationSource,
    Message,
    MessageState,
    Proposal,
    ProposalStatus,
    ReviewStatus,
    utcnow,
)
from tagsmith.gmail.protocol import GmailGateway
from tagsmith.review.queue import ReviewService
from tagsmith.services.sync import SyncResult, SyncService
from tagsmith.taxonomy.registry import TaxonomyRegistry
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


@dataclass
class ProposalView:
    proposal: Proposal
    message: Message | None


class ReviewOps:
    def __init__(
        self,
        session: Session,
        gmail: GmailGateway,
        settings: Settings,
    ) -> None:
        self.session = session
        self.gmail = gmail
        self.settings = settings
        self.queue = ReviewService(session)
        self.taxonomy = TaxonomyRegistry(session, settings)

    def list_proposals(self) -> list[ProposalView]:
        out: list[ProposalView] = []
        for proposal in self.queue.list_pending_proposals():
            msg = self.session.get(Message, proposal.gmail_id)
            out.append(ProposalView(proposal=proposal, message=msg))
        return out

    def list_needs_review(self) -> list[tuple[Message, ClassificationRecord]]:
        return self.queue.list_needs_review()

    async def approve_proposal(
        self,
        proposal_id: int,
        *,
        apply: bool = True,
        key_override: str | None = None,
        description_override: str | None = None,
    ) -> SyncResult:
        proposal = self.session.get(Proposal, proposal_id)
        if proposal is None:
            raise KeyError(f"proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"proposal {proposal_id} is {proposal.status}")

        key = key_override or proposal.suggested_key
        description = description_override or proposal.description

        label_id: str | None = None
        if apply:
            label = self.gmail.get_or_create_label(self.settings.gmail_label_name(key))
            label_id = str(label.get("id") or "")
            self.gmail.modify_labels(proposal.gmail_id, add_label_ids=[label_id])

        self.taxonomy.activate_category(
            key,
            description,
            gmail_label_id=label_id,
        )

        proposal.status = ProposalStatus.APPROVED
        proposal.decided_at = datetime.now(UTC)
        if key_override:
            proposal.suggested_key = key
        if description_override:
            proposal.description = description

        message = self.session.get(Message, proposal.gmail_id)
        if message:
            message.state = MessageState.LABELED
            message.applied_label_key = key
            message.applied_label_id = label_id
            message.updated_at = utcnow()

        self.session.add(
            ClassificationRecord(
                gmail_id=proposal.gmail_id,
                label_key=key,
                predicted_key=None,
                final_key=key,
                confidence=None,
                rationale=f"Human approved proposal '{key}'",
                source=ClassificationSource.HUMAN,
                applied_at=utcnow() if apply else None,
                needs_review=False,
                review_status=None,
            )
        )
        self.session.commit()
        log.info("proposal.approved", proposal_id=proposal_id, key=key)

        # Re-classify remaining held messages inside approve.
        sync = SyncService(self.session, self.gmail, self.settings)
        return await sync.reclassify_held(apply=apply)

    def reject_proposal(self, proposal_id: int) -> Proposal:
        return self.queue.reject_proposal(proposal_id)

    def _latest_needs_review_record(self, gmail_id: str) -> ClassificationRecord:
        stmt = (
            select(ClassificationRecord)
            .where(ClassificationRecord.gmail_id == gmail_id)
            .where(ClassificationRecord.needs_review == True)  # noqa: E712
            .order_by(ClassificationRecord.created_at.desc())  # type: ignore[attr-defined]
        )
        record = self.session.exec(stmt).first()
        if record is None:
            raise KeyError(f"no needs-review classification for {gmail_id}")
        return record

    def confirm_label(self, gmail_id: str, *, apply: bool = True) -> ClassificationRecord:
        message = self.session.get(Message, gmail_id)
        if message is None:
            raise KeyError(gmail_id)
        record = self._latest_needs_review_record(gmail_id)
        final = record.predicted_key or record.label_key
        if not final:
            raise ValueError("nothing to confirm")

        if apply and message.applied_label_id is None:
            label = self.gmail.get_or_create_label(self.settings.gmail_label_name(final))
            label_id = str(label.get("id") or "")
            self.gmail.modify_labels(gmail_id, add_label_ids=[label_id])
            message.applied_label_id = label_id

        record.final_key = final
        record.label_key = final
        record.review_status = ReviewStatus.CONFIRMED
        record.needs_review = False
        message.state = MessageState.LABELED
        message.applied_label_key = final
        message.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(record)
        return record

    def change_label(
        self,
        gmail_id: str,
        new_key: str,
        *,
        apply: bool = True,
    ) -> ClassificationRecord:
        if new_key not in self.taxonomy.active_keys():
            raise ValueError(f"unknown active label: {new_key}")
        message = self.session.get(Message, gmail_id)
        if message is None:
            raise KeyError(gmail_id)
        record = self._latest_needs_review_record(gmail_id)
        predicted = record.predicted_key or record.label_key

        label_id: str | None = message.applied_label_id
        if apply:
            # Remove previous category label if present; keep needs-review removal optional.
            remove_ids: list[str] = []
            if message.applied_label_id:
                remove_ids.append(message.applied_label_id)
            label = self.gmail.get_or_create_label(self.settings.gmail_label_name(new_key))
            label_id = str(label.get("id") or "")
            self.gmail.modify_labels(
                gmail_id,
                add_label_ids=[label_id],
                remove_label_ids=remove_ids,
            )

        record.predicted_key = predicted
        record.final_key = new_key
        record.label_key = new_key
        record.review_status = ReviewStatus.CHANGED
        record.needs_review = False
        message.state = MessageState.LABELED
        message.applied_label_key = new_key
        message.applied_label_id = label_id
        message.updated_at = utcnow()

        self.session.add(
            ClassificationRecord(
                gmail_id=gmail_id,
                label_key=new_key,
                predicted_key=predicted,
                final_key=new_key,
                confidence=None,
                rationale=f"Human changed label from '{predicted}' to '{new_key}'",
                source=ClassificationSource.HUMAN,
                applied_at=utcnow() if apply else None,
                needs_review=False,
                review_status=ReviewStatus.CHANGED,
            )
        )
        self.session.commit()
        self.session.refresh(record)
        return record

    def reject_and_propose(
        self,
        gmail_id: str,
        *,
        suggested_key: str,
        description: str,
        why: str,
    ) -> Proposal:
        message = self.session.get(Message, gmail_id)
        if message is None:
            raise KeyError(gmail_id)
        record = self._latest_needs_review_record(gmail_id)
        predicted = record.predicted_key or record.label_key

        record.review_status = ReviewStatus.PROPOSED_NEW
        record.needs_review = False
        record.final_key = None
        message.state = MessageState.HELD
        message.updated_at = utcnow()

        proposal = self.queue.enqueue_proposal(
            gmail_id=gmail_id,
            suggested_key=suggested_key,
            description=description,
            rationale=f"Human rejected predicted '{predicted}'",
            why_no_existing_fit=why,
        )
        if proposal is None:
            # Dedupe hit — fetch existing
            from tagsmith.review.queue import proposal_dedupe_key

            dedupe = proposal_dedupe_key(suggested_key, description)
            proposal = self.session.exec(
                select(Proposal).where(
                    Proposal.status == ProposalStatus.PENDING,
                    Proposal.dedupe_key == dedupe,
                )
            ).one()
        self.session.commit()
        return proposal
