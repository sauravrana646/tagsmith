"""Pydantic AI classifier with closed-set label keys."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from typing import Any

from pydantic_ai import Agent, AgentRetries
from pydantic_ai.exceptions import UnexpectedModelBehavior

from tagsmith.classify.outcome import ClassifyOutcome
from tagsmith.classify.schema import (
    Classification,
    LabeledEmail,
    NewCategory,
    build_classification_model,
    to_classification,
)
from tagsmith.config import PROMPT_VERSION, Settings
from tagsmith.gmail.parser import NormalizedEmail
from tagsmith.telemetry import get_logger, span

log = get_logger(__name__)

SYSTEM_PROMPT = """You classify a single email into exactly one taxonomy label.

Rules:
- Choose label_key from the provided closed set whenever one fits — even partially.
- label_key MUST be exactly one of the catalog keys, or JSON null. Never invent keys.
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
- confidence is a number from 0 to 1 (not a string).
- rationale must be one sentence and must name the chosen label_key when set.
- Prefer transactional meaning over marketing tone when both appear.
- List-Unsubscribe strongly suggests newsletter or promotion; use subject/body to pick.
- Always return valid JSON matching the schema. proposed_new is REQUIRED when
  label_key is null.
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


def _usage_tokens(result: Any) -> tuple[int | None, int | None]:
    usage_fn = getattr(result, "usage", None)
    usage = usage_fn() if callable(usage_fn) else usage_fn
    if usage is None:
        return None, None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    return (
        int(input_tokens) if input_tokens is not None else None,
        int(output_tokens) if output_tokens is not None else None,
    )


def _fallback_hold(email: NormalizedEmail, *, reason: str) -> Classification:
    """Safe hold when the model cannot produce valid structured output."""
    slug = re.sub(r"[^a-z0-9]+", "-", email.subject.lower()).strip("-")
    parts = [p for p in slug.split("-") if p][:4]
    slug = "-".join(parts) or "needs-human-review"
    if slug in {"uncategorized-followup", "unknown", "other", "misc"}:
        slug = "needs-human-review"
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        slug = "needs-human-review"
    try:
        proposed = NewCategory(
            suggested_key=slug,
            description=f"Human should refine category for: {email.subject[:80]}",
            why_no_existing_fit=reason[:500],
        )
    except ValueError:
        proposed = NewCategory(
            suggested_key="needs-human-review",
            description=f"Human should refine category for: {email.subject[:80]}",
            why_no_existing_fit=reason[:500],
        )
    return Classification(
        label_key=None,
        confidence=0.0,
        rationale=f"Model output invalid; held for review. ({reason[:200]})",
        proposed_new=proposed,
    )


async def classify_email(
    email: NormalizedEmail,
    *,
    label_keys: list[str],
    catalog: str,
    settings: Settings,
    examples: Sequence[LabeledEmail] | None = None,
    agent: Any | None = None,
) -> ClassifyOutcome:
    """Classify one email.

    `examples` is the Phase 3 RAG seam — accepted now, unused by callers in Phase 1/2.
    """
    result_type = build_classification_model(label_keys)
    retries = max(1, int(settings.llm_output_retries))
    if agent is None:
        # Dynamic closed-set output model; Agent is intentionally loosely typed here.
        agent = Agent(
            settings.llm_model,
            output_type=result_type,
            system_prompt=SYSTEM_PROMPT,
            retries=AgentRetries(output=retries, tools=1),
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
    started = time.perf_counter()
    with span(
        "tagsmith.classify.llm",
        gmail_id=email.gmail_id,
        model=settings.llm_model,
        prompt_version=PROMPT_VERSION,
    ):
        try:
            result = await agent.run(prompt)
        except UnexpectedModelBehavior as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            cause = getattr(exc, "__cause__", None)
            detail = f"{exc}" + (f" | cause={cause}" if cause else "")
            log.warning(
                "classify.llm.invalid_output",
                gmail_id=email.gmail_id,
                error=detail,
                latency_ms=round(latency_ms, 2),
            )
            return ClassifyOutcome(
                classification=_fallback_hold(email, reason=detail),
                input_tokens=None,
                output_tokens=None,
                latency_ms=latency_ms,
            )

    latency_ms = (time.perf_counter() - started) * 1000.0
    classification = to_classification(result.output)
    input_tokens, output_tokens = _usage_tokens(result)
    log.info(
        "classify.llm.done",
        gmail_id=email.gmail_id,
        label_key=classification.label_key,
        confidence=classification.confidence,
        has_proposal=classification.proposed_new is not None,
        latency_ms=round(latency_ms, 2),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return ClassifyOutcome(
        classification=classification,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
