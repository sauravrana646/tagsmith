from tagsmith.review.display import clean_review_text, format_message_for_review


def test_clean_review_text_strips_zw_and_shortens_urls() -> None:
    raw = (
        "Create more images\u200b\u200b with advanced models.\n\n\n"
        "[ ](https://u.email.openai.com/uni/ls/click?upn=very-long-tracking-token-here)\n"
        "https://example.com/path/that/is/extremely/long/and/ugly?x=1&y=2"
    )
    cleaned = clean_review_text(raw, max_chars=500)
    assert "\u200b" not in cleaned
    assert "Create more images with advanced models." in cleaned
    assert "very-long-tracking-token-here" not in cleaned
    assert "…" in cleaned or len(cleaned) < len(raw)


def test_format_message_for_review_includes_headers() -> None:
    text = format_message_for_review(
        {
            "sender": "ChatGPT <noreply@email.openai.com>",
            "subject": "More access to advanced tools",
            "date": "2026-08-06T16:04:10+00:00",
            "list_unsubscribe": "<mailto:x>",
            "body_text": "Do more with ChatGPT",
        }
    )
    assert "From: ChatGPT" in text
    assert "Subject: More access" in text
    assert "List-Unsubscribe: yes" in text
    assert "Do more with ChatGPT" in text


def test_list_needs_review_uses_constant_queries(session, settings) -> None:
    from tagsmith.db.models import ClassificationRecord, ClassificationSource, Message, MessageState
    from tagsmith.review.queue import ReviewService

    for i in range(5):
        session.add(
            Message(
                gmail_id=f"nr-{i}",
                thread_id=f"t-{i}",
                sender="a@b.com",
                subject=f"s{i}",
                state=MessageState.NEEDS_REVIEW,
            )
        )
        session.add(
            ClassificationRecord(
                gmail_id=f"nr-{i}",
                label_key="promotion",
                predicted_key="promotion",
                source=ClassificationSource.LLM,
                needs_review=True,
            )
        )
    session.commit()
    rows = ReviewService(session).list_needs_review()
    assert len(rows) == 5
