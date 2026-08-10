import pytest
from tests.fixtures.messages import NEWSLETTER, OTP_CODE, PAYMENT_ALERT, SECURITY_ALERT

from tagsmith.classify.rules import RuleValidationError, load_rules, match_rules
from tagsmith.gmail.parser import normalize_message
from tagsmith.taxonomy.registry import load_seed_categories


def test_builtin_rules_validate_against_seed(settings, session) -> None:
    keys = {c.key for c in load_seed_categories()}
    rules = load_rules(settings.rules_path, keys)
    assert rules
    # payment alert should match chase rule
    email = normalize_message(PAYMENT_ALERT)
    hit = match_rules(email, rules)
    assert hit is not None
    assert hit.label_key == "payment-sent"
    assert hit.confidence is None
    assert hit.rationale.startswith("Matched rule")


def test_security_and_otp_rules(settings, session) -> None:
    keys = {c.key for c in load_seed_categories()}
    rules = load_rules(settings.rules_path, keys)
    sec = match_rules(normalize_message(SECURITY_ALERT), rules)
    assert sec is not None and sec.label_key == "security-alert"
    otp = match_rules(normalize_message(OTP_CODE), rules)
    assert otp is not None and otp.label_key == "otp-verification"
    news = match_rules(normalize_message(NEWSLETTER), rules)
    assert news is not None and news.label_key == "newsletter"


def test_stale_rule_fails_loudly(settings, tmp_path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        """
rules:
  - name: stale
    label_key: not-a-real-category
    subject_regex: "(?i)hello"
""",
        encoding="utf-8",
    )
    settings.rules_path = path
    with pytest.raises(RuleValidationError, match="not-a-real-category"):
        load_rules(settings.rules_path, {c.key for c in load_seed_categories()})
