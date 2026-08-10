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
- Choose label_key from the provided closed set whenever one fits — even partially.
- Do NOT set label_key to null if your rationale describes an existing category.
  Example: if the email is a completed purchase debit / "was paid" confirmation,
  label_key must be payment-sent, not null.
- If no existing label is a reasonable fit, set label_key to null AND you MUST fill
  proposed_new with:
    - suggested_key: specific kebab-case category (never placeholders like
      uncategorized-followup / other / unknown)
    - description: one-line disambiguation instruction for future prompts
    - why_no_existing_fit: why the closed set fails
- If you pick an existing label_key but confidence is below 0.5 (guessy), still set
  that label_key as your best guess AND also fill proposed_new with a better new
  category alternative for the human reviewer.
- confidence is coarse triage from 0 to 1, not a calibrated probability.
- rationale must be one sentence and must name the chosen label_key when set.
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
