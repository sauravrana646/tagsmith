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
        route_classification(mid, apply_threshold=0.75, review_threshold=0.5) == "apply_with_review"
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


def test_new_category_strips_punctuation() -> None:
    n = NewCategory(
        suggested_key="Home Insurance!!",
        description="renewal packets",
        why_no_existing_fit="no insurance label",
    )
    assert n.suggested_key == "home-insurance"


def test_dynamic_model_coerces_string_confidence() -> None:
    from tagsmith.classify.schema import build_classification_model

    model = build_classification_model(["promotion", "newsletter"])
    obj = model.model_validate(
        {
            "label_key": "promotion",
            "confidence": "0.91",
            "rationale": "sale email",
            "proposed_new": None,
        }
    )
    assert obj.confidence == 0.91


def test_dynamic_model_null_string_label_requires_proposal() -> None:
    from tagsmith.classify.schema import build_classification_model

    model = build_classification_model(["promotion"])
    with pytest.raises(ValueError, match="proposed_new"):
        model.model_validate(
            {
                "label_key": "null",
                "confidence": 0.5,
                "rationale": "no fit",
                "proposed_new": None,
            }
        )
