# Phase 4 — Continuous operation & MCP

Status: **in progress on branch `feature/phase-4-5-ops-product`** (not merged until approved).

## Goal

Stop full unread scans as the only path. Keep a Gmail `historyId`, sync
incrementally, renew `users.watch`, schedule periodic ticks, and expose the same
service layer over MCP.

## Pieces

| Piece | Command / module |
|-------|------------------|
| History cursor | `sync_state` table + `SyncService.ensure_history_cursor` |
| Incremental sync | `tagsmith sync --incremental` / `SyncService.sync_incremental` |
| Watch lease | `tagsmith watch start\|status\|stop` / `WatchOps` |
| Scheduler | `tagsmith schedule run --once` or `--loop` |
| MCP | `tagsmith mcp` (stdio FastMCP tools) |

## MCP tools

- `list_unread`
- `classify_message` (`apply` defaults false)
- `apply_label`
- `propose_category`
- `approve_proposal`
- `sync_incremental`

## Config

```bash
TAGSMITH_PUBSUB_TOPIC=projects/YOUR_PROJECT/topics/tagsmith-gmail
TAGSMITH_SCHEDULE_INTERVAL_SECONDS=300
TAGSMITH_WATCH_RENEW_HOURS=144
```

Pub/Sub setup (GCP): create a topic, grant `pubsub.publisher` to
`gmail-api-push@system.gserviceaccount.com`, point a push subscription at your
HTTPS endpoint (Phase 5 API can host the receiver later). Until Pub/Sub is wired,
`tagsmith schedule run --loop` incremental-polls history on an interval.

## Success criteria

- [x] `historyId` persisted + incremental sync path
- [x] Watch start/renew/stop helpers
- [x] Scheduler tick (sync + renew)
- [x] MCP server wrapping service layer
- [ ] Live Pub/Sub push receiver in production deploy
