"""Gmail users.watch lease management (Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from tagsmith.config import Settings
from tagsmith.db.models import SyncState, utcnow
from tagsmith.gmail.protocol import GmailGateway
from tagsmith.telemetry import get_logger

log = get_logger(__name__)


@dataclass
class WatchStatus:
    history_id: str | None
    watch_expiration_ms: int | None
    watch_resource_id: str | None
    pubsub_topic: str | None
    last_watch_renewed_at: str | None

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "history_id": self.history_id,
            "watch_expiration_ms": self.watch_expiration_ms,
            "watch_resource_id": self.watch_resource_id,
            "pubsub_topic": self.pubsub_topic,
            "last_watch_renewed_at": self.last_watch_renewed_at,
        }


class WatchOps:
    def __init__(
        self,
        session: Session,
        gmail: GmailGateway,
        settings: Settings,
    ) -> None:
        self.session = session
        self.gmail = gmail
        self.settings = settings

    def _state(self) -> SyncState:
        state = self.session.get(SyncState, 1)
        if state is None:
            state = SyncState(id=1)
            self.session.add(state)
            self.session.commit()
            self.session.refresh(state)
        return state

    def status(self) -> WatchStatus:
        state = self._state()
        renewed = state.last_watch_renewed_at.isoformat() if state.last_watch_renewed_at else None
        return WatchStatus(
            history_id=state.history_id,
            watch_expiration_ms=state.watch_expiration_ms,
            watch_resource_id=state.watch_resource_id,
            pubsub_topic=state.pubsub_topic,
            last_watch_renewed_at=renewed,
        )

    def start_or_renew(self, *, topic_name: str | None = None) -> WatchStatus:
        topic = topic_name or self.settings.pubsub_topic
        if not topic:
            raise ValueError(
                "Pub/Sub topic required. Set TAGSMITH_PUBSUB_TOPIC "
                "(projects/.../topics/...) or pass --topic."
            )
        result = self.gmail.watch_mailbox(topic_name=topic, label_ids=["INBOX"])
        state = self._state()
        state.pubsub_topic = topic
        state.watch_resource_id = str(result.get("resourceId") or "") or None
        exp = result.get("expiration")
        state.watch_expiration_ms = int(exp) if exp is not None else None
        if result.get("historyId") is not None:
            state.history_id = str(result["historyId"])
        state.last_watch_renewed_at = utcnow()
        state.updated_at = utcnow()
        self.session.commit()
        log.info(
            "watch.renewed",
            topic=topic,
            expiration_ms=state.watch_expiration_ms,
            history_id=state.history_id,
        )
        return self.status()

    def stop(self) -> WatchStatus:
        self.gmail.stop_watch()
        state = self._state()
        state.watch_expiration_ms = None
        state.watch_resource_id = None
        state.updated_at = utcnow()
        self.session.commit()
        log.info("watch.stopped")
        return self.status()
