from tests.fixtures.messages import HTML_ONLY, PAYMENT_ALERT, WITH_ATTACHMENT

from tagsmith.gmail.parser import normalize_message, redact_sensitive


def test_redact_digit_runs() -> None:
    assert "[REDACTED]" in redact_sensitive("Account 123456789012 charged $12.50")
    assert "$12.50" in redact_sensitive("Account 123456789012 charged $12.50")
    assert "482193" in redact_sensitive("code 482193")  # 6 digits survive


def test_normalize_payment_alert() -> None:
    email = normalize_message(PAYMENT_ALERT)
    assert email.gmail_id == "msg_payment_1"
    assert "Uber" in email.subject
    payload = email.classifier_payload(2000)
    assert "From:" in payload
    assert "[REDACTED]" in payload
    assert "123456789012" not in payload


def test_html_only_fallback() -> None:
    email = normalize_message(HTML_ONLY)
    assert "Flash sale" in email.body_text
    payload = email.classifier_payload(2000)
    assert "4111111111111111" not in payload
    assert "[REDACTED]" in payload


def test_attachment_filename_only() -> None:
    email = normalize_message(WITH_ATTACHMENT)
    assert email.attachment_names == ["invoice_march.pdf"]
    payload = email.classifier_payload(2000)
    assert "invoice_march.pdf" in payload
