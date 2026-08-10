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
