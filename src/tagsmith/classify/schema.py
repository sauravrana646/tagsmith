"""Classification contracts and dynamic closed-set models."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model, field_validator

KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class NewCategory(BaseModel):
    suggested_key: str = Field(description="kebab-case key, e.g. insurance-renewal")
    description: str = Field(
        description="One-line disambiguation instruction for the taxonomy/prompt"
    )
    why_no_existing_fit: str = Field(description="Why none of the existing labels apply")

    @field_validator("suggested_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip().lower().replace("_", "-").replace(" ", "-")
        if not KEBAB_RE.match(value):
            raise ValueError("suggested_key must be kebab-case")
        return value


class Classification(BaseModel):
    """Application-facing classification result."""

    label_key: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str
    proposed_new: NewCategory | None = None


class LabeledEmail(BaseModel):
    """Few-shot example seam for Phase 3 RAG (unused in Phase 1)."""

    subject: str
    sender: str
    body_excerpt: str
    label_key: str


def build_classification_model(label_keys: list[str]) -> type[BaseModel]:
    """Build a Pydantic model whose label_key is a Literal closed set (+ None)."""
    if not label_keys:
        raise ValueError("label_keys must be non-empty")
    label_literal = Literal.__getitem__(tuple([*sorted(label_keys), None]))
    return create_model(
        "DynamicClassification",
        label_key=(label_literal, Field(default=None)),
        confidence=(float, Field(ge=0.0, le=1.0)),
        rationale=(str, ...),
        proposed_new=(NewCategory | None, None),
        __base__=BaseModel,
    )


def to_classification(result: BaseModel | Classification | dict[str, Any]) -> Classification:
    if isinstance(result, Classification):
        return result
    if isinstance(result, BaseModel):
        return Classification.model_validate(result.model_dump())
    return Classification.model_validate(result)


RouteName = Literal["apply", "apply_with_review", "hold_propose"]


def route_classification(
    classification: Classification,
    *,
    apply_threshold: float,
    review_threshold: float,
) -> RouteName:
    """Return apply | apply_with_review | hold_propose."""
    if classification.label_key is None:
        return "hold_propose"
    # Rules (confidence is None) always apply when they produce a label_key.
    if classification.confidence is None:
        return "apply"
    if classification.confidence >= apply_threshold:
        return "apply"
    if classification.confidence >= review_threshold:
        return "apply_with_review"
    return "hold_propose"
