"""Process-wide single-flight lock for mailbox sync."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class SyncInProgress(RuntimeError):
    """Raised when a non-blocking acquire fails because a sync is already running."""


_lock = threading.Lock()


def sync_is_running() -> bool:
    return _lock.locked()


@contextmanager
def sync_flight(*, blocking: bool = False) -> Iterator[None]:
    """Hold the process-wide sync lock.

    ``blocking=False`` raises ``SyncInProgress`` immediately if another flight
    is active (API 409). Background ticks use the same mode and skip the tick.
    """
    acquired = _lock.acquire(blocking=blocking)
    if not acquired:
        raise SyncInProgress("already_running")
    try:
        yield
    finally:
        _lock.release()
