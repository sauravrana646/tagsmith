"""Gmail API errors with an HTTP status for callers (stale history, auth, 5xx)."""

from __future__ import annotations


class GmailApiError(Exception):
    """Normalized Gmail HTTP failure. ``status`` is the response code."""

    def __init__(self, status: int, message: str = "") -> None:
        self.status = status
        super().__init__(message or f"Gmail HTTP {status}")
