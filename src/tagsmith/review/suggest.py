"""Heuristic label suggestions for human review (not used for auto-apply)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Ordered: first match wins. Patterns run against subject + rationale + body snippet.
_HINTS: list[tuple[str, re.Pattern[str]]] = [
    (
        "payment-sent",
        re.compile(
            r"(?i)(\bwas paid\b|\byou paid\b|payment (was )?successful|money leaving|"
            r"\bdebited\b|\bcharged\b|payment confirmation for a charge)"
        ),
    ),
    (
        "payment-received",
        re.compile(
            r"(?i)(\byou received\b|payment received|money (arriving|received)|"
            r"\bcredited\b|direct deposit)"
        ),
    ),
    (
        "shipping-update",
        re.compile(r"(?i)(\bshipped\b|out for delivery|\bdelivered\b|\btracking\b)"),
    ),
    (
        "order-confirmation",
        re.compile(r"(?i)(\bordered\b|order confirmed|thanks for your order)"),
    ),
    (
        "security-alert",
        re.compile(r"(?i)(security alert|new sign-?in|\bsign-in\b|password (was )?changed)"),
    ),
    (
        "otp-verification",
        re.compile(r"(?i)(verification code|one-?time|\botp\b|passcode)"),
    ),
    (
        "refund",
        re.compile(r"(?i)(\brefund\b|charge reversed|return is complete)"),
    ),
    (
        "promotion",
        re.compile(
            r"(?i)(\bupsell\b|\bpromo(?:tion)?\b|\bsale\b|\boffer\b|flash sale|"
            r"save up to|marketing)"
        ),
    ),
    (
        "newsletter",
        re.compile(r"(?i)(\bnewsletter\b|\bdigest\b|weekly roundup|this week in)"),
    ),
]


@dataclass(slots=True)
class LabelSuggestion:
    label_key: str
    reason: str


def suggest_existing_label(
    *,
    active_keys: list[str],
    subject: str = "",
    rationale: str = "",
    body: str = "",
) -> LabelSuggestion | None:
    """Best-effort suggestion for review UI — never auto-applied."""
    active = set(active_keys)
    blob = f"{subject}\n{rationale}\n{body[:400]}"
    for key, pattern in _HINTS:
        if key in active and pattern.search(blob):
            return LabelSuggestion(label_key=key, reason=f"matched cues for '{key}'")
    # Fall back: exact key / spaced key mentioned in rationale.
    lowered = rationale.lower()
    for key in active_keys:
        if key in lowered or key.replace("-", " ") in lowered:
            return LabelSuggestion(label_key=key, reason="mentioned in model rationale")
    return None
