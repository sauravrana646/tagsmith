"""Terminal-friendly email formatting for interactive review."""

from __future__ import annotations

import re
from typing import Any

# Zero-width / soft-hyphen / BOM junk common in marketing HTML→text.
_ZW_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
# Markdown / HTML-ish links: keep visible label when short, else drop URL.
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def _shorten_url(url: str, max_len: int = 48) -> str:
    if len(url) <= max_len:
        return url
    return url[: max_len - 1] + "…"


def _replace_md_link(match: re.Match[str]) -> str:
    label = (match.group(1) or "").strip()
    url = match.group(2)
    if label and label not in {"", " "}:
        return f"{label} ({_shorten_url(url, 40)})"
    return f"<{_shorten_url(url)}>"


def clean_review_text(text: str, *, max_chars: int = 500) -> str:
    """Strip tracking junk and cap length for readable TUI panels."""
    text = _ZW_RE.sub("", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MD_LINK_RE.sub(_replace_md_link, text)
    text = _BARE_URL_RE.sub(lambda m: _shorten_url(m.group(0)), text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n…[truncated]"
    return text


def format_message_for_review(payload: dict[str, Any], *, body_chars: int = 500) -> str:
    sender = str(payload.get("sender") or "")
    subject = str(payload.get("subject") or "")
    date = str(payload.get("date") or "")
    list_unsub = payload.get("list_unsubscribe")
    attachments = payload.get("attachment_names") or []
    body = clean_review_text(str(payload.get("body_text") or ""), max_chars=body_chars)

    lines = [
        f"From: {sender}",
        f"Subject: {subject}",
        f"Date: {date}",
    ]
    if list_unsub:
        lines.append("List-Unsubscribe: yes")
    if attachments:
        names = ", ".join(str(a) for a in attachments[:5])
        lines.append(f"Attachments: {names}")
    lines.append("")
    lines.append(body or "(empty body)")
    return "\n".join(lines)
