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
from tagsmith.gmail.parser import NormalizedEmail, normalize_message
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


def _is_retryable(exc: BaseException) -> bool:
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
        return request.execute()

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
