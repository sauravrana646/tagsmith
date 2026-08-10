"""Rules → LLM → threshold routing for a single email."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tagsmith.classify.agent import classify_email
from tagsmith.classify.rules import Rule, match_rules
from tagsmith.classify.schema import Classification, LabeledEmail, route_classification
from tagsmith.config import Settings
from tagsmith.gmail.parser import NormalizedEmail
from tagsmith.telemetry import get_logger

log = get_logger(__name__)

Route = Literal["apply", "apply_with_review", "hold_propose"]
Source = Literal["rule", "llm"]


@dataclass(slots=True)
class PipelineResult:
    classification: Classification
    route: Route
    source: Source


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

    classification = await classify_email(
        email,
        label_keys=label_keys,
        catalog=catalog,
        settings=settings,
        examples=examples,
    )
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
    )
    return PipelineResult(classification=classification, route=route, source="llm")
