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
from tagsmith.db.session import LOCAL_TENANT_ID
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
        *,
        tenant_id: int = LOCAL_TENANT_ID,
    ) -> None:
        self.session = session
        self.gmail = gmail
        self.settings = settings
        self.tenant_id = tenant_id
        self.queue = ReviewService(session, tenant_id=tenant_id)
        self.taxonomy = TaxonomyRegistry(session, settings)

    def _index_for_rag(self, message: Message, label_key: str) -> None:
        if not self.settings.enable_rag:
            return
        from tagsmith.rag.index import make_store
        from tagsmith.rag.store import example_text_from_email

        payload = dict(message.payload_json or {})
        meta = example_text_from_email(
            sender=str(payload.get("sender") or message.sender),
            subject=str(payload.get("subject") or message.subject),
            body_text=str(payload.get("body_text") or ""),
        )
        make_store(self.session, self.settings).upsert(
            gmail_id=message.gmail_id,
            label_key=label_key,
            sender=meta["sender"],
            subject=meta["subject"],
            body_excerpt=meta["body_excerpt"],
        )

    def list_proposals(self) -> list[ProposalView]:
        out: list[ProposalView] = []
        for proposal in self.queue.list_pending_proposals():
            msg = self.session.get(Message, proposal.gmail_id)
            # Skip proposals already resolved via the held-message review path.
            if msg is not None and msg.state != MessageState.HELD:
                continue
            out.append(ProposalView(proposal=proposal, message=msg))
        return out

    def list_needs_review(self) -> list[tuple[Message, ClassificationRecord]]:
        return self.queue.list_needs_review()

    def list_held(self) -> list[tuple[Message, ClassificationRecord | None]]:
        return self.queue.list_held()

    def _needs_review_label_id(self) -> str | None:
        label = self.gmail.get_or_create_label(self.settings.needs_review_label_name)
        return str(label.get("id") or "") or None

    def _close_pending_proposals_for_message(self, gmail_id: str) -> None:
        pending = self.session.exec(
            select(Proposal).where(
                Proposal.gmail_id == gmail_id,
                Proposal.status == ProposalStatus.PENDING,
            )
        ).all()
        now = datetime.now(UTC)
        for proposal in pending:
            proposal.status = ProposalStatus.REJECTED
            proposal.decided_at = now

    def resolve_held_with_existing(
        self,
        gmail_id: str,
        label_key: str,
        *,
        apply: bool = True,
    ) -> ClassificationRecord:
        """File a held message under an existing label and clear its review state."""
        if label_key not in self.taxonomy.active_keys():
            raise ValueError(f"unknown active label: {label_key}")

        message = self.session.get(Message, gmail_id)
        if message is None:
            raise KeyError(gmail_id)
        if message.state != MessageState.HELD:
            raise ValueError(f"message {gmail_id} is {message.state}, expected held")

        latest = self.session.exec(
            select(ClassificationRecord)
            .where(ClassificationRecord.gmail_id == gmail_id)
            .order_by(ClassificationRecord.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        predicted = latest.predicted_key if latest else None

        label_id: str | None = None
        if apply:
            remove_ids: list[str] = []
            if message.applied_label_id:
                remove_ids.append(message.applied_label_id)
            review_id = self._needs_review_label_id()
            if review_id:
                remove_ids.append(review_id)
            label = self.gmail.get_or_create_label(self.settings.gmail_label_name(label_key))
            label_id = str(label.get("id") or "")
            self.gmail.modify_labels(
                gmail_id,
                add_label_ids=[label_id],
                remove_label_ids=remove_ids,
            )

        self._close_pending_proposals_for_message(gmail_id)
        message.state = MessageState.LABELED
        message.applied_label_key = label_key
        message.applied_label_id = label_id
        message.updated_at = utcnow()

        record = ClassificationRecord(
            gmail_id=gmail_id,
            label_key=label_key,
            predicted_key=predicted,
            final_key=label_key,
            confidence=None,
            rationale=f"Human filed held message under existing label '{label_key}'",
            source=ClassificationSource.HUMAN,
            applied_at=utcnow() if apply else None,
            needs_review=False,
            review_status=ReviewStatus.CHANGED,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        self._index_for_rag(message, label_key)
        log.info("held.assigned_existing", gmail_id=gmail_id, label_key=label_key)
        return record

    def resolve_held_with_new(
        self,
        gmail_id: str,
        *,
        suggested_key: str,
        description: str,
        why: str,
        apply: bool = True,
    ) -> ClassificationRecord:
        """Create/activate a new category and apply it to a held message."""
        message = self.session.get(Message, gmail_id)
        if message is None:
            raise KeyError(gmail_id)
        if message.state != MessageState.HELD:
            raise ValueError(f"message {gmail_id} is {message.state}, expected held")

        latest = self.session.exec(
            select(ClassificationRecord)
            .where(ClassificationRecord.gmail_id == gmail_id)
            .order_by(ClassificationRecord.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        predicted = latest.predicted_key if latest else None

        label_id: str | None = None
        if apply:
            remove_ids: list[str] = []
            review_id = self._needs_review_label_id()
            if review_id:
                remove_ids.append(review_id)
            label = self.gmail.get_or_create_label(self.settings.gmail_label_name(suggested_key))
            label_id = str(label.get("id") or "")
            self.gmail.modify_labels(
                gmail_id,
                add_label_ids=[label_id],
                remove_label_ids=remove_ids,
            )

        self.taxonomy.activate_category(
            suggested_key,
            description,
            gmail_label_id=label_id,
        )
        self._close_pending_proposals_for_message(gmail_id)

        message.state = MessageState.LABELED
        message.applied_label_key = suggested_key
        message.applied_label_id = label_id
        message.updated_at = utcnow()

        record = ClassificationRecord(
            gmail_id=gmail_id,
            label_key=suggested_key,
            predicted_key=predicted,
            final_key=suggested_key,
            confidence=None,
            rationale=f"Human created category '{suggested_key}' for held message ({why})",
            source=ClassificationSource.HUMAN,
            applied_at=utcnow() if apply else None,
            needs_review=False,
            review_status=ReviewStatus.PROPOSED_NEW,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        self._index_for_rag(message, suggested_key)
        log.info("held.created_category", gmail_id=gmail_id, key=suggested_key)
        return record

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
            remove_ids: list[str] = []
            review_id = self._needs_review_label_id()
            if review_id:
                remove_ids.append(review_id)
            self.gmail.modify_labels(
                proposal.gmail_id,
                add_label_ids=[label_id],
                remove_label_ids=remove_ids,
            )

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

        # Re-classify remaining held messages waiting on this category.
        sync = SyncService(self.session, self.gmail, self.settings, tenant_id=self.tenant_id)
        return await sync.reclassify_held(
            apply=apply,
            label_key=key,
            exclude_gmail_ids={proposal.gmail_id},
        )

    def reject_proposal(self, proposal_id: int) -> Proposal:
        return self.queue.reject_proposal(proposal_id)

    def assign_existing_label(
        self,
        proposal_id: int,
        label_key: str,
        *,
        apply: bool = True,
    ) -> ClassificationRecord:
        """Resolve a proposal by filing the message under an existing taxonomy label."""
        if label_key not in self.taxonomy.active_keys():
            raise ValueError(f"unknown active label: {label_key}")

        proposal = self.session.get(Proposal, proposal_id)
        if proposal is None:
            raise KeyError(f"proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"proposal {proposal_id} is {proposal.status}")

        message = self.session.get(Message, proposal.gmail_id)
        if message is None:
            raise KeyError(proposal.gmail_id)

        label_id: str | None = None
        remove_ids: list[str] = []
        if apply:
            if message.applied_label_id:
                remove_ids.append(message.applied_label_id)
            review_id = self._needs_review_label_id()
            if review_id:
                remove_ids.append(review_id)
            label = self.gmail.get_or_create_label(self.settings.gmail_label_name(label_key))
            label_id = str(label.get("id") or "")
            self.gmail.modify_labels(
                proposal.gmail_id,
                add_label_ids=[label_id],
                remove_label_ids=remove_ids,
            )

        proposal.status = ProposalStatus.REJECTED
        proposal.decided_at = datetime.now(UTC)
        message.state = MessageState.LABELED
        message.applied_label_key = label_key
        message.applied_label_id = label_id
        message.updated_at = utcnow()

        record = ClassificationRecord(
            gmail_id=proposal.gmail_id,
            label_key=label_key,
            predicted_key=None,
            final_key=label_key,
            confidence=None,
            rationale=(
                f"Human assigned existing label '{label_key}' "
                f"(rejected proposal '{proposal.suggested_key}')"
            ),
            source=ClassificationSource.HUMAN,
            applied_at=utcnow() if apply else None,
            needs_review=False,
            review_status=ReviewStatus.CHANGED,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        log.info(
            "proposal.assigned_existing",
            proposal_id=proposal_id,
            label_key=label_key,
            gmail_id=proposal.gmail_id,
        )
        return record

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

        if apply:
            add_ids: list[str] = []
            if message.applied_label_id is None:
                label = self.gmail.get_or_create_label(self.settings.gmail_label_name(final))
                label_id = str(label.get("id") or "")
                add_ids.append(label_id)
                message.applied_label_id = label_id
            remove_ids: list[str] = []
            review_id = self._needs_review_label_id()
            if review_id:
                remove_ids.append(review_id)
            if add_ids or remove_ids:
                self.gmail.modify_labels(
                    gmail_id,
                    add_label_ids=add_ids,
                    remove_label_ids=remove_ids,
                )

        record.final_key = final
        record.label_key = final
        record.review_status = ReviewStatus.CONFIRMED
        record.needs_review = False
        message.state = MessageState.LABELED
        message.applied_label_key = final
        message.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(record)
        self._index_for_rag(message, final)
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
            remove_ids: list[str] = []
            if message.applied_label_id:
                remove_ids.append(message.applied_label_id)
            review_id = self._needs_review_label_id()
            if review_id:
                remove_ids.append(review_id)
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
        self._index_for_rag(message, new_key)
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
            from sqlalchemy.exc import IntegrityError

            from tagsmith.review.queue import proposal_dedupe_key

            dedupe = proposal_dedupe_key(suggested_key, description)
            try:
                proposal = self.session.exec(
                    select(Proposal).where(
                        Proposal.status == ProposalStatus.PENDING,
                        Proposal.dedupe_key == dedupe,
                        Proposal.gmail_id == gmail_id,
                    )
                ).first()
            except IntegrityError:
                self.session.rollback()
                proposal = self.session.exec(
                    select(Proposal).where(
                        Proposal.status == ProposalStatus.PENDING,
                        Proposal.dedupe_key == dedupe,
                    )
                ).first()
            if proposal is None:
                proposal = self.session.exec(
                    select(Proposal).where(
                        Proposal.status == ProposalStatus.PENDING,
                        Proposal.dedupe_key == dedupe,
                    )
                ).first()
            if proposal is None:
                raise RuntimeError("failed to enqueue or locate proposal")
        self.session.commit()
        return proposal
