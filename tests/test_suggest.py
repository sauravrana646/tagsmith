from tagsmith.review.suggest import suggest_existing_label


def test_suggest_payment_sent_from_amazon_subject() -> None:
    suggestion = suggest_existing_label(
        active_keys=["payment-sent", "promotion", "order-confirmation"],
        subject="Rs 229.00 was paid on Amazon.in",
        rationale=(
            "A payment confirmation for a charge made on Amazon.in, "
            "indicating money leaving the account for a purchase already completed."
        ),
        body="Thanks for using Amazon Pay Balance. Your payment was successful.",
    )
    assert suggestion is not None
    assert suggestion.label_key == "payment-sent"


def test_suggest_none_when_no_cues() -> None:
    suggestion = suggest_existing_label(
        active_keys=["payment-sent", "promotion"],
        subject="Hello from a friend",
        rationale="Personal note with no taxonomy fit.",
        body="Want to grab coffee?",
    )
    assert suggestion is None
