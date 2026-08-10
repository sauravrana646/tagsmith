"""In-memory Gmail gateway for offline tests."""

from __future__ import annotations

from typing import Any

from tagsmith.gmail.parser import NormalizedEmail, normalize_message


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
