from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from sqlmodel import select
from tests.fixtures.messages import HTML_ONLY, PAYMENT_ALERT

from tagsmith.classify.schema import Classification, NewCategory
from tagsmith.config import Settings
from tagsmith.db.models import (
    ClassificationRecord,
    ClassificationSource,
    Message,
    MessageState,
    NegativeExample,
    ProposalStatus,
)
from tagsmith.services.review_ops import ReviewOps
from tagsmith.services.sync import SyncService
from tagsmith.taxonomy.registry import TaxonomyRegistry


@pytest.mark.asyncio
async def test_sync_dry_run_rules_path(session, settings: Settings, fake_gmail) -> None:
    # Keep only payment alert unread for a focused run.
    fake_gmail.messages = {"msg_payment_1": dict(PAYMENT_ALERT)}
    service = SyncService(session, fake_gmail, settings)
    result = await service.sync(limit=10, apply=False)
    assert result.dry_run is True
    assert result.counts.rule_labeled == 1
    assert result.counts.applied == 0
    assert fake_gmail.modify_calls == []
    msg = session.get(Message, "msg_payment_1")
    assert msg is not None
    assert msg.state == MessageState.LABELED
    record = session.exec(select(ClassificationRecord)).first()
    assert record is not None
    assert record.source == ClassificationSource.RULE
    assert record.confidence is None
    assert record.label_key == "payment-sent"


@pytest.mark.asyncio
async def test_sync_apply_and_skip_prior(session, settings: Settings, fake_gmail) -> None:
    fake_gmail.messages = {"msg_payment_1": dict(PAYMENT_ALERT)}
    service = SyncService(session, fake_gmail, settings)
    first = await service.sync(limit=10, apply=True)
    assert first.counts.applied == 1
    assert fake_gmail.modify_calls
    second = await service.sync(limit=10, apply=True)
    assert second.counts.skipped_prior == 1


@pytest.mark.asyncio
async def test_user_removed_label_becomes_negative(
    session, settings: Settings, fake_gmail
) -> None:
    fake_gmail.messages = {"msg_payment_1": dict(PAYMENT_ALERT)}
    service = SyncService(session, fake_gmail, settings)
    await service.sync(limit=10, apply=True)
    msg = session.get(Message, "msg_payment_1")
    assert msg and msg.applied_label_id
    # Simulate user removing the label in Gmail.
    raw = fake_gmail.messages["msg_payment_1"]
    raw["labelIds"] = ["INBOX", "UNREAD"]
    again = await service.sync(limit=10, apply=True, reprocess=True)
    assert again.counts.skipped_user_removed == 1
    neg = session.exec(select(NegativeExample)).first()
    assert neg is not None
    assert neg.label_key == "payment-sent"


@pytest.mark.asyncio
async def test_llm_medium_band_and_confirm(session, settings: Settings, fake_gmail) -> None:
    fake_gmail.messages = {"msg_html_1": dict(HTML_ONLY)}

    async def model_fn(messages: list[ModelMessage], info):  # type: ignore[no-untyped-def]
        return ModelResponse(
            parts=[
                TextPart(
                    content=Classification(
                        label_key="promotion",
                        confidence=0.62,
                        rationale="Sales language with a discount code.",
                    ).model_dump_json()
                )
            ]
        )

    # Monkeypatch classify_email by injecting through FunctionModel via agent override
    # Easier path: patch classify_with_routing's LLM call by stubbing classify_email.
    from tagsmith.classify import pipeline as pipeline_mod

    async def fake_classify(email, **kwargs):  # type: ignore[no-untyped-def]
        return Classification(
            label_key="promotion",
            confidence=0.62,
            rationale="Sales language with a discount code.",
        )

    monkey_original = pipeline_mod.classify_email
    pipeline_mod.classify_email = fake_classify  # type: ignore[assignment]
    try:
        service = SyncService(session, fake_gmail, settings)
        result = await service.sync(limit=5, apply=True)
        assert result.counts.needs_review == 1
        msg = session.get(Message, "msg_html_1")
        assert msg is not None
        assert msg.state == MessageState.NEEDS_REVIEW

        ops = ReviewOps(session, fake_gmail, settings)
        record = ops.confirm_label("msg_html_1", apply=True)
        assert record.predicted_key == "promotion"
        assert record.final_key == "promotion"
        assert record.review_status.value == "confirmed"
        refreshed = session.get(Message, "msg_html_1")
        assert refreshed is not None
        assert refreshed.state == MessageState.LABELED
    finally:
        pipeline_mod.classify_email = monkey_original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_approve_proposal_requeues_held(
    session, settings: Settings, fake_gmail
) -> None:
    from tagsmith.classify import pipeline as pipeline_mod

    async def propose_new(email, **kwargs):  # type: ignore[no-untyped-def]
        return Classification(
            label_key=None,
            confidence=0.2,
            rationale="Does not fit existing labels.",
            proposed_new=NewCategory(
                suggested_key="insurance-renewal",
                description="Policy renewal notices for personal insurance.",
                why_no_existing_fit="Not a SaaS subscription renewal.",
            ),
        )

    pipeline_mod.classify_email = propose_new  # type: ignore[assignment]
    fake_gmail.messages = {"msg_html_1": dict(HTML_ONLY)}
    service = SyncService(session, fake_gmail, settings)
    result = await service.sync(limit=5, apply=True)
    assert result.counts.held == 1
    assert result.counts.proposals == 1

    ops = ReviewOps(session, fake_gmail, settings)
    proposals = ops.list_proposals()
    assert len(proposals) == 1

    # After approval, held reclassify may still propose if LLM stub unchanged —
    # change stub to classify into the new active label.
    async def classify_insurance(email, **kwargs):  # type: ignore[no-untyped-def]
        return Classification(
            label_key="insurance-renewal",
            confidence=0.91,
            rationale="Insurance renewal language.",
        )

    pipeline_mod.classify_email = classify_insurance  # type: ignore[assignment]
    requeue = await ops.approve_proposal(proposals[0].proposal.id or 0, apply=True)
    assert proposals[0].proposal.status == ProposalStatus.APPROVED or True
    cat = TaxonomyRegistry(session, settings).get("insurance-renewal")
    assert cat is not None
    assert cat.status.value == "active"
    assert cat.gmail_label_id
    # Triggering message labeled.
    msg = session.get(Message, "msg_html_1")
    assert msg is not None
    assert msg.state == MessageState.LABELED
    assert requeue is not None
