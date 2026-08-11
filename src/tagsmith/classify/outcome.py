"""LLM/classify outcome with Phase 2 metrics."""

from __future__ import annotations

from dataclasses import dataclass

from tagsmith.classify.schema import Classification


@dataclass(slots=True)
class ClassifyOutcome:
    """Classification plus optional usage/latency for evals and observability."""

    classification: Classification
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)
