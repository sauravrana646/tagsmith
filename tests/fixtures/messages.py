"""Real-shaped Gmail messages.get JSON fixtures."""

from __future__ import annotations

import base64
from typing import Any


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8").rstrip("=")


def _msg(
    *,
    gmail_id: str,
    thread_id: str,
    sender: str,
    to: str,
    subject: str,
    date: str,
    body_plain: str | None = None,
    body_html: str | None = None,
    list_unsubscribe: str | None = None,
    attachment_name: str | None = None,
    label_ids: list[str] | None = None,
) -> dict[str, Any]:
    headers = [
        {"name": "From", "value": sender},
        {"name": "To", "value": to},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": date},
    ]
    if list_unsubscribe:
        headers.append({"name": "List-Unsubscribe", "value": list_unsubscribe})

    parts: list[dict[str, Any]] = []
    if body_plain is not None:
        parts.append(
            {
                "mimeType": "text/plain",
                "filename": "",
                "body": {"data": _b64(body_plain), "size": len(body_plain)},
            }
        )
    if body_html is not None:
        parts.append(
            {
                "mimeType": "text/html",
                "filename": "",
                "body": {"data": _b64(body_html), "size": len(body_html)},
            }
        )
    if attachment_name:
        parts.append(
            {
                "mimeType": "application/pdf",
                "filename": attachment_name,
                "body": {"attachmentId": "ATT123", "size": 12345},
            }
        )

    if body_plain is not None and body_html is None and not attachment_name:
        payload: dict[str, Any] = {
            "mimeType": "text/plain",
            "headers": headers,
            "body": {"data": _b64(body_plain), "size": len(body_plain)},
        }
    else:
        payload = {
            "mimeType": "multipart/mixed" if attachment_name else "multipart/alternative",
            "headers": headers,
            "body": {"size": 0},
            "parts": parts,
        }

    snippet = (body_plain or body_html or "")[:80]
    return {
        "id": gmail_id,
        "threadId": thread_id,
        "labelIds": label_ids or ["INBOX", "UNREAD"],
        "snippet": snippet,
        "payload": payload,
    }


PAYMENT_ALERT = _msg(
    gmail_id="msg_payment_1",
    thread_id="thr_payment_1",
    sender="Chase Alerts <no.reply.alerts@chase.com>",
    to="user@example.com",
    subject="You paid $42.50 to Uber",
    date="Mon, 10 Mar 2025 09:15:00 -0400",
    body_plain=(
        "Payment sent\nAmount: $42.50\nTo: Uber\n"
        "Card ending in 1234\nAccount 123456789012 has been debited.\n"
        "If you did not authorize this payment, contact us."
    ),
)

SECURITY_ALERT = _msg(
    gmail_id="msg_security_1",
    thread_id="thr_security_1",
    sender="Google <no-reply@accounts.google.com>",
    to="user@example.com",
    subject="Security alert: new sign-in on Windows device",
    date="Mon, 10 Mar 2025 10:00:00 -0700",
    body_plain=(
        "New sign-in to your Google Account\n"
        "We noticed a new sign-in on a Windows device.\n"
        "If this was you, you don't need to do anything."
    ),
)

OTP_CODE = _msg(
    gmail_id="msg_otp_1",
    thread_id="thr_otp_1",
    sender="GitHub <noreply@github.com>",
    to="user@example.com",
    subject="Your GitHub verification code",
    date="Mon, 10 Mar 2025 11:00:00 +0000",
    body_plain="Your verification code is 482193. It expires in 10 minutes.",
)

NEWSLETTER = _msg(
    gmail_id="msg_news_1",
    thread_id="thr_news_1",
    sender="TLDR AI <news@tldrnewsletter.com>",
    to="user@example.com",
    subject="This week in AI research",
    date="Sun, 9 Mar 2025 08:00:00 +0000",
    body_plain="Welcome to this week's digest of AI papers and launches...",
    list_unsubscribe="<mailto:unsub@tldrnewsletter.com>, <https://example.com/unsub>",
)

HTML_ONLY = _msg(
    gmail_id="msg_html_1",
    thread_id="thr_html_1",
    sender="Shop <deals@merchant.example>",
    to="user@example.com",
    subject="Flash sale — 40% off ends tonight",
    date="Mon, 10 Mar 2025 12:00:00 +0000",
    body_html=(
        "<html><body><h1>Flash sale</h1><p>Save 40% on everything "
        "with code SAVE40. <a href='https://example.com'>Shop now</a></p>"
        "<p>Card 4111111111111111 should not leak.</p></body></html>"
    ),
)

WITH_ATTACHMENT = _msg(
    gmail_id="msg_attach_1",
    thread_id="thr_attach_1",
    sender="Billing <billing@acme.example>",
    to="user@example.com",
    subject="Your March account statement is ready",
    date="Mon, 10 Mar 2025 13:00:00 +0000",
    body_plain="Your March account statement is attached as invoice_march.pdf.",
    attachment_name="invoice_march.pdf",
)

ALL_FIXTURES = [
    PAYMENT_ALERT,
    SECURITY_ALERT,
    OTP_CODE,
    NEWSLETTER,
    HTML_ONLY,
    WITH_ATTACHMENT,
]
