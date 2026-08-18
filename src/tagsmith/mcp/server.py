"""FastMCP server — thin adapters over SyncService / ReviewOps / ClassifyOps."""

from __future__ import annotations

from typing import Any

from tagsmith.config import Settings, get_settings
from tagsmith.db.session import get_session, init_db
from tagsmith.gmail.auth import AuthError
from tagsmith.gmail.client import GmailClient
from tagsmith.services.classify_ops import ClassifyOps
from tagsmith.services.review_ops import ReviewOps
from tagsmith.services.sync import SyncService
from tagsmith.telemetry import configure_logging, get_logger

log = get_logger(__name__)


def _build_mcp() -> Any:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("tagsmith")

    def _settings() -> Settings:
        settings = get_settings()
        configure_logging(settings.log_level)
        init_db(settings)
        return settings

    def _gmail(settings: Settings) -> GmailClient:
        try:
            return GmailClient.from_settings(settings, interactive=False)
        except AuthError as exc:
            raise RuntimeError(str(exc)) from exc

    @mcp.tool()
    async def list_unread(limit: int = 20) -> list[dict[str, Any]]:
        """List unread Gmail message ids/subjects (read-only)."""
        settings = _settings()
        gmail = _gmail(settings)
        ids = gmail.list_message_ids(query="is:unread", limit=limit)
        out: list[dict[str, Any]] = []
        for gmail_id in ids:
            raw = gmail.get_message(gmail_id, format="metadata")
            headers = {
                h["name"].lower(): h["value"]
                for h in (raw.get("payload") or {}).get("headers") or []
                if "name" in h and "value" in h
            }
            out.append(
                {
                    "gmail_id": gmail_id,
                    "subject": headers.get("subject", ""),
                    "from": headers.get("from", ""),
                    "snippet": raw.get("snippet", ""),
                }
            )
        return out

    @mcp.tool()
    async def classify_message(
        gmail_id: str,
        apply: bool = False,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Classify one message. apply=False is dry-run (default)."""
        settings = _settings()
        gmail = _gmail(settings)
        with get_session(settings) as session:
            ops = ClassifyOps(session, gmail, settings)
            view = await ops.classify_message(gmail_id, apply=apply, persist=persist)
            return view.as_dict()

    @mcp.tool()
    async def apply_label(gmail_id: str, label_key: str, apply: bool = False) -> dict[str, Any]:
        """File a held/needs-review message under an existing taxonomy key."""
        settings = _settings()
        gmail = _gmail(settings)
        with get_session(settings) as session:
            ops = ReviewOps(session, gmail, settings)
            try:
                ops.resolve_held_with_existing(gmail_id, label_key, apply=apply)
                return {
                    "gmail_id": gmail_id,
                    "label_key": label_key,
                    "applied": apply,
                    "path": "held",
                }
            except Exception:
                ops.change_label(gmail_id, label_key, apply=apply)
                return {
                    "gmail_id": gmail_id,
                    "label_key": label_key,
                    "applied": apply,
                    "path": "needs_review",
                }

    @mcp.tool()
    async def propose_category(
        gmail_id: str,
        suggested_key: str,
        description: str,
        why_no_existing_fit: str = "",
        apply: bool = False,
    ) -> dict[str, Any]:
        """Create/activate a new category for a held message."""
        settings = _settings()
        gmail = _gmail(settings)
        with get_session(settings) as session:
            ops = ReviewOps(session, gmail, settings)
            ops.resolve_held_with_new(
                gmail_id,
                suggested_key=suggested_key,
                description=description,
                why=why_no_existing_fit or description,
                apply=apply,
            )
            return {
                "gmail_id": gmail_id,
                "suggested_key": suggested_key,
                "applied": apply,
            }

    @mcp.tool()
    async def approve_proposal(proposal_id: int, apply: bool = False) -> dict[str, Any]:
        """Approve a pending proposal and reclassify held mail."""
        settings = _settings()
        gmail = _gmail(settings)
        with get_session(settings) as session:
            ops = ReviewOps(session, gmail, settings)
            result = await ops.approve_proposal(proposal_id, apply=apply)
            return {
                "proposal_id": proposal_id,
                "applied": apply,
                "reclassify_counts": result.counts.as_dict(),
            }

    @mcp.tool()
    async def sync_incremental(limit: int = 50, apply: bool = False) -> dict[str, Any]:
        """Run Phase 4 incremental sync from the stored historyId."""
        settings = _settings()
        gmail = _gmail(settings)
        with get_session(settings) as session:
            service = SyncService(session, gmail, settings)
            result = await service.sync_incremental(limit=limit, apply=apply)
            return {
                "run_id": result.run_id,
                "dry_run": result.dry_run,
                "counts": result.counts.as_dict(),
            }

    return mcp


def main() -> None:
    """Entry point: `tagsmith mcp` or `uv run python -m tagsmith.mcp.server`."""
    mcp = _build_mcp()
    log.info("mcp.starting")
    mcp.run()


if __name__ == "__main__":
    main()
