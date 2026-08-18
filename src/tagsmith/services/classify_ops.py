"""Single-message classify helpers for MCP / API (Phase 4+5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from tagsmith.classify.pipeline import PipelineResult, classify_with_routing
from tagsmith.classify.rules import load_rules
from tagsmith.config import Settings
from tagsmith.db.models import NegativeExample
from tagsmith.gmail.parser import NormalizedEmail, normalize_message
from tagsmith.gmail.protocol import GmailGateway
from tagsmith.rag.index import make_store
from tagsmith.rag.retriever import Retriever, format_category_hints
from tagsmith.rag.store import example_text_from_email
from tagsmith.services.sync import SyncCounts, SyncService
from tagsmith.taxonomy.registry import TaxonomyRegistry


@dataclass
class ClassifyView:
    gmail_id: str
    label_key: str | None
    confidence: float | None
    route: str
    source: str
    rationale: str
    proposed_new: dict[str, Any] | None
    applied: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "gmail_id": self.gmail_id,
            "label_key": self.label_key,
            "confidence": self.confidence,
            "route": self.route,
            "source": self.source,
            "rationale": self.rationale,
            "proposed_new": self.proposed_new,
            "applied": self.applied,
        }


class ClassifyOps:
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

    def _blocked_keys(self, gmail_id: str) -> set[str]:
        rows = self.session.exec(
            select(NegativeExample).where(NegativeExample.gmail_id == gmail_id)
        ).all()
        return {r.label_key for r in rows}

    async def classify_message(
        self,
        gmail_id: str,
        *,
        apply: bool = False,
        persist: bool = True,
    ) -> ClassifyView:
        """Classify one message. Dry-run by default; apply=True writes Gmail labels."""
        self.taxonomy.ensure_seeded()
        raw = self.gmail.get_message(gmail_id)
        email = normalize_message(raw, body_char_limit=self.settings.body_char_limit)

        if persist:
            sync = SyncService(self.session, self.gmail, self.settings)
            counts = SyncCounts()
            decisions: list[dict[str, Any]] = []
            await sync.process_email(
                email,
                apply=apply,
                reprocess=True,
                counts=counts,
                decisions=decisions,
            )
            decision = decisions[-1] if decisions else {}
            label_key = decision.get("label_key")
            confidence = decision.get("confidence")
            proposed_new = decision.get("proposed_new")
            return ClassifyView(
                gmail_id=gmail_id,
                label_key=label_key if isinstance(label_key, str) else None,
                confidence=confidence if isinstance(confidence, float) else None,
                route=str(decision.get("route") or decision.get("action") or "unknown"),
                source=str(decision.get("source") or "unknown"),
                rationale=str(decision.get("rationale") or ""),
                proposed_new=proposed_new if isinstance(proposed_new, dict) else None,
                applied=bool(decision.get("applied")),
            )

        result = await self._classify_only(email)
        return ClassifyView(
            gmail_id=gmail_id,
            label_key=result.classification.label_key,
            confidence=result.classification.confidence,
            route=result.route,
            source=result.source,
            rationale=result.classification.rationale,
            proposed_new=(
                result.classification.proposed_new.model_dump()
                if result.classification.proposed_new
                else None
            ),
            applied=False,
        )

    async def _classify_only(self, email: NormalizedEmail) -> PipelineResult:
        active_keys = self.taxonomy.active_keys()
        rules = load_rules(self.settings.rules_path, set(active_keys))
        catalog = self.taxonomy.prompt_catalog()
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
            rag_ctx = retriever.retrieve(query, exclude_gmail_ids={email.gmail_id})
            examples = rag_ctx.examples or None
            category_hints = format_category_hints(rag_ctx.category_hints) or None
        return await classify_with_routing(
            email,
            rules=rules,
            label_keys=active_keys,
            catalog=catalog,
            settings=self.settings,
            examples=examples,
            category_hints=category_hints,
            blocked_keys=self._blocked_keys(email.gmail_id),
        )
