"""In-process per-tenant rate limit for expensive sync calls."""

from __future__ import annotations

import time
from collections import defaultdict

_hits: dict[int, list[float]] = defaultdict(list)


def check_sync_rate(tenant_id: int, *, limit_per_day: int) -> bool:
    """Return True if the call is allowed. Mutates the hit log."""
    now = time.time()
    window = now - 86400
    recent = [t for t in _hits[tenant_id] if t >= window]
    if len(recent) >= limit_per_day:
        _hits[tenant_id] = recent
        return False
    recent.append(now)
    _hits[tenant_id] = recent
    return True


def reset_rate_limits() -> None:
    _hits.clear()
