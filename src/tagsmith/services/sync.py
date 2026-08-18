"""Sync unread mail: classify, apply/hold, persist — dry-run by default."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from tagsmith.classify.pipeline import classify_with_routing
from tagsmith.classify.rules import load_rules
from tagsmith.classify.schema import Classification, NewCategory
from tagsmith.config import PROMPT_VERSION, Settings
from tagsmith.db.models import (
    ClassificationRecord,
    ClassificationSource,
    Message,
    MessageState,
    NegativeExample,
    Proposal,
    ProposalStatus,
    ReviewStatus,
    Run,
    SyncState,
    utcnow,
)
from tagsmith.db.session import LOCAL_TENANT_ID
from tagsmith.gmail.errors import GmailApiError
from tagsmith.gmail.parser import NormalizedEmail, normalize_message
from tagsmith.gmail.protocol import GmailGateway
from tagsmith.rag.index import index_normalized, make_store, unindex_gmail_id
from tagsmith.rag.retriever import Retriever, format_category_hints
from tagsmith.rag.store import example_text_from_email
from tagsmith.review.queue import ReviewService
from tagsmith.taxonomy.registry import TaxonomyRegistry
from tagsmith.telemetry import get_logger, span

log = get_logger(__name__)


@dataclass
class SyncCounts:
    fetched: int = 0
    skipped_prior: int = 0
    skipped_user_removed: int = 0
    rule_labeled: int = 0
    llm_labeled: int = 0
    rag_labeled: int = 0
    needs_review: int = 0
    held: int = 0
    proposals: int = 0
    applied: int = 0
    classify_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "skipped_prior": self.skipped_prior,
            "skipped_user_removed": self.skipped_user_removed,
            "rule_labeled": self.rule_labeled,
            "llm_labeled": self.llm_labeled,
            "rag_labeled": self.rag_labeled,
            "needs_review": self.needs_review,
            "held": self.held,
            "proposals": self.proposals,
            "applied": self.applied,
            "classify_errors": self.classify_errors,
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
        *,
        tenant_id: int = LOCAL_TENANT_ID,
    ) -> None:
        self.session = session
        self.gmail = gmail
        self.settings = settings
        self.tenant_id = tenant_id
        self.taxonomy = TaxonomyRegistry(session, settings)
        self.reviews = ReviewService(session, tenant_id=tenant_id)

    async def _io(self, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)

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
        unindex_gmail_id(self.session, self.settings, message.gmail_id)
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
                tenant_id=self.tenant_id,
            )
            self.session.add(msg)
        else:
            msg.sender = email.sender
            msg.subject = email.subject
            msg.received_at = email.date
            msg.body_hash = email.body_hash
            msg.payload_json = payload
            msg.tenant_id = self.tenant_id
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
            review_label = self.gmail.get_or_create_label(self.settings.needs_review_label_name)
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

        reused = None if reprocess else self._unapplied_record(email.gmail_id)
        if reused is not None:
            classification, route, source, result_source, total_tokens, latency_ms = (
                self._classification_from_record(reused)
            )
        else:
            active_keys = self.taxonomy.active_keys()
            rules = load_rules(self.settings.rules_path, set(active_keys))
            catalog = self.taxonomy.prompt_catalog()
            blocked = self._blocked_keys(email.gmail_id)

            examples = None
            category_hints = None
            if self.settings.enable_rag:
                store = make_store(self.session, self.settings)
                retriever = Retriever(
                    store,
                    store.embedder,
                    example_k=self.settings.rag_example_k,
                    category_k=self.settings.rag_category_k,
                )
                query = example_text_from_email(
                    sender=email.sender,
                    subject=email.subject,
                    body_text=email.body_text,
                )["text"]
                rag_ctx = retriever.retrieve(
                    query,
                    exclude_gmail_ids={email.gmail_id},
                )
                examples = rag_ctx.examples or None
                category_hints = format_category_hints(rag_ctx.category_hints) or None

            result = await classify_with_routing(
                email,
                rules=rules,
                label_keys=active_keys,
                catalog=catalog,
                settings=self.settings,
                examples=examples,
                category_hints=category_hints,
                blocked_keys=blocked,
            )
            if (
                result.source in {"llm", "rag"}
                and result.classification.confidence == 0.0
                and "Model output invalid" in result.classification.rationale
            ):
                counts.classify_errors += 1
            classification = result.classification
            route = result.route
            if result.source == "rule":
                source = ClassificationSource.RULE
            elif result.source == "rag":
                source = ClassificationSource.RAG
            else:
                source = ClassificationSource.LLM
            result_source = result.source
            total_tokens = result.total_tokens
            latency_ms = result.latency_ms

        needs_review = route == "apply_with_review"
        hold = route == "hold_propose"
        label_key = None if hold else classification.label_key

        if result_source == "rule":
            counts.rule_labeled += 1
        elif result_source == "rag":
            counts.rag_labeled += 1
        else:
            counts.llm_labeled += 1

        proposed = classification.proposed_new
        record = reused
        if record is None:
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
                tokens=total_tokens,
                applied_at=None,
                needs_review=needs_review,
                review_status=ReviewStatus.PENDING if needs_review else None,
                tenant_id=self.tenant_id,
            )
            self.session.add(record)

        applied_label_id = None
        if apply:
            if label_key:
                message.applied_label_key = label_key
            message.tenant_id = self.tenant_id
            message.updated_at = utcnow()
            self.session.commit()

            if not hold and label_key:
                applied_label_id, _ = await self._io(
                    self._apply_labels,
                    email.gmail_id,
                    label_key=label_key,
                    needs_review=needs_review,
                    apply=True,
                )
                counts.applied += 1
            elif hold:
                await self._io(
                    self._apply_labels,
                    email.gmail_id,
                    label_key=None,
                    needs_review=True,
                    apply=True,
                )

            if hold:
                message.state = MessageState.HELD
                counts.held += 1
                if proposed is None and classification.label_key is None:
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

            if label_key:
                message.applied_label_key = label_key
                message.applied_label_id = applied_label_id
            record.applied_at = utcnow() if not hold else None
            message.updated_at = utcnow()
            self.session.commit()

            if self.settings.enable_rag and label_key and not hold and not needs_review:
                index_normalized(
                    make_store(self.session, self.settings), email, label_key=label_key
                )
        else:
            if hold:
                counts.held += 1
            elif needs_review:
                counts.needs_review += 1
            message.tenant_id = self.tenant_id
            message.updated_at = utcnow()
            self.session.commit()

        decisions.append(
            {
                "gmail_id": email.gmail_id,
                "subject": email.subject,
                "source": result_source,
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
                "tokens": total_tokens,
                "latency_ms": latency_ms,
                "rag_examples": 0,
            }
        )

    def _unapplied_record(self, gmail_id: str) -> ClassificationRecord | None:
        rec = self.session.exec(
            select(ClassificationRecord)
            .where(ClassificationRecord.gmail_id == gmail_id)
            .order_by(ClassificationRecord.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        if rec is None or rec.applied_at is not None:
            return None
        return rec

    def _classification_from_record(
        self, rec: ClassificationRecord
    ) -> tuple[Classification, str, ClassificationSource, str, int | None, float | None]:
        proposed = None
        if rec.proposed_key:
            proposed = NewCategory(
                suggested_key=rec.proposed_key,
                description=rec.proposed_description or "",
                why_no_existing_fit=rec.proposed_why or "",
            )
        classification = Classification(
            label_key=rec.predicted_key or rec.label_key,
            confidence=rec.confidence if rec.confidence is not None else 0.0,
            rationale=rec.rationale,
            proposed_new=proposed,
        )
        if rec.needs_review:
            route = "apply_with_review"
        elif rec.proposed_key and not rec.final_key:
            route = "hold_propose"
        else:
            route = "apply"
        if rec.source == ClassificationSource.RULE:
            result_source = "rule"
        elif rec.source == ClassificationSource.RAG:
            result_source = "rag"
        else:
            result_source = "llm"
        return classification, route, rec.source, result_source, rec.tokens, None

    def get_sync_state(self) -> SyncState:
        state = self.session.get(SyncState, self.tenant_id)
        if state is None:
            state = SyncState(id=self.tenant_id, tenant_id=self.tenant_id)
            self.session.add(state)
            self.session.commit()
            self.session.refresh(state)
        return state

    def ensure_history_cursor(self) -> SyncState:
        """Bootstrap historyId from Gmail profile when missing."""
        state = self.get_sync_state()
        if state.history_id:
            return state
        state.history_id = self.gmail.get_profile_history_id()
        state.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(state)
        log.info("sync.history_cursor_bootstrapped", history_id=state.history_id)
        return state

    def _finalize_run(
        self,
        run: Run,
        *,
        counts: SyncCounts,
        decisions: list[dict[str, Any]],
        notes: str = "",
    ) -> SyncResult:
        run.finished_at = datetime.now(UTC)
        run.counts_json = counts.as_dict()
        run.notes = notes
        token_total = 0
        for decision in decisions:
            t = decision.get("tokens")
            if isinstance(t, int):
                token_total += t
        if token_total and (
            self.settings.cost_per_1k_input_tokens or self.settings.cost_per_1k_output_tokens
        ):
            blended = (
                self.settings.cost_per_1k_input_tokens + self.settings.cost_per_1k_output_tokens
            ) / 2.0
            run.cost_estimate = (token_total / 1000.0) * blended
        self.session.commit()
        return SyncResult(run_id=run.id, dry_run=run.dry_run, counts=counts, decisions=decisions)

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
            await self._io(self.taxonomy.reconcile_gmail_labels, self.gmail)

        run = Run(
            started_at=datetime.now(UTC),
            dry_run=not apply,
            notes="full_unread",
            tenant_id=self.tenant_id,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        counts = SyncCounts()
        decisions: list[dict[str, Any]] = []

        with span(
            "tagsmith.sync",
            limit=limit,
            apply=apply,
            reprocess=reprocess,
            query=query,
        ):
            try:
                ids = await self._io(self.gmail.list_message_ids, query=query, limit=limit)
                counts.fetched = len(ids)
                for gmail_id in ids:
                    try:
                        raw = await self._io(self.gmail.get_message, gmail_id)
                    except Exception as exc:
                        log.warning("sync.message_missing", gmail_id=gmail_id, error=str(exc))
                        existing = self.session.get(Message, gmail_id)
                        if existing is not None:
                            existing.state = MessageState.SKIPPED
                            existing.updated_at = utcnow()
                            self.session.commit()
                        continue
                    email = normalize_message(raw, body_char_limit=self.settings.body_char_limit)
                    await self.process_email(
                        email,
                        apply=apply,
                        reprocess=reprocess,
                        counts=counts,
                        decisions=decisions,
                    )

                state = self.get_sync_state()
                state.history_id = await self._io(self.gmail.get_profile_history_id)
                state.updated_at = utcnow()
                self.session.commit()
            finally:
                if run.finished_at is None:
                    self._finalize_run(run, counts=counts, decisions=decisions, notes="full_unread")

        return SyncResult(run_id=run.id, dry_run=run.dry_run, counts=counts, decisions=decisions)

    async def sync_incremental(
        self,
        *,
        limit: int = 100,
        apply: bool = False,
        reprocess: bool = False,
        fallback_to_full: bool = True,
    ) -> SyncResult:
        """Process messages changed since the stored historyId (Phase 4)."""
        self.bootstrap()
        if apply:
            await self._io(self.taxonomy.reconcile_gmail_labels, self.gmail)

        state = self.ensure_history_cursor()
        start_history_id = state.history_id
        assert start_history_id is not None

        run = Run(
            started_at=datetime.now(UTC),
            dry_run=not apply,
            notes="incremental",
            tenant_id=self.tenant_id,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        counts = SyncCounts()
        decisions: list[dict[str, Any]] = []

        with span(
            "tagsmith.sync.incremental",
            limit=limit,
            apply=apply,
            start_history_id=start_history_id,
        ):
            try:
                try:
                    page = await self._io(
                        self.gmail.list_history,
                        start_history_id=start_history_id,
                        max_results=limit,
                    )
                except GmailApiError as exc:
                    if exc.status == 404 and fallback_to_full:
                        log.warning(
                            "sync.history_stale",
                            error=str(exc),
                            history_id=start_history_id,
                        )
                        self.session.delete(run)
                        self.session.commit()
                        run.finished_at = datetime.now(UTC)
                        return await self.sync(limit=limit, apply=apply, reprocess=reprocess)
                    log.warning(
                        "sync.history_error",
                        status=exc.status,
                        error=str(exc),
                        history_id=start_history_id,
                    )
                    raise

                ids = page.message_ids
                latest = page.cursor
                counts.fetched = len(ids)
                if page.truncated:
                    log.info(
                        "sync.history_truncated",
                        start_history_id=start_history_id,
                        cursor=latest,
                        fetched=len(ids),
                        limit=limit,
                    )
                for gmail_id in ids:
                    try:
                        raw = await self._io(self.gmail.get_message, gmail_id)
                    except Exception as exc:
                        log.warning(
                            "sync.history_message_missing", gmail_id=gmail_id, error=str(exc)
                        )
                        existing = self.session.get(Message, gmail_id)
                        if existing is not None:
                            existing.state = MessageState.SKIPPED
                            existing.updated_at = utcnow()
                            self.session.commit()
                        continue
                    email = normalize_message(raw, body_char_limit=self.settings.body_char_limit)
                    await self.process_email(
                        email,
                        apply=apply,
                        reprocess=reprocess,
                        counts=counts,
                        decisions=decisions,
                    )

                state = self.get_sync_state()
                if page.truncated:
                    if latest:
                        state.history_id = latest
                else:
                    state.history_id = latest or await self._io(self.gmail.get_profile_history_id)
                state.last_incremental_at = utcnow()
                state.updated_at = utcnow()
                self.session.commit()
            finally:
                if run.finished_at is None:
                    self._finalize_run(run, counts=counts, decisions=decisions, notes="incremental")

        return SyncResult(run_id=run.id, dry_run=run.dry_run, counts=counts, decisions=decisions)

    async def reclassify_held(
        self,
        *,
        apply: bool,
        label_key: str | None = None,
        exclude_gmail_ids: set[str] | None = None,
    ) -> SyncResult:
        """Re-run classification for held messages (used after proposal approval)."""
        self.bootstrap()
        exclude = exclude_gmail_ids or set()
        held = list(
            self.session.exec(
                select(Message).where(
                    Message.state == MessageState.HELD,
                    Message.tenant_id == self.tenant_id,
                )
            ).all()
        )
        counts = SyncCounts()
        decisions: list[dict[str, Any]] = []
        for message in held:
            if message.gmail_id in exclude:
                continue
            if label_key and not self._held_matches_key(message.gmail_id, label_key):
                continue
            try:
                raw = await self._io(self.gmail.get_message, message.gmail_id)
            except Exception as exc:
                log.warning("sync.held_message_missing", gmail_id=message.gmail_id, error=str(exc))
                continue
            email = normalize_message(raw, body_char_limit=self.settings.body_char_limit)
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

    def _held_matches_key(self, gmail_id: str, label_key: str) -> bool:
        rec = self.session.exec(
            select(ClassificationRecord)
            .where(ClassificationRecord.gmail_id == gmail_id)
            .order_by(ClassificationRecord.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        if rec is not None and rec.proposed_key == label_key:
            return True
        proposal = self.session.exec(
            select(Proposal).where(
                Proposal.gmail_id == gmail_id,
                Proposal.status == ProposalStatus.PENDING,
                Proposal.suggested_key == label_key,
            )
        ).first()
        return proposal is not None
