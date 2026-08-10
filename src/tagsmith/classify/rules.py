"""Deterministic sender/subject rule engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from tagsmith.classify.schema import Classification
from tagsmith.gmail.parser import NormalizedEmail
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


class RuleValidationError(ValueError):
    pass


@dataclass(slots=True)
class Rule:
    name: str
    label_key: str
    sender_regex: str | None = None
    subject_regex: str | None = None
    body_regex: str | None = None
    require_list_unsubscribe: bool = False
    _sender_re: re.Pattern[str] | None = None
    _subject_re: re.Pattern[str] | None = None
    _body_re: re.Pattern[str] | None = None

    def compile(self) -> Rule:
        self._sender_re = re.compile(self.sender_regex) if self.sender_regex else None
        self._subject_re = re.compile(self.subject_regex) if self.subject_regex else None
        self._body_re = re.compile(self.body_regex) if self.body_regex else None
        return self

    def matches(self, email: NormalizedEmail) -> bool:
        if self.require_list_unsubscribe and not email.list_unsubscribe:
            return False
        if self._sender_re and not self._sender_re.search(email.sender or ""):
            return False
        if self._subject_re and not self._subject_re.search(email.subject or ""):
            return False
        if self._body_re and not self._body_re.search(email.body_text or ""):
            return False
        # At least one positive signal beyond optional list-unsubscribe alone.
        return any([self._sender_re, self._subject_re, self._body_re])


def _parse_rules(data: dict[str, Any], *, source: str) -> list[Rule]:
    rules: list[Rule] = []
    for item in data.get("rules") or []:
        rule = Rule(
            name=str(item["name"]),
            label_key=str(item["label_key"]),
            sender_regex=item.get("sender_regex"),
            subject_regex=item.get("subject_regex"),
            body_regex=item.get("body_regex"),
            require_list_unsubscribe=bool(item.get("require_list_unsubscribe", False)),
        ).compile()
        rules.append(rule)
    log.debug("rules.loaded", source=source, count=len(rules))
    return rules


def load_builtin_rules() -> list[Rule]:
    text = (
        resources.files("tagsmith.classify")
        .joinpath("builtin_rules.yaml")
        .read_text(encoding="utf-8")
    )
    return _parse_rules(yaml.safe_load(text) or {}, source="builtin")


def load_user_rules(path: Path) -> list[Rule]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _parse_rules(data, source=str(path))


def merge_rules(builtin: list[Rule], user: list[Rule]) -> list[Rule]:
    """User rules win on name conflict; user rules are tried first."""
    by_name = {r.name: r for r in builtin}
    for rule in user:
        by_name[rule.name] = rule
    # Preserve user order first, then remaining builtin.
    user_names = {r.name for r in user}
    ordered = list(user) + [r for r in builtin if r.name not in user_names]
    return ordered


def validate_rules(rules: list[Rule], active_keys: set[str]) -> None:
    bad = sorted({r.label_key for r in rules if r.label_key not in active_keys})
    if bad:
        raise RuleValidationError(
            "Rules reference unknown or inactive taxonomy keys: " + ", ".join(bad)
        )


def load_rules(user_rules_path: Path, active_keys: set[str]) -> list[Rule]:
    rules = merge_rules(load_builtin_rules(), load_user_rules(user_rules_path))
    validate_rules(rules, active_keys)
    return rules


def match_rules(email: NormalizedEmail, rules: list[Rule]) -> Classification | None:
    for rule in rules:
        if rule.matches(email):
            return Classification(
                label_key=rule.label_key,
                confidence=None,  # intentionally NULL for calibration hygiene
                rationale=f"Matched rule '{rule.name}'",
                proposed_new=None,
            )
    return None
