"""Sync unread mail: classify, apply/hold, persist — dry-run by default."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from tagsmith.classify.pipeline import classify_with_routing
from tagsmith.classify.rules import load_rules
from tagsmith.classify.schema import NewCategory
from tagsmith.config import PROMPT_VERSION, Settings
from tagsmith.db.models import (
    ClassificationRecord,
    ClassificationSource,
    Message,
    MessageState,
    NegativeExample,
    ReviewStatus,
    Run,
    utcnow,
)
from tagsmith.gmail.parser import NormalizedEmail, normalize_message
from tagsmith.gmail.protocol import GmailGateway
from tagsmith.review.queue import ReviewService
from tagsmith.taxonomy.registry import TaxonomyRegistry
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


@dataclass
class SyncCounts:
    fetched: int = 0
    skipped_prior: int = 0
    skipped_user_removed: int = 0
    rule_labeled: int = 0
    llm_labeled: int = 0
    needs_review: int = 0
    held: int = 0
    proposals: int = 0
    applied: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "skipped_prior": self.skipped_prior,
            "skipped_user_removed": self.skipped_user_removed,
            "rule_labeled": self.rule_labeled,
            "llm_labeled": self.llm_labeled,
            "needs_review": self.needs_review,
            "held": self.held,
            "proposals": self.proposals,
            "applied": self.applied,
        }


@dataclass
class SyncResult:
    run_id: int | None
    dry_run: bool
    counts: SyncCounts = field(default_factory=SyncCounts)
    decisions: list[dict[str, Any]] = field(default_factory=list)


class SyncService:
    def __init__(
        self,
        session: Session,
        gmail: GmailGateway,
        settings: Settings,
    ) -> None:
        self.session = session
        self.gmail = gmail
        self.settings = settings
        self.taxonomy = TaxonomyRegistry(session, settings)
        self.reviews = ReviewService(session)

    def bootstrap(self) -> None:
        self.taxonomy.ensure_seeded()
        active = set(self.taxonomy.active_keys())
        # Validate rules early and loudly.
        load_rules(self.settings.rules_path, active)

    def _blocked_keys(self, gmail_id: str) -> set[str]:
        rows = self.session.exec(
            select(NegativeExample).where(NegativeExample.gmail_id == gmail_id)
        ).all()
        return {r.label_key for r in rows}

    def _detect_user_removed_label(self, email: NormalizedEmail, message: Message) -> bool:
        if not message.applied_label_id or not message.applied_label_key:
            return False
        if message.applied_label_id in email.label_ids:
            return False
        # User removed our label.
        exists = self.session.exec(
            select(NegativeExample).where(
                NegativeExample.gmail_id == message.gmail_id,
                NegativeExample.label_key == message.applied_label_key,
            )
        ).first()
        if exists is None:
            self.session.add(
                NegativeExample(
                    gmail_id=message.gmail_id,
                    label_key=message.applied_label_key,
                )
            )
        message.state = MessageState.USER_REMOVED
        message.updated_at = utcnow()
        self.session.commit()
        log.info(
            "sync.user_removed_label",
            gmail_id=message.gmail_id,
            label_key=message.applied_label_key,
        )
        return True

    def _upsert_message(self, email: NormalizedEmail) -> Message:
        msg = self.session.get(Message, email.gmail_id)
        payload = {
            "sender": email.sender,
            "to": email.to,
            "subject": email.subject,
            "date": email.date.isoformat() if email.date else None,
            "list_unsubscribe": email.list_unsubscribe,
            "body_text": email.body_text,
            "attachment_names": email.attachment_names,
            "label_ids": email.label_ids,
            "snippet": email.snippet,
        }
        if msg is None:
            msg = Message(
                gmail_id=email.gmail_id,
                thread_id=email.thread_id,
                sender=email.sender,
                subject=email.subject,
                received_at=email.date,
                body_hash=email.body_hash,
                state=MessageState.PENDING,
                payload_json=payload,
            )
            self.session.add(msg)
        else:
            msg.sender = email.sender
            msg.subject = email.subject
            msg.received_at = email.date
            msg.body_hash = email.body_hash
            msg.payload_json = payload
            msg.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(msg)
        return msg

    def _ensure_label_id(self, key: str, *, apply: bool) -> str | None:
        category = self.taxonomy.get(key)
        if category and category.gmail_label_id:
            return category.gmail_label_id
        if not apply:
            return None
        label = self.gmail.get_or_create_label(self.settings.gmail_label_name(key))
        label_id = str(label.get("id") or "")
        if category:
            category.gmail_label_id = label_id
            self.session.commit()
        return label_id or None

    def _apply_labels(
        self,
        gmail_id: str,
        *,
        label_key: str | None,
        needs_review: bool,
        apply: bool,
    ) -> tuple[str | None, str | None]:
        add_ids: list[str] = []
        applied_label_id: str | None = None
        if label_key:
            label_id = self._ensure_label_id(label_key, apply=apply)
            applied_label_id = label_id
            if label_id:
                add_ids.append(label_id)
        if needs_review and apply:
            review_label = self.gmail.get_or_create_label(
                self.settings.needs_review_label_name
            )
            rid = str(review_label.get("id") or "")
            if rid:
                add_ids.append(rid)
        if apply and add_ids:
            self.gmail.modify_labels(gmail_id, add_label_ids=add_ids)
        return applied_label_id, label_key

    async def process_email(
        self,
        email: NormalizedEmail,
        *,
        apply: bool,
        reprocess: bool,
        counts: SyncCounts,
        decisions: list[dict[str, Any]],
    ) -> None:
        message = self._upsert_message(email)

        if self._detect_user_removed_label(email, message):
            counts.skipped_user_removed += 1
            decisions.append(
                {
                    "gmail_id": email.gmail_id,
                    "action": "skip_user_removed",
                    "subject": email.subject,
                }
            )
            return

        terminal = {
            MessageState.LABELED,
            MessageState.HELD,
            MessageState.NEEDS_REVIEW,
            MessageState.SKIPPED,
            MessageState.USER_REMOVED,
        }
        if message.state in terminal and not reprocess:
            counts.skipped_prior += 1
            decisions.append(
                {
                    "gmail_id": email.gmail_id,
                    "action": "skip_prior",
                    "state": message.state.value,
                    "subject": email.subject,
                }
            )
            return

        active_keys = self.taxonomy.active_keys()
        rules = load_rules(self.settings.rules_path, set(active_keys))
        catalog = self.taxonomy.prompt_catalog()
        blocked = self._blocked_keys(email.gmail_id)

        result = await classify_with_routing(
            email,
            rules=rules,
            label_keys=active_keys,
            catalog=catalog,
            settings=self.settings,
            examples=None,
            blocked_keys=blocked,
        )
        classification = result.classification
        route = result.route
        source = (
            ClassificationSource.RULE
            if result.source == "rule"
            else ClassificationSource.LLM
        )

        needs_review = route == "apply_with_review"
        hold = route == "hold_propose"
        label_key = None if hold else classification.label_key

        applied_label_id = None
        if not hold and label_key:
            applied_label_id, _ = self._apply_labels(
                email.gmail_id,
                label_key=label_key,
                needs_review=needs_review,
                apply=apply,
            )
            if apply:
                counts.applied += 1
        elif hold and needs_review is False:
            # Still mark needs-review label on holds so they are visible in Gmail.
            if apply:
                self._apply_labels(
                    email.gmail_id,
                    label_key=None,
                    needs_review=True,
                    apply=True,
                )

        if hold:
            message.state = MessageState.HELD
            counts.held += 1
            proposed = classification.proposed_new
            if proposed is None and classification.label_key is None:
                # Last-resort only if the model ignored the schema (should be rare).
                slug = re.sub(r"[^a-z0-9]+", "-", email.subject.lower()).strip("-")
                slug = "-".join(slug.split("-")[:4]) or "needs-human-name"
                if slug in {"uncategorized-followup", "unknown", "other", "misc"}:
                    slug = "needs-human-name"
                proposed = NewCategory(
                    suggested_key=slug,
                    description=f"Human should refine category for: {email.subject[:80]}",
                    why_no_existing_fit=classification.rationale,
                )
                classification = classification.model_copy(update={"proposed_new": proposed})
            if proposed is not None:
                proposal = self.reviews.enqueue_proposal(
                    gmail_id=email.gmail_id,
                    suggested_key=proposed.suggested_key,
                    description=proposed.description,
                    rationale=classification.rationale,
                    why_no_existing_fit=proposed.why_no_existing_fit,
                )
                if proposal is not None:
                    counts.proposals += 1
        elif needs_review:
            message.state = MessageState.NEEDS_REVIEW
            counts.needs_review += 1
        else:
            message.state = MessageState.LABELED

        if result.source == "rule":
            counts.rule_labeled += 1
        else:
            counts.llm_labeled += 1

        if label_key:
            message.applied_label_key = label_key
            message.applied_label_id = applied_label_id
        message.updated_at = utcnow()

        proposed = classification.proposed_new
        record = ClassificationRecord(
            gmail_id=email.gmail_id,
            label_key=label_key,
            predicted_key=classification.label_key,
            final_key=None if needs_review or hold else label_key,
            confidence=classification.confidence,
            rationale=classification.rationale,
            proposed_key=proposed.suggested_key if proposed else None,
            proposed_description=proposed.description if proposed else None,
            proposed_why=proposed.why_no_existing_fit if proposed else None,
            source=source,
            model=None if source == ClassificationSource.RULE else self.settings.llm_model,
            prompt_version=None if source == ClassificationSource.RULE else PROMPT_VERSION,
            applied_at=utcnow() if apply and not hold else None,
            needs_review=needs_review,
            review_status=ReviewStatus.PENDING if needs_review else None,
        )
        self.session.add(record)
        self.session.commit()

        decisions.append(
            {
                "gmail_id": email.gmail_id,
                "subject": email.subject,
                "source": result.source,
                "route": route,
                "label_key": classification.label_key,
                "confidence": classification.confidence,
                "rationale": classification.rationale,
                "proposed_new": (
                    classification.proposed_new.model_dump()
                    if classification.proposed_new
                    else None
                ),
                "applied": bool(apply and not hold and label_key),
            }
        )

    async def sync(
        self,
        *,
        limit: int = 50,
        apply: bool = False,
        reprocess: bool = False,
        query: str = "is:unread",
    ) -> SyncResult:
        self.bootstrap()
        if apply:
            self.taxonomy.reconcile_gmail_labels(self.gmail)  # type: ignore[arg-type]

        run = Run(started_at=datetime.now(UTC), dry_run=not apply)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        counts = SyncCounts()
        decisions: list[dict[str, Any]] = []

        ids = self.gmail.list_message_ids(query=query, limit=limit)
        counts.fetched = len(ids)
        for gmail_id in ids:
            raw = self.gmail.get_message(gmail_id)
            email = normalize_message(raw, body_char_limit=self.settings.body_char_limit)
            await self.process_email(
                email,
                apply=apply,
                reprocess=reprocess,
                counts=counts,
                decisions=decisions,
            )

        run.finished_at = datetime.now(UTC)
        run.counts_json = counts.as_dict()
        self.session.commit()

        return SyncResult(run_id=run.id, dry_run=not apply, counts=counts, decisions=decisions)

    async def reclassify_held(self, *, apply: bool) -> SyncResult:
        """Re-run classification for held messages (used after proposal approval)."""
        self.bootstrap()
        held = list(
            self.session.exec(select(Message).where(Message.state == MessageState.HELD)).all()
        )
        counts = SyncCounts()
        decisions: list[dict[str, Any]] = []
        for message in held:
            raw = self.gmail.get_message(message.gmail_id)
            email = normalize_message(raw, body_char_limit=self.settings.body_char_limit)
            # Force reprocess path.
            message.state = MessageState.PENDING
            self.session.commit()
            await self.process_email(
                email,
                apply=apply,
                reprocess=True,
                counts=counts,
                decisions=decisions,
            )
        return SyncResult(run_id=None, dry_run=not apply, counts=counts, decisions=decisions)
