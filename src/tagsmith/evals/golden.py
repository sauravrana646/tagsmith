"""Golden-set schema and loaders for Phase 2 evals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

ExpectedRoute = Literal["apply", "apply_with_review", "hold_propose"]


class GoldenCase(BaseModel):
    """One hand-labeled email used as ground truth.

    `expected_label_key=None` means the case should be held / no existing label fit.
    """

    id: str
    expected_label_key: str | None = None
    expected_route: ExpectedRoute | None = None
    notes: str = ""
    # Full Gmail `messages.get`-shaped payload (same as test fixtures).
    message: dict[str, Any] = Field(min_length=1)


def load_golden_set(path: Path) -> list[GoldenCase]:
    if not path.exists():
        raise FileNotFoundError(f"Golden set not found: {path}")
    cases: list[GoldenCase] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            cases.append(GoldenCase.model_validate(payload))
    if not cases:
        raise ValueError(f"Golden set is empty: {path}")
    return cases


def dump_golden_set(path: Path, cases: list[GoldenCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(case.model_dump_json() + "\n")
