"""Service layer — CLI / MCP / FastAPI call these functions."""

from tagsmith.services.classify_ops import ClassifyOps
from tagsmith.services.review_ops import ReviewOps
from tagsmith.services.sync import SyncService
from tagsmith.services.watch_ops import WatchOps

__all__ = ["ClassifyOps", "ReviewOps", "SyncService", "WatchOps"]
