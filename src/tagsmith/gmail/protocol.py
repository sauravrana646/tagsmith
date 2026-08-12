"""Thin Gmail interface so services can run against fixtures or the live API."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from tagsmith.gmail.parser import NormalizedEmail


@runtime_checkable
class GmailGateway(Protocol):
    def list_labels(self) -> list[dict[str, Any]]: ...

    def get_or_create_label(self, name: str) -> dict[str, Any]: ...

    def list_message_ids(self, *, query: str = "is:unread", limit: int = 50) -> list[str]: ...

    def get_message(self, gmail_id: str, *, format: str = "full") -> dict[str, Any]: ...

    def fetch_unread(self, *, limit: int = 50) -> list[NormalizedEmail]: ...

    def modify_labels(
        self,
        gmail_id: str,
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def batch_modify_labels(
        self,
        gmail_ids: list[str],
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> None: ...

    def get_profile_history_id(self) -> str: ...

    def list_history(
        self,
        *,
        start_history_id: str,
        max_results: int = 100,
    ) -> tuple[list[str], str | None]:
        """Return (changed_message_ids, latest_history_id)."""
        ...

    def watch_mailbox(
        self,
        *,
        topic_name: str,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Start users.watch; returns expiration / historyId / resource fields."""
        ...

    def stop_watch(self) -> None: ...
