"""MIME normalization: headers + clean text, privacy-safe payload shaping."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import html2text

DIGIT_RUN_RE = re.compile(r"\d{9,}")
WHITESPACE_RE = re.compile(r"[ \t]+")
MULTI_NL_RE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class NormalizedEmail:
    gmail_id: str
    thread_id: str
    sender: str
    to: str
    subject: str
    date: datetime | None
    list_unsubscribe: str | None
    body_text: str
    attachment_names: list[str] = field(default_factory=list)
    label_ids: list[str] = field(default_factory=list)
    snippet: str = ""

    @property
    def body_hash(self) -> str:
        return hashlib.sha256(self.body_text.encode("utf-8")).hexdigest()

    def classifier_payload(self, char_limit: int = 2000) -> str:
        """Build the privacy-safe text sent to rules/LLM."""
        header_lines = [
            f"From: {self.sender}",
            f"To: {self.to}",
            f"Subject: {self.subject}",
            f"Date: {self.date.isoformat() if self.date else ''}",
        ]
        if self.list_unsubscribe:
            header_lines.append(f"List-Unsubscribe: {self.list_unsubscribe}")
        if self.attachment_names:
            header_lines.append(f"Attachments: {', '.join(self.attachment_names)}")

        body = redact_sensitive(self.body_text)
        if len(body) > char_limit:
            body = body[:char_limit].rstrip() + "\n…[truncated]"
        return "\n".join(header_lines) + "\n\n" + body


def redact_sensitive(text: str) -> str:
    return DIGIT_RUN_RE.sub("[REDACTED]", text)


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers") or []
    out: dict[str, str] = {}
    for item in headers:
        name = str(item.get("name", "")).lower()
        value = str(item.get("value", ""))
        if name:
            out[name] = value
    return out


def _walk_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parts = payload.get("parts") or []
    if not parts:
        return [payload]
    collected: list[dict[str, Any]] = []
    for part in parts:
        collected.extend(_walk_parts(part))
    return collected


def _html_to_text(html: str) -> str:
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0
    return converter.handle(html)


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = WHITESPACE_RE.sub(" ", text)
    text = MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def _extract_bodies(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    plain: str | None = None
    html: str | None = None
    for part in _walk_parts(payload):
        mime = str(part.get("mimeType", "")).lower()
        body = part.get("body") or {}
        data = body.get("data")
        filename = part.get("filename") or ""
        if filename or not data:
            continue
        try:
            decoded = _b64url_decode(data).decode("utf-8", errors="replace")
        except Exception:
            continue
        if mime == "text/plain" and plain is None:
            plain = decoded
        elif mime == "text/html" and html is None:
            html = decoded
    # Top-level body without parts
    if plain is None and html is None:
        body = payload.get("body") or {}
        data = body.get("data")
        mime = str(payload.get("mimeType", "")).lower()
        if data:
            decoded = _b64url_decode(data).decode("utf-8", errors="replace")
            if mime == "text/html":
                html = decoded
            else:
                plain = decoded
    return plain, html


def _attachment_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for part in _walk_parts(payload):
        filename = part.get("filename") or ""
        if filename:
            names.append(str(filename))
    return names


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def normalize_message(raw: dict[str, Any], *, body_char_limit: int = 2000) -> NormalizedEmail:
    """Convert a Gmail messages.get payload into a NormalizedEmail."""
    payload = raw.get("payload") or {}
    headers = _header_map(payload)
    plain, html = _extract_bodies(payload)
    if plain:
        body = _clean_text(plain)
    elif html:
        body = _clean_text(_html_to_text(html))
    else:
        body = _clean_text(str(raw.get("snippet") or ""))

    # Cap stored body the same way we cap outbound payload.
    if len(body) > body_char_limit:
        body = body[:body_char_limit].rstrip()

    return NormalizedEmail(
        gmail_id=str(raw.get("id") or ""),
        thread_id=str(raw.get("threadId") or ""),
        sender=headers.get("from", ""),
        to=headers.get("to", ""),
        subject=headers.get("subject", ""),
        date=_parse_date(headers.get("date")),
        list_unsubscribe=headers.get("list-unsubscribe"),
        body_text=body,
        attachment_names=_attachment_names(payload),
        label_ids=list(raw.get("labelIds") or []),
        snippet=str(raw.get("snippet") or ""),
    )
