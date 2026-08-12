# Phase 4 — Continuous operation & MCP

Status: **in progress on branch `feature/phase-4-5-ops-product`** (not merged until approved).

## Goal

Stop full unread scans as the only path. Keep a Gmail `historyId`, sync
incrementally, renew `users.watch` leases, schedule periodic ticks, and expose
the same service layer over MCP.

**Local / dogfood first.** Hosted Pub/Sub push to a public HTTPS endpoint is
**Phase 6 (SaaS)** — see [SAAS.md](SAAS.md).

## Pieces

| Piece | Command / module |
|-------|------------------|
| History cursor | `sync_state` table + `SyncService.ensure_history_cursor` |
| Incremental sync | `tagsmith sync --incremental` / `SyncService.sync_incremental` |
| Watch lease | `tagsmith watch start\|status\|stop` / `WatchOps` |
| Scheduler | `tagsmith schedule run --once` or `--loop` (polls history) |
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

Until Phase 6 wires a hosted push subscription, prefer:

```bash
uv run tagsmith schedule run --loop --interval 300
```

That incremental-polls `historyId` on an interval and can renew the watch lease
when `TAGSMITH_PUBSUB_TOPIC` is set.

## Success criteria

- [x] `historyId` persisted + incremental sync path
- [x] Watch start/renew/stop helpers
- [x] Scheduler tick (sync + renew)
- [x] MCP server wrapping service layer
- [ ] Live Pub/Sub push receiver in production deploy → **Phase 6**
