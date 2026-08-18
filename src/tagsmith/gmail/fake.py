"""In-memory Gmail gateway for offline tests."""

from __future__ import annotations

from typing import Any

from tagsmith.gmail.errors import GmailApiError
from tagsmith.gmail.parser import NormalizedEmail, normalize_message
from tagsmith.gmail.protocol import HistoryPage


class FakeGmail:
    def __init__(
        self,
        messages: list[dict[str, Any]] | None = None,
        labels: list[dict[str, Any]] | None = None,
    ) -> None:
        self.messages = {str(m["id"]): m for m in (messages or [])}
        self.labels = {
            str(label["name"]): dict(label)
            for label in (
                labels
                or [
                    {"id": "INBOX", "name": "INBOX", "type": "system"},
                    {"id": "UNREAD", "name": "UNREAD", "type": "system"},
                ]
            )
        }
        self._label_seq = 1000
        self.modify_calls: list[dict[str, Any]] = []
        self.history_id = "1000"
        # Map start_history_id -> list of message ids that changed after it.
        self.history_events: dict[str, list[str]] = {}
        # Ordered (history_entry_id, message_id) records for truncation tests.
        self.history_chain: list[tuple[str, str]] = []
        self.list_history_error: GmailApiError | None = None
        self.get_message_errors: dict[str, Exception] = {}
        self.watch_calls: list[dict[str, Any]] = []
        self.stop_watch_calls = 0

    def list_labels(self) -> list[dict[str, Any]]:
        return list(self.labels.values())

    def get_or_create_label(self, name: str) -> dict[str, Any]:
        if name in self.labels:
            return self.labels[name]
        self._label_seq += 1
        label = {"id": f"L{self._label_seq}", "name": name, "type": "user"}
        self.labels[name] = label
        return label

    def list_message_ids(self, *, query: str = "is:unread", limit: int = 50) -> list[str]:
        ids: list[str] = []
        for msg in self.messages.values():
            label_ids = set(msg.get("labelIds") or [])
            if "is:unread" in query and "UNREAD" not in label_ids:
                continue
            ids.append(str(msg["id"]))
            if len(ids) >= limit:
                break
        return ids

    def get_message(self, gmail_id: str, *, format: str = "full") -> dict[str, Any]:
        err = self.get_message_errors.get(gmail_id)
        if err is not None:
            raise err
        try:
            return self.messages[gmail_id]
        except KeyError as exc:
            raise KeyError(f"unknown message {gmail_id}") from exc

    def fetch_unread(self, *, limit: int = 50) -> list[NormalizedEmail]:
        return [
            normalize_message(self.get_message(i))
            for i in self.list_message_ids(query="is:unread", limit=limit)
        ]

    def modify_labels(
        self,
        gmail_id: str,
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        msg = self.messages[gmail_id]
        labels = set(msg.get("labelIds") or [])
        for lid in add_label_ids or []:
            labels.add(lid)
        for lid in remove_label_ids or []:
            labels.discard(lid)
        msg["labelIds"] = list(labels)
        call = {
            "gmail_id": gmail_id,
            "add": list(add_label_ids or []),
            "remove": list(remove_label_ids or []),
        }
        self.modify_calls.append(call)
        return msg

    def batch_modify_labels(
        self,
        gmail_ids: list[str],
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> None:
        for gmail_id in gmail_ids:
            self.modify_labels(
                gmail_id,
                add_label_ids=add_label_ids,
                remove_label_ids=remove_label_ids,
            )

    def get_profile_history_id(self) -> str:
        return self.history_id

    def list_history(
        self,
        *,
        start_history_id: str,
        max_results: int = 100,
    ) -> HistoryPage:
        if self.list_history_error is not None:
            raise self.list_history_error
        if self.history_chain:
            records = [
                (hid, mid)
                for hid, mid in self.history_chain
                if _history_after(hid, start_history_id)
            ]
            truncated = len(records) > max_results
            records = records[:max_results]
            ids: list[str] = []
            seen: set[str] = set()
            latest: str | None = None
            for hid, mid in records:
                latest = hid
                if mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
            return HistoryPage(ids, latest, truncated)
        events = list(self.history_events.get(start_history_id) or [])
        truncated = len(events) > max_results
        sliced = events[:max_results]
        if not sliced:
            return HistoryPage([], start_history_id, False)
        try:
            base = int(start_history_id)
        except ValueError:
            base = 0
        cursor = str(base + len(sliced))
        return HistoryPage(sliced, cursor, truncated)

    def watch_mailbox(
        self,
        *,
        topic_name: str,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        call = {"topicName": topic_name, "labelIds": label_ids or ["INBOX"]}
        self.watch_calls.append(call)
        return {
            "historyId": self.history_id,
            "expiration": "9999999999999",
            "resourceId": "fake-resource",
        }

    def stop_watch(self) -> None:
        self.stop_watch_calls += 1


def _history_after(entry_id: str, start_history_id: str) -> bool:
    try:
        return int(entry_id) > int(start_history_id)
    except ValueError:
        return entry_id > start_history_id
