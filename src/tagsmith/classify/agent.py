"""Pydantic AI classifier with closed-set label keys."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic_ai import Agent

from tagsmith.classify.schema import (
    Classification,
    LabeledEmail,
    build_classification_model,
    to_classification,
)
from tagsmith.config import PROMPT_VERSION, Settings
from tagsmith.gmail.parser import NormalizedEmail
from tagsmith.telemetry import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You classify a single email into exactly one taxonomy label.

Rules:
- Choose label_key from the provided closed set when one fits.
- If none fit, set label_key to null and fill proposed_new with a kebab-case key,
  a one-line disambiguation description, and why existing labels fail.
- confidence is coarse triage from 0 to 1, not a calibrated probability.
- rationale must be one sentence.
- Prefer transactional meaning over marketing tone when both appear.
- List-Unsubscribe strongly suggests newsletter or promotion; use subject/body to pick.
"""


def _examples_block(examples: Sequence[LabeledEmail]) -> str:
    if not examples:
        return ""
    lines = ["Similar previously labeled emails:"]
    for ex in examples:
        lines.append(
            f"- label={ex.label_key} | from={ex.sender} | subject={ex.subject}\n"
            f"  excerpt: {ex.body_excerpt}"
        )
    return "\n".join(lines)


def build_user_prompt(
    email: NormalizedEmail,
    *,
    catalog: str,
    char_limit: int,
    examples: Sequence[LabeledEmail] | None = None,
) -> str:
    parts = [
        "Active taxonomy:",
        catalog,
        "",
        _examples_block(examples or []),
        "",
        "Email to classify:",
        email.classifier_payload(char_limit),
    ]
    return "\n".join(p for p in parts if p is not None).strip() + "\n"


async def classify_email(
    email: NormalizedEmail,
    *,
    label_keys: list[str],
    catalog: str,
    settings: Settings,
    examples: Sequence[LabeledEmail] | None = None,
    agent: Any | None = None,
) -> Classification:
    """Classify one email.

    `examples` is the Phase 3 RAG seam — accepted now, unused by callers in Phase 1.
    """
    result_type = build_classification_model(label_keys)
    if agent is None:
        # Dynamic closed-set output model; Agent is intentionally loosely typed here.
        agent = Agent(
            settings.llm_model,
            output_type=result_type,
            system_prompt=SYSTEM_PROMPT,
        )

    prompt = build_user_prompt(
        email,
        catalog=catalog,
        char_limit=settings.body_char_limit,
        examples=examples,
    )
    log.info(
        "classify.llm.start",
        gmail_id=email.gmail_id,
        model=settings.llm_model,
        prompt_version=PROMPT_VERSION,
    )
    result = await agent.run(prompt)
    classification = to_classification(result.output)
    log.info(
        "classify.llm.done",
        gmail_id=email.gmail_id,
        label_key=classification.label_key,
        confidence=classification.confidence,
        has_proposal=classification.proposed_new is not None,
    )
    return classification
