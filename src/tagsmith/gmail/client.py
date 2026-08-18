"""Gmail API wrapper with retries and backoff."""

from __future__ import annotations

from typing import Any, cast

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from tagsmith.config import Settings
from tagsmith.gmail.auth import get_credentials
from tagsmith.gmail.errors import GmailApiError
from tagsmith.gmail.parser import NormalizedEmail, normalize_message
from tagsmith.gmail.protocol import HistoryPage
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, GmailApiError):
        return exc.status == 429 or exc.status >= 500
    if not isinstance(exc, HttpError):
        return False
    status = int(exc.resp.status) if exc.resp is not None else 0
    return status == 429 or status >= 500


def build_service(credentials: Credentials) -> Resource:
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


class GmailClient:
    def __init__(self, service: Resource, settings: Settings) -> None:
        self.service = service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings, *, interactive: bool = False) -> GmailClient:
        creds = get_credentials(settings, interactive=interactive)
        return cls(build_service(creds), settings)

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _execute(self, request: Any) -> Any:
        try:
            return request.execute()
        except HttpError as exc:
            status = int(exc.resp.status) if exc.resp is not None else 0
            raise GmailApiError(status, str(exc)) from exc

    def list_labels(self) -> list[dict[str, Any]]:
        result = cast(
            dict[str, Any],
            self._execute(self.service.users().labels().list(userId="me")),
        )
        return list(result.get("labels") or [])

    def get_or_create_label(self, name: str) -> dict[str, Any]:
        for label in self.list_labels():
            if label.get("name") == name:
                return label
        body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        created = cast(
            dict[str, Any],
            self._execute(self.service.users().labels().create(userId="me", body=body)),
        )
        log.info("gmail.label_created", name=name, label_id=created.get("id"))
        return created

    def list_message_ids(
        self,
        *,
        query: str = "is:unread",
        limit: int = 50,
    ) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        while len(ids) < limit:
            page_size = min(100, limit - len(ids))
            result = cast(
                dict[str, Any],
                self._execute(
                    self.service.users()
                    .messages()
                    .list(userId="me", q=query, maxResults=page_size, pageToken=page_token)
                ),
            )
            for item in result.get("messages") or []:
                ids.append(str(item["id"]))
                if len(ids) >= limit:
                    break
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return ids

    def get_message(self, gmail_id: str, *, format: str = "full") -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._execute(
                self.service.users().messages().get(userId="me", id=gmail_id, format=format)
            ),
        )

    def fetch_unread(self, *, limit: int = 50) -> list[NormalizedEmail]:
        ids = self.list_message_ids(query="is:unread", limit=limit)
        emails: list[NormalizedEmail] = []
        for gmail_id in ids:
            raw = self.get_message(gmail_id)
            emails.append(normalize_message(raw, body_char_limit=self.settings.body_char_limit))
        return emails

    def modify_labels(
        self,
        gmail_id: str,
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        body = {
            "addLabelIds": add_label_ids or [],
            "removeLabelIds": remove_label_ids or [],
        }
        return cast(
            dict[str, Any],
            self._execute(
                self.service.users().messages().modify(userId="me", id=gmail_id, body=body)
            ),
        )

    def batch_modify_labels(
        self,
        gmail_ids: list[str],
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> None:
        if not gmail_ids:
            return
        body = {
            "ids": gmail_ids,
            "addLabelIds": add_label_ids or [],
            "removeLabelIds": remove_label_ids or [],
        }
        self._execute(self.service.users().messages().batchModify(userId="me", body=body))

    def get_profile_history_id(self) -> str:
        profile = cast(
            dict[str, Any],
            self._execute(self.service.users().getProfile(userId="me")),
        )
        history_id = profile.get("historyId")
        if history_id is None:
            raise RuntimeError("Gmail profile missing historyId")
        return str(history_id)

    def list_history(
        self,
        *,
        start_history_id: str,
        max_results: int = 100,
    ) -> HistoryPage:
        """Page users.history.list and collect unique message ids that changed.

        The returned cursor is the last consumed history **entry** id. Mailbox-head
        ``historyId`` is never used when the page stream is truncated (C-2).
        """
        ids: list[str] = []
        seen: set[str] = set()
        page_token: str | None = None
        latest: str | None = None
        truncated = False
        mailbox_head: str | None = None
        while True:
            result = cast(
                dict[str, Any],
                self._execute(
                    self.service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=start_history_id,
                        maxResults=min(100, max_results),
                        pageToken=page_token,
                        historyTypes=[
                            "messageAdded",
                            "messageDeleted",
                            "labelAdded",
                            "labelRemoved",
                        ],
                    )
                ),
            )
            if result.get("historyId") is not None:
                mailbox_head = str(result["historyId"])
            for entry in result.get("history") or []:
                entry_ids: list[str] = []
                for key in ("messagesAdded", "messagesDeleted", "labelsAdded", "labelsRemoved"):
                    for item in entry.get(key) or []:
                        msg = item.get("message") or {}
                        mid = msg.get("id")
                        if mid:
                            entry_ids.append(str(mid))
                incoming = [mid for mid in entry_ids if mid not in seen]
                if incoming and len(ids) + len(incoming) > max_results and ids:
                    truncated = True
                    break
                entry_id = str(entry.get("id") or "") or None
                if entry_id:
                    latest = entry_id
                for mid in incoming:
                    seen.add(mid)
                    ids.append(mid)
                    if len(ids) >= max_results:
                        truncated = True
                        break
                if truncated:
                    break
            page_token = result.get("nextPageToken")
            if truncated:
                break
            if not page_token:
                if latest is None:
                    latest = mailbox_head
                break
            if len(ids) >= max_results:
                truncated = True
                break
        return HistoryPage(ids[:max_results], latest, truncated)

    def watch_mailbox(
        self,
        *,
        topic_name: str,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "topicName": topic_name,
            "labelIds": label_ids or ["INBOX"],
            "labelFilterBehavior": "include",
        }
        return cast(
            dict[str, Any],
            self._execute(self.service.users().watch(userId="me", body=body)),
        )

    def stop_watch(self) -> None:
        self._execute(self.service.users().stop(userId="me"))
