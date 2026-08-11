"""Classifier fallback when structured output fails."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from tagsmith.classify.agent import _fallback_hold, classify_email
from tagsmith.config import Settings
from tagsmith.gmail.parser import NormalizedEmail


def test_fallback_hold_has_proposal() -> None:
    email = NormalizedEmail(
        gmail_id="g1",
        thread_id="t1",
        sender="a@b.com",
        to="u@example.com",
        subject="HOA meeting agenda",
        date=None,
        list_unsubscribe=None,
        body_text="Please vote on the budget.",
    )
    c = _fallback_hold(email, reason="Exceeded maximum output retries (1)")
    assert c.label_key is None
    assert c.proposed_new is not None
    assert "Model output invalid" in c.rationale


@pytest.mark.asyncio
async def test_classify_email_falls_back_on_unexpected_behavior(
    settings: Settings,
) -> None:
    class BoomAgent:
        async def run(self, _prompt: str) -> object:
            raise UnexpectedModelBehavior("Exceeded maximum output retries (1)")

    email = NormalizedEmail(
        gmail_id="g2",
        thread_id="t2",
        sender="a@b.com",
        to="u@example.com",
        subject="Lab results ready",
        date=None,
        list_unsubscribe=None,
        body_text="New results in portal.",
    )
    outcome = await classify_email(
        email,
        label_keys=["promotion", "newsletter"],
        catalog="- promotion: sales",
        settings=settings,
        agent=BoomAgent(),
    )
    assert outcome.classification.label_key is None
    assert outcome.classification.proposed_new is not None
    assert outcome.latency_ms is not None
