"""Rebuild a Gmail-shaped message dict from a stored normalized payload."""

from __future__ import annotations

import base64
from typing import Any


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8").rstrip("=")


def normalized_payload_to_gmail_message(
    *,
    gmail_id: str,
    thread_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Best-effort `messages.get` reconstruction for golden-set export."""
    sender = str(payload.get("sender") or "")
    to = str(payload.get("to") or "")
    subject = str(payload.get("subject") or "")
    date = str(payload.get("date") or "")
    body = str(payload.get("body_text") or "")
    list_unsub = payload.get("list_unsubscribe")
    headers = [
        {"name": "From", "value": sender},
        {"name": "To", "value": to},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": date},
    ]
    if list_unsub:
        headers.append({"name": "List-Unsubscribe", "value": str(list_unsub)})
    return {
        "id": gmail_id,
        "threadId": thread_id,
        "labelIds": list(payload.get("label_ids") or ["INBOX"]),
        "snippet": str(payload.get("snippet") or body[:80]),
        "payload": {
            "mimeType": "text/plain",
            "headers": headers,
            "body": {"data": _b64(body), "size": len(body)},
        },
    }
