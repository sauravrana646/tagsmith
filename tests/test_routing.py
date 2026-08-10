import pytest

from tagsmith.classify.schema import Classification, NewCategory, route_classification


def test_none_label_is_hold() -> None:
    c = Classification(
        label_key=None,
        confidence=0.9,
        rationale="no fit",
        proposed_new=NewCategory(
            suggested_key="insurance-renewal",
            description="policy renewals",
            why_no_existing_fit="not subscription-renewal",
        ),
    )
    assert route_classification(c, apply_threshold=0.75, review_threshold=0.5) == "hold_propose"


def test_none_label_requires_proposal() -> None:
    with pytest.raises(ValueError, match="proposed_new"):
        Classification(label_key=None, confidence=0.9, rationale="no fit")


def test_thresholds() -> None:
    high = Classification(label_key="refund", confidence=0.8, rationale="x")
    mid = Classification(label_key="refund", confidence=0.6, rationale="x")
    low = Classification(
        label_key="refund",
        confidence=0.4,
        rationale="x",
        proposed_new=NewCategory(
            suggested_key="chargeback-notice",
            description="bank chargeback notices",
            why_no_existing_fit="not a completed refund credit",
        ),
    )
    assert route_classification(high, apply_threshold=0.75, review_threshold=0.5) == "apply"
    assert (
        route_classification(mid, apply_threshold=0.75, review_threshold=0.5)
        == "apply_with_review"
    )
    assert route_classification(low, apply_threshold=0.75, review_threshold=0.5) == "hold_propose"


def test_rule_null_confidence_applies() -> None:
    c = Classification(label_key="payment-sent", confidence=None, rationale="rule")
    assert route_classification(c, apply_threshold=0.75, review_threshold=0.5) == "apply"


def test_new_category_key_normalization() -> None:
    n = NewCategory(
        suggested_key="Insurance_Renewal",
        description="renewal notices",
        why_no_existing_fit="not a subscription SaaS renew",
    )
    assert n.suggested_key == "insurance-renewal"


def test_new_category_rejects_placeholder() -> None:
    with pytest.raises(ValueError, match="specific category"):
        NewCategory(
            suggested_key="uncategorized-followup",
            description="x",
            why_no_existing_fit="y",
        )
