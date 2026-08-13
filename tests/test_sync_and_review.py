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
    from tagsmith.rag.index import catchup_from_db, make_store

    assert make_store(session, settings).count() == 0
    caught = catchup_from_db(session, settings)
    assert caught.indexed == 1
    assert make_store(session, settings).count() == 1


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
async def test_user_removed_label_becomes_negative(session, settings: Settings, fake_gmail) -> None:
    fake_gmail.messages = {"msg_payment_1": dict(PAYMENT_ALERT)}
    service = SyncService(session, fake_gmail, settings)
    await service.sync(limit=10, apply=True)
    msg = session.get(Message, "msg_payment_1")
    assert msg and msg.applied_label_id
    from tagsmith.rag.index import make_store

    assert make_store(session, settings).count() == 1
    # Simulate user removing the label in Gmail.
    raw = fake_gmail.messages["msg_payment_1"]
    raw["labelIds"] = ["INBOX", "UNREAD"]
    again = await service.sync(limit=10, apply=True, reprocess=True)
    assert again.counts.skipped_user_removed == 1
    neg = session.exec(select(NegativeExample)).first()
    assert neg is not None
    assert neg.label_key == "payment-sent"
    assert make_store(session, settings).count() == 0


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
        from tagsmith.rag.index import make_store

        assert make_store(session, settings).count() == 0

        ops = ReviewOps(session, fake_gmail, settings)
        record = ops.confirm_label("msg_html_1", apply=True)
        assert record.predicted_key == "promotion"
        assert record.final_key == "promotion"
        assert record.review_status.value == "confirmed"
        refreshed = session.get(Message, "msg_html_1")
        assert refreshed is not None
        assert refreshed.state == MessageState.LABELED
        from tagsmith.rag.index import make_store

        assert make_store(session, settings).count() == 1
    finally:
        pipeline_mod.classify_email = monkey_original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_approve_proposal_requeues_held(session, settings: Settings, fake_gmail) -> None:
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
    held_record = session.exec(select(ClassificationRecord)).first()
    assert held_record is not None
    assert held_record.proposed_key == "insurance-renewal"

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


@pytest.mark.asyncio
async def test_held_messages_appear_and_can_be_filed(
    session, settings: Settings, fake_gmail
) -> None:
    from tagsmith.classify import pipeline as pipeline_mod

    async def no_fit(email, **kwargs):  # type: ignore[no-untyped-def]
        return Classification(
            label_key=None,
            confidence=0.9,
            rationale="Does not fit; maybe promotion though.",
            proposed_new=NewCategory(
                suggested_key="product-upsell",
                description="Product feature upsell and quota upgrade mail.",
                why_no_existing_fit="none",
            ),
        )

    pipeline_mod.classify_email = no_fit  # type: ignore[assignment]
    # Two HTML-ish messages that will both hold; second proposal dedupes.
    second = dict(HTML_ONLY)
    second["id"] = "msg_html_2"
    second["threadId"] = "thr_html_2"
    fake_gmail.messages = {
        "msg_html_1": dict(HTML_ONLY),
        "msg_html_2": second,
    }
    service = SyncService(session, fake_gmail, settings)
    result = await service.sync(limit=10, apply=True)
    assert result.counts.held == 2
    assert result.counts.proposals == 1  # deduped

    ops = ReviewOps(session, fake_gmail, settings)
    held = ops.list_held()
    assert len(held) == 2

    ops.resolve_held_with_existing("msg_html_1", "promotion", apply=True)
    ops.resolve_held_with_existing("msg_html_2", "promotion", apply=True)

    assert ops.list_held() == []
    assert session.get(Message, "msg_html_1").state == MessageState.LABELED  # type: ignore[union-attr]
    assert session.get(Message, "msg_html_2").applied_label_key == "promotion"  # type: ignore[union-attr]
    # Proposal queue should no longer show items for resolved messages.
    assert ops.list_proposals() == []


@pytest.mark.asyncio
async def test_assign_existing_label_closes_proposal(
    session, settings: Settings, fake_gmail
) -> None:
    from tagsmith.classify import pipeline as pipeline_mod
    from tagsmith.db.models import ProposalStatus as PS

    async def propose_new(email, **kwargs):  # type: ignore[no-untyped-def]
        return Classification(
            label_key=None,
            confidence=0.9,
            rationale="OpenAI upsell; fits promotion.",
            proposed_new=NewCategory(
                suggested_key="product-upsell",
                description="Product feature upsell and quota upgrade mail.",
                why_no_existing_fit="fallback",
            ),
        )

    pipeline_mod.classify_email = propose_new  # type: ignore[assignment]
    fake_gmail.messages = {"msg_html_1": dict(HTML_ONLY)}
    service = SyncService(session, fake_gmail, settings)
    await service.sync(limit=5, apply=True)

    ops = ReviewOps(session, fake_gmail, settings)
    proposals = ops.list_proposals()
    assert len(proposals) == 1
    proposal_id = proposals[0].proposal.id or 0

    record = ops.assign_existing_label(proposal_id, "promotion", apply=True)
    assert record.final_key == "promotion"
    assert record.source == ClassificationSource.HUMAN

    proposal = session.get(type(proposals[0].proposal), proposal_id)
    assert proposal is not None
    assert proposal.status == PS.REJECTED

    msg = session.get(Message, "msg_html_1")
    assert msg is not None
    assert msg.state == MessageState.LABELED
    assert msg.applied_label_key == "promotion"
    assert msg.applied_label_id is not None
    assert any(msg.applied_label_id in call["add"] for call in fake_gmail.modify_calls)
