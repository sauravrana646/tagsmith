"""Rules → LLM → threshold routing for a single email."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from tagsmith.classify.agent import classify_email
from tagsmith.classify.outcome import ClassifyOutcome
from tagsmith.classify.rules import Rule, match_rules
from tagsmith.classify.schema import Classification, LabeledEmail, route_classification
from tagsmith.config import Settings
from tagsmith.gmail.parser import NormalizedEmail
from tagsmith.telemetry import get_logger, span

log = get_logger(__name__)

Route = Literal["apply", "apply_with_review", "hold_propose"]
Source = Literal["rule", "llm"]


@dataclass(slots=True)
class PipelineResult:
    classification: Classification
    route: Route
    source: Source
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


async def _coerce_outcome(raw: Classification | ClassifyOutcome | Any) -> ClassifyOutcome:
    if isinstance(raw, ClassifyOutcome):
        return raw
    if isinstance(raw, Classification):
        return ClassifyOutcome(classification=raw)
    # Defensive: some stubs may return a model dump-like object.
    if hasattr(raw, "classification"):
        return raw  # type: ignore[no-any-return]
    raise TypeError(f"Unexpected classify_email return type: {type(raw)!r}")


async def classify_with_routing(
    email: NormalizedEmail,
    *,
    rules: list[Rule],
    label_keys: list[str],
    catalog: str,
    settings: Settings,
    examples: list[LabeledEmail] | None = None,
    blocked_keys: set[str] | None = None,
) -> PipelineResult:
    blocked = blocked_keys or set()

    with span("tagsmith.classify.pipeline", gmail_id=email.gmail_id):
        ruled = match_rules(email, rules)
        if ruled and ruled.label_key and ruled.label_key not in blocked:
            route = route_classification(
                ruled,
                apply_threshold=settings.confidence_apply,
                review_threshold=settings.confidence_review,
            )
            log.info(
                "classify.route",
                gmail_id=email.gmail_id,
                source="rule",
                route=route,
                label_key=ruled.label_key,
                confidence=ruled.confidence,
            )
            return PipelineResult(classification=ruled, route=route, source="rule")

        outcome = await _coerce_outcome(
            await classify_email(
                email,
                label_keys=label_keys,
                catalog=catalog,
                settings=settings,
                examples=examples,
            )
        )
        classification = outcome.classification
        if classification.label_key in blocked:
            # Treat blocked (user-removed) prediction as no-fit.
            classification = classification.model_copy(
                update={
                    "label_key": None,
                    "rationale": (
                        classification.rationale
                        + f" (blocked re-apply of user-removed label '{classification.label_key}')"
                    ),
                }
            )

        route = route_classification(
            classification,
            apply_threshold=settings.confidence_apply,
            review_threshold=settings.confidence_review,
        )
        log.info(
            "classify.route",
            gmail_id=email.gmail_id,
            source="llm",
            route=route,
            label_key=classification.label_key,
            confidence=classification.confidence,
            latency_ms=outcome.latency_ms,
            tokens=outcome.total_tokens,
        )
        return PipelineResult(
            classification=classification,
            route=route,
            source="llm",
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            latency_ms=outcome.latency_ms,
        )
