# Fix plan — review-opus findings

Implementation playbook for [review-opus.md](review-opus.md). Finding IDs
(`C-1`, `B-4`, …) are stable anchors for PRs and commit messages.

**Source.** Static review of `feature/phase-4-5-ops-product` (originally
`ec6b614`). This document does not implement the fixes; it specifies what to
change, where, and how to prove it.

**Immediate workaround (until Stage 1 lands).** Set
`TAGSMITH_ENABLE_BACKGROUND_SYNC=false`. The API background loop is on by
default and runs with `background_sync_apply=false`, which is how **C-1**
silently marks mail as done without writing Gmail labels.

**Chosen approaches (locked).**

- **C-1:** do not write terminal `MessageState` on dry-run. Leave rows
  `PENDING`. Do not add a parallel `applied` flag.
- **B-1:** overlapping API sync returns **HTTP 409** (`already_running`). Do
  not wait silently.

---

## Success criteria

| Stage | Done when |
|---|---|
| **1** | Dry-run no longer blocks a later apply. Incremental sync never skips unprocessed history. Background + dashboard sync cannot race. Review confirm/approve remove `AI/needs-review`. Approving one proposal does not re-LLM every held message. RAG catch-up indexes only Gmail-committed applies. Background sync may be re-enabled. |
| **2** | API stays responsive during a long sync. Crash mid-apply is recoverable. Stale-cursor fallback is not triggered by 503/auth. SQLite concurrent writes do not lock. Full sync survives a deleted message. `/docs` and `/auth/debug` are off unless explicitly enabled. |
| **3** | Unsigned cookies, unauthenticated `/api/*`, shared mailbox state, and desktop-token-for-every-tenant are gone. Product is not opened to customers before this stage. |
| **4** | Actions are SHA-pinned, gitleaks scans docs, web has a smoke test + JS audit, RAG and review-list queries are not full-table / N+1. |

---

## Stage 1 — labeling correctness

Must ship before dogfooding with background sync on. Touches
`services/sync.py`, `gmail/client.py`, `services/watch_ops.py`,
`services/review_ops.py`, `rag/index.py`, plus a process-wide lock used by
the API and scheduler.

### C-1 — Dry-run must not mark messages terminal

**Files.** [`src/tagsmith/services/sync.py`](../src/tagsmith/services/sync.py)
(`process_email`); tests in
[`tests/test_sync_and_review.py`](../tests/test_sync_and_review.py).

**Change.** In `process_email`, gate terminal state writes on `apply`:

- `apply=False`: leave `message.state` as `PENDING`. Still persist a
  `ClassificationRecord` for audit (`applied_at=None`). Do not set
  `LABELED` / `HELD` / `NEEDS_REVIEW`. Do not enqueue proposals that would
  later be treated as resolved work (or enqueue with a non-terminal message
  so a later apply can still process the mail).
- `apply=True`: keep current terminal transitions.
- Skip-prior (`sync.py` ~227–244) stays based on terminal states. After this
  change, dry-run rows are not terminal, so a later apply run classifies and
  writes Gmail.

Do **not** add a second `applied` column. Terminal skip already means
“Gmail holds the outcome”; dry-run must simply not claim that.

**Acceptance.**

1. `sync(apply=False)` leaves `Message.state == PENDING`, `applied_label_id
   is None`, Gmail `modify_calls` empty.
2. A subsequent `sync(apply=True)` on the same message applies the label
   (`skipped_prior == 0`, `applied >= 1`).
3. `sync(apply=True)` twice still increments `skipped_prior` on the second
   run (`test_sync_apply_and_skip_prior` remains valid).

**Tests.**

- Update `test_sync_dry_run_rules_path`: assert `PENDING`, not `LABELED`;
  catch-up indexes `0` (also **B-6**).
- Add `test_dry_run_then_apply_does_not_skip_prior`.

---

### C-2 — Advance history cursor only past processed records

**Files.** [`src/tagsmith/gmail/client.py`](../src/tagsmith/gmail/client.py)
(`list_history`);
[`src/tagsmith/services/sync.py`](../src/tagsmith/services/sync.py)
(`sync_incremental`).

**Change.**

1. In `list_history`, stop overwriting `latest` with the response’s
   mailbox-head `historyId` (`client.py` ~200–201). Keep `latest` as the
   **last history entry `id` actually consumed**.
2. Return a third value `truncated: bool` (or a small named tuple): true
   when the loop stopped because `len(ids) >= max_results` while a
   `nextPageToken` still existed, or when `ids` was sliced to
   `max_results`.
3. In `sync_incremental`, commit `state.history_id` to that last consumed
   entry id. **Never** fall back to `get_profile_history_id()` after a
   truncated page (`sync.py` ~571). Profile-head is only valid when the
   history stream is exhausted (`truncated is False` and no
   `nextPageToken`) and there were zero history entries (empty mailbox
   bootstrap).
4. If truncated, log `sync.history_truncated` with start cursor, new
   cursor, and id count.

Gmail history ids are per-record; the next `users.history.list` with
`startHistoryId=<last consumed>` returns subsequent records, including
those skipped by `max_results`.

**Acceptance.**

- 150 history changes with `limit=100`: first incremental run processes 100
  and stores a cursor **inside** the 150, not mailbox-head. Second run
  returns the remaining 50.
- Exhausted history (no `nextPageToken`) may store the last entry id; the
  next incremental call is empty, not a silent gap.

**Tests.**

- Add `test_list_history_truncated_does_not_jump_to_mailbox_head` (fake
  Gmail with paged history).
- Add `test_sync_incremental_second_page_after_limit`.
- Extend [`tests/test_phase4_ops.py`](../tests/test_phase4_ops.py)
  `test_sync_incremental_processes_history_ids` so a truncated fixture does
  not equal `fake_gmail.history_id` (mailbox head).

---

### C-2 (watch) — Renew must not move the sync cursor

**File.** [`src/tagsmith/services/watch_ops.py`](../src/tagsmith/services/watch_ops.py)
(`start_or_renew`).

**Change.** Persist lease fields only: `pubsub_topic`, `watch_resource_id`,
`watch_expiration_ms`, `last_watch_renewed_at`. Set `state.history_id` from
the watch response **only if** `state.history_id` is currently `None`
(bootstrap). Never overwrite a cursor that sync has already advanced — or
failed to finish.

**Acceptance.** After a truncated incremental sync, `start_or_renew` leaves
`history_id` unchanged. First-time watch with empty cursor still seeds it.

**Tests.**

- Add `test_watch_renew_does_not_overwrite_existing_history_id`.
- Add `test_watch_bootstrap_sets_history_id_when_unset`.

---

### B-1 — Single-flight lock; overlapping API sync returns 409

**Files.** New small helper (e.g. [`src/tagsmith/services/sync_lock.py`](../src/tagsmith/services/sync_lock.py));
wire into [`src/tagsmith/background.py`](../src/tagsmith/background.py),
[`src/tagsmith/scheduler.py`](../src/tagsmith/scheduler.py),
[`src/tagsmith/api/routes/sync.py`](../src/tagsmith/api/routes/sync.py)
(`run_sync`).

**Change.** Process-wide `asyncio.Lock` (module singleton) acquired around
`sync` / `sync_incremental` / `run_schedule_tick`.

- Background / scheduler: if the lock is held, skip the tick and log
  `sync.skipped_lock`.
- `POST /api/sync/run`: `acquire` with timeout 0; on failure return
  **409** `{"detail": "already_running"}`. Do not queue behind the
  background loop.

CLI `tagsmith sync` in another process is out of scope for the in-process
lock (Stage 2 SQLite WAL covers disk races).

**Acceptance.** Concurrent `POST /api/sync/run` while a tick is in flight
returns 409 and does not double-classify. A second request after the lock
releases succeeds.

**Tests.**

- Add `test_run_sync_returns_409_when_lock_held` in
  [`tests/test_phase5_api.py`](../tests/test_phase5_api.py).
- Add `test_background_tick_skips_when_lock_held`.

---

### B-4 — Remove `AI/needs-review` on confirm / change / approve

**File.** [`src/tagsmith/services/review_ops.py`](../src/tagsmith/services/review_ops.py)
(`confirm_label`, `change_label`, `approve_proposal`).

**Change.** Mirror `assign_existing_label` / `resolve_held_with_existing`:
always include `_needs_review_label_id()` in `remove_label_ids` when
`apply=True`.

- `confirm_label`: today it only *adds* the category label when
  `applied_label_id is None` and never removes needs-review. Even when the
  category label is already on the message, still `modify_labels` with
  needs-review removal.
- `change_label`: delete the comment “keep needs-review removal optional”
  and append the needs-review id to `remove_ids`.
- `approve_proposal`: add the new category label **and** remove
  needs-review (holds also get that Gmail label in `process_email`).

**Acceptance.** After confirm / change / approve with `apply=True`, Gmail
modify calls include the needs-review label id in `remove_label_ids`.

**Tests.**

- Add `test_confirm_label_removes_needs_review`.
- Add `test_change_label_removes_needs_review`.
- Add `test_approve_proposal_removes_needs_review`.

---

### B-5 — Scope `reclassify_held` to the approved category

**Files.** [`src/tagsmith/services/review_ops.py`](../src/tagsmith/services/review_ops.py)
(`approve_proposal` ~296–298);
[`src/tagsmith/services/sync.py`](../src/tagsmith/services/sync.py)
(`reclassify_held`).

**Change.** `reclassify_held(*, apply, label_key: str)` selects `HELD`
messages whose pending `Proposal.suggested_key` (or latest
`ClassificationRecord.proposed_key`) matches `label_key`. Exclude the
already-labeled approved message.

`approve_proposal` passes the activated key. Unrelated held mail stays
`HELD` until its own proposal is decided.

**Acceptance.** Two held messages for different proposed keys; approving
one reclassifies only messages waiting on that key. The other remains
`HELD` with no extra Gmail writes.

**Tests.**

- Add `test_approve_proposal_reclassifies_only_matching_held`.

---

### B-6 — RAG catch-up indexes only committed applies

**Files.** [`src/tagsmith/rag/index.py`](../src/tagsmith/rag/index.py)
(`catchup_from_db`, `reindex_from_db`);
[`tests/test_sync_and_review.py`](../tests/test_sync_and_review.py)
(`test_sync_dry_run_rules_path`);
[`tests/test_rag.py`](../tests/test_rag.py).

**Change.** Require a committed apply before upsert: `message.state ==
LABELED` **and** `message.applied_label_id is not None`. After **C-1**,
dry-run rows stay `PENDING` and drop out naturally; the `applied_label_id`
gate still blocks accidental `LABELED` without a Gmail write.

Inline indexing in `process_email` already requires `apply` — leave that.

**Acceptance.** Dry-run catch-up indexes 0. Apply then catch-up indexes 1.
Reindex does not restore dry-run-only rows.

**Tests.**

- Flip `test_sync_dry_run_rules_path`: `caught.indexed == 0`.
- Add `test_catchup_skips_labeled_without_applied_label_id`.
- Keep apply-path RAG tests green
  (`test_user_removed_label_becomes_negative` still sees count 1 after
  apply).

---

### Stage 1 ship gate

Re-enable `TAGSMITH_ENABLE_BACKGROUND_SYNC` (default `true`) only after
the Stage 1 tests above are green. Until then keep the env workaround.

---

## Stage 2 — safe to leave running

### B-2 — Move blocking Gmail I/O off the event loop

**Files.** [`src/tagsmith/gmail/client.py`](../src/tagsmith/gmail/client.py)
(`_execute`); callers in `SyncService` / `ReviewOps` used from `async def`
routes.

**Change.** Wrap `request.execute()` (and other sync `httpx` /
`googleapiclient` calls) with `asyncio.to_thread` from async service
methods, **or** make FastAPI sync routes (`def` not `async def`) so
Starlette uses the threadpool. Prefer `to_thread` at the Gmail boundary so
CLI async sync benefits too.

Do not hold the Stage 1 lock across an extra unbounded wait without a
timeout log.

**Acceptance.** A 30s Gmail list does not stall `GET /health` or
`GET /api/status` on the same event loop.

**Tests.** `test_health_responds_during_in_flight_sync` (inject a slow
fake `_execute`).

---

### B-3 — Recoverable Gmail vs DB ordering

**File.** [`src/tagsmith/services/sync.py`](../src/tagsmith/services/sync.py)
(`process_email`); same pattern in `review_ops.py` apply paths.

**Change.** Commit DB **intent** first: keep or set `PENDING` with the
planned `applied_label_key`, `applied_at=None`. Then Gmail
`modify_labels`. Then set terminal state + `applied_label_id` +
`applied_at` and commit.

On retry, if Gmail already has the `AI/*` label, treat modify as
idempotent success (do not re-LLM). If Gmail succeeded and DB commit
failed, the next run sees `PENDING` + existing Gmail label and adopts
state without a second classification.

**Acceptance.** Killing the process between Gmail write and DB commit does
not skip the message forever or double-charge the LLM.

**Tests.** `test_process_email_retries_after_commit_failure_does_not_reclassify`
(fake Gmail records modify; inject commit failure once).

---

### B-7 — Narrow stale-cursor exception handling

**File.** [`src/tagsmith/services/sync.py`](../src/tagsmith/services/sync.py)
(`sync_incremental` ~540–552).

**Change.** Fall back to full unread sync only on Gmail **404** (historyId
too old). Re-raise 401/403. Retry or fail the run on 5xx / network errors.
Do not `except Exception`.

**Acceptance.** A mocked 503 does not call `sync()` full fallback. A
mocked 404 does.

**Tests.** `test_incremental_404_falls_back_to_full`;
`test_incremental_503_does_not_fallback`.

---

### B-8 — SQLite WAL and busy timeout

**File.** [`src/tagsmith/db/session.py`](../src/tagsmith/db/session.py)
(`get_engine`).

**Change.** For SQLite URLs, set `connect_args` to include
`timeout=30` (or `PRAGMA busy_timeout=30000`) and execute
`PRAGMA journal_mode=WAL` plus `PRAGMA synchronous=NORMAL` on connect
(SQLAlchemy `event.listens_for(engine, "connect")`).

**Acceptance.** Two concurrent sessions can write without immediate
`database is locked`.

**Tests.** `test_sqlite_wal_pragma_enabled` (query `PRAGMA journal_mode`).

---

### B-9 — Per-message error tolerance on full sync

**File.** [`src/tagsmith/services/sync.py`](../src/tagsmith/services/sync.py)
(`sync` ~490–492). Mirror the incremental loop’s
`sync.history_message_missing` continue. Always `_finalize_run` in
`finally` so `Run` is not left open.

**Acceptance.** One `get_message` 404 does not abort the run; remaining
messages process; `Run.finished_at` is set.

**Tests.** `test_full_sync_skips_missing_message_and_finalizes_run`.

---

### Docs and debug endpoints

**Files.** [`src/tagsmith/api/app.py`](../src/tagsmith/api/app.py)
(`create_app`); [`src/tagsmith/api/routes/oauth.py`](../src/tagsmith/api/routes/oauth.py)
(`/auth/debug`); [`src/tagsmith/config.py`](../src/tagsmith/config.py).

**Change.**

- `FastAPI(docs_url=..., redoc_url=..., openapi_url=...)` only when
  `TAGSMITH_ENABLE_API_DOCS=true` (default **false**).
- `/auth/debug` returns 404 unless `TAGSMITH_ENABLE_AUTH_DEBUG=true`.
- Escape `web_app_url` in the HTML fallback (`html.escape`); do not
  interpolate untrusted settings into markup (full allowlist is Stage 3).

**Tests.** `test_docs_disabled_by_default`;
`test_auth_debug_disabled_by_default`.

---

## Stage 3 — SaaS auth and tenancy

Largest change. **Do not open the product to anyone before this
completes.** Hosted SaaS is the customer product
([PHASE6.md](PHASE6.md)); the CLI remains operator dogfood.

### C-3 — Authenticate `/api/*`

**Files.** New `require_session` in [`src/tagsmith/api/deps.py`](../src/tagsmith/api/deps.py);
apply on routers in `review.py`, `sync.py`, `status.py`, `taxonomy.py`.
Keep `GET /health` public. Keep `GET /api/billing/plans` public. Protect
webhooks with provider signatures only (no session).

**Change.** FastAPI `Depends(require_session)` on all sensitive reads and
every mutation. Unauthenticated → 401.

**Tests.** `test_api_sync_run_unauthorized`; `test_api_review_list_unauthorized`;
`test_health_still_public`.

### Signed session cookie

**Files.** [`src/tagsmith/api/routes/oauth.py`](../src/tagsmith/api/routes/oauth.py)
(`_set_session_cookie`, `_tenant_from_request`);
`session_signing_key` already in [`src/tagsmith/config.py`](../src/tagsmith/config.py).

**Change.** Sign `tagsmith_tenant` with `itsdangerous.URLSafeTimedSerializer`
(or equivalent HMAC) using `session_signing_key`. Reject missing/invalid
signatures. Require the key in non-local environments.

**Tests.** `test_unsigned_tenant_cookie_rejected`;
`test_signed_session_cookie_authenticates`.

### Validate OAuth `state`

**File.** `oauth.py` login + callback.

**Change.** `/auth/callback` requires `request.cookies["oauth_state"] ==
state` (constant-time compare), then deletes the cookie. Mismatch → 400.

**Tests.** `test_oauth_callback_rejects_mismatched_state`;
`test_oauth_callback_accepts_matching_state`.

### CORS: explicit origins only

**File.** [`src/tagsmith/api/app.py`](../src/tagsmith/api/app.py).

**Change.** Remove `allow_origin_regex`. Allow only `web_app_url` and
`api_public_base_url` (plus the existing explicit `127.0.0.1:3000` /
`:3001` entries for local dashboard ports). Never combine a wildcard
localhost regex with `allow_credentials=True`.

**Tests.** `test_cors_localhost_random_port_not_allowed`.

### Tenant isolation

**Files.** [`src/tagsmith/db/models.py`](../src/tagsmith/db/models.py),
[`src/tagsmith/rag/store.py`](../src/tagsmith/rag/store.py), every query
on Message / ClassificationRecord / Proposal / Run / SyncState /
RagExample / Category as needed.

**Change.** Add `tenant_id` FK. Make `SyncState` per-tenant (drop hardcoded
`id=1`). Scope `get_sync_state`, review lists, RAG store, and sync. SQLite
column migration in `db/session.py` `_SQLITE_COLUMN_MIGRATIONS` (existing
local DBs). Operator dogfood uses a single default tenant created at
`init_db`.

**Tests.** `test_tenant_a_cannot_read_tenant_b_messages`;
`test_sync_state_is_per_tenant`.

### Per-tenant Gmail credentials

**Files.** [`src/tagsmith/api/deps.py`](../src/tagsmith/api/deps.py)
(`gmail_dep`, `try_gmail_from_request`); decrypt helper already in
`api/auth/web_oauth.py`.

**Change.** Load tenant from signed session → `decrypt_refresh_token` →
attach `Credentials` on `request.state` → `gmail_dep` prefers that over
desktop `token.json`. Desktop fallback only when no tenant session
(local single-user).

**Tests.** `test_gmail_dep_uses_tenant_refresh_token` (mocked decrypt +
client).

### Cookies, CSRF, redirects, KDF, rate limits, billing keying

| Item | Change |
|---|---|
| `Secure` cookie | Set when request is HTTPS or `TAGSMITH_COOKIE_SECURE=true`. |
| CSRF | Double-submit or SameSite=Lax + custom header for cookie-auth POSTs from the dashboard. |
| Redirect allowlist | Parse `web_app_url`; only redirect to that origin. Escape HTML interpolations. |
| KDF | Replace single SHA-256 in [`src/tagsmith/security/crypto.py`](../src/tagsmith/security/crypto.py) with HKDF or scrypt; version ciphertext so existing tokens can be re-encrypted. Plan KMS in Phase 6, not here. |
| Rate limits | Per-tenant cap on `POST /api/sync/run` (honor plan `sync_per_day` when present; default conservative). |
| Watch renew | Auth required (**C-3**); ignore caller-supplied topic unless it matches the tenant’s configured `pubsub_topic`. |
| Stripe webhook | Key upgrades on Stripe customer id, not `customer_email`; store processed `event.id` for idempotency. **Do not implement PayPal here** (Phase 6). |

**Tests.** Redirect allowlist; CSRF missing-header 403; watch renew rejects
foreign topic; webhook duplicate event is no-op.

---

## Stage 4 — quality and supply chain

### Pin GitHub Actions to commit SHAs

**File.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

Replace moving tags (`actions/checkout@v4`, `astral-sh/setup-uv@v5`,
`actions/setup-node@v4`, `actions/upload-artifact@v4`,
`actions/github-script@v7`, `gitleaks/gitleaks-action@v2`) with full
commit SHAs and a trailing `# vN` comment. Resolve SHAs at implementation
time from GitHub tag refs (do not guess).

### Narrow gitleaks docs allowlist

**File.** [`.gitleaks.toml`](../.gitleaks.toml).

Remove `^docs/.*`. Keep `.env.example` and `README.md`. If a docs file
must contain a fake secret, allowlist that **file** plus a description,
not the whole tree.

### JS scanning and web smoke

**File.** CI `lint-test` / web job in `ci.yml`; [`web/`](../web/).

Add `npm audit` (or `pnpm audit`) in the existing Node job. Add a smoke
test: `tsc` already runs; add a Playwright or HTTP test that the dashboard
builds and `/` renders without crashing. No full e2e Gmail suite here.

### B-10 — RAG load / re-embed

**Files.** [`src/tagsmith/rag/store.py`](../src/tagsmith/rag/store.py),
[`src/tagsmith/rag/retriever.py`](../src/tagsmith/rag/retriever.py).

Cache seed-category embeddings for the process lifetime (invalidate on
taxonomy change). Do not `SELECT` every `RagExample` and re-embed seeds on
each `process_email`. Retrieve top-k via existing vector path without a
full Python-side scan if already supported; otherwise add a simple
in-memory cache keyed by store fingerprint.

**Tests.** `test_retriever_does_not_reembed_seeds_every_call` (counter on
fake embedder).

### B-12 — Review list N+1

**File.** [`src/tagsmith/review/queue.py`](../src/tagsmith/review/queue.py)
(`list_needs_review`, `list_held`).

Load messages then fetch classifications in one `IN` query (or join),
pick latest per `gmail_id` in Python.

**Tests.** `test_list_needs_review_uses_constant_queries` (SQLAlchemy
query counter) or a fixture of N messages asserting one classification
query.

### B-11 — Atomic proposal dedupe

**Files.** [`src/tagsmith/review/queue.py`](../src/tagsmith/review/queue.py),
`reject_and_propose` in `review_ops.py`.

Unique constraint on `dedupe_key` (and `tenant_id` once Stage 3 exists).
`INSERT OR IGNORE` / catch integrity error instead of filter + `.one()`.
Scope lookup by `gmail_id` so another message’s proposal cannot attach.

**Tests.** `test_concurrent_enqueue_same_dedupe_key_does_not_raise`.

### B-13 — `SKIPPED` and `messagesDeleted`

**Files.** [`src/tagsmith/db/models.py`](../src/tagsmith/db/models.py),
[`src/tagsmith/gmail/client.py`](../src/tagsmith/gmail/client.py)
`list_history`.

Either assign `MessageState.SKIPPED` on a defined path (e.g. classified
but explicitly ignored) **or** drop the unused enum member. Add
`messageDeleted` to `historyTypes` if deleted mail should update local
state; otherwise stop reading `messagesDeleted` in the loop.

**Tests.** Match the chosen behavior (assignment site or removed dead
code).

---

## Test matrix

| ID | New / updated test | File |
|---|---|---|
| C-1 | `test_sync_dry_run_rules_path` (assert `PENDING`) | `tests/test_sync_and_review.py` |
| C-1 | `test_dry_run_then_apply_does_not_skip_prior` | `tests/test_sync_and_review.py` |
| C-2 | `test_list_history_truncated_does_not_jump_to_mailbox_head` | `tests/test_phase4_ops.py` |
| C-2 | `test_sync_incremental_second_page_after_limit` | `tests/test_phase4_ops.py` |
| C-2 watch | `test_watch_renew_does_not_overwrite_existing_history_id` | `tests/test_phase4_ops.py` |
| C-2 watch | `test_watch_bootstrap_sets_history_id_when_unset` | `tests/test_phase4_ops.py` |
| B-1 | `test_run_sync_returns_409_when_lock_held` | `tests/test_phase5_api.py` |
| B-1 | `test_background_tick_skips_when_lock_held` | `tests/test_phase5_api.py` |
| B-4 | `test_confirm_label_removes_needs_review` | `tests/test_sync_and_review.py` |
| B-4 | `test_change_label_removes_needs_review` | `tests/test_sync_and_review.py` |
| B-4 | `test_approve_proposal_removes_needs_review` | `tests/test_sync_and_review.py` |
| B-5 | `test_approve_proposal_reclassifies_only_matching_held` | `tests/test_sync_and_review.py` |
| B-6 | flip catch-up assertion in `test_sync_dry_run_rules_path` | `tests/test_sync_and_review.py` |
| B-6 | `test_catchup_skips_labeled_without_applied_label_id` | `tests/test_rag.py` |
| B-2 | `test_health_responds_during_in_flight_sync` | `tests/test_phase5_api.py` |
| B-3 | `test_process_email_retries_after_commit_failure_does_not_reclassify` | `tests/test_sync_and_review.py` |
| B-7 | `test_incremental_404_falls_back_to_full` / `_503_does_not_fallback` | `tests/test_phase4_ops.py` |
| B-8 | `test_sqlite_wal_pragma_enabled` | `tests/test_phase4_ops.py` |
| B-9 | `test_full_sync_skips_missing_message_and_finalizes_run` | `tests/test_sync_and_review.py` |
| Stage 2 docs | `test_docs_disabled_by_default` / `test_auth_debug_disabled_by_default` | `tests/test_phase5_api.py` |
| C-3 | `test_api_sync_run_unauthorized` | `tests/test_phase5_api.py` |
| Stage 3 | signed cookie, OAuth state, CORS, tenant isolation, gmail_dep | `tests/test_phase5_api.py` (new module if large) |
| B-10 | `test_retriever_does_not_reembed_seeds_every_call` | `tests/test_rag.py` |
| B-11 | `test_concurrent_enqueue_same_dedupe_key_does_not_raise` | `tests/test_sync_and_review.py` |
| B-12 | `test_list_needs_review_uses_constant_queries` | `tests/test_review_display.py` |
| B-13 | assignment or dead-code removal test | matching module |

Existing `test_sync_apply_and_skip_prior` must stay green (apply still
skips terminal rows).

---

## Ship order

1. Keep `TAGSMITH_ENABLE_BACKGROUND_SYNC=false` in the dogfood
   environment.
2. Implement **C-1** and **C-2** (including watch) first — mailbox
   correctness.
3. Implement **B-1**, **B-4**, **B-5**, **B-6**.
4. Run the Stage 1 test matrix; then restore default background sync.
5. Stage 2 (leave-running): **B-2**, **B-3**, **B-7**, **B-8**, **B-9**,
   docs/debug flags.
6. Stage 3 before any hosted user: auth, cookies, CORS, `tenant_id`,
   per-tenant Gmail, CSRF, KDF, rate limits.
7. Stage 4 in parallel with Stage 3 once labeling is correct: Actions
   SHAs, gitleaks, web smoke, **B-10**–**B-13**.

PRs should reference finding IDs in the title (e.g. `fix(C-1): keep dry-run
messages pending`).

---

## Out of scope

These are Phase 6 product work, not review-opus bugfixes:

- PayPal billing (replace Stripe stubs; [PHASE6.md](PHASE6.md)).
- Google OAuth verification / Limited Use production review.
- Legal review of `policies/` drafts.
- Customer local install / BYOK / desktop installer (dropped).
- Merging this branch to `main` / un-drafting PR #6.

Infrastructure notes from the review that are **not** code bugs: `main`
lagging this branch; PR #6 remaining a draft. Track those in ops, not in
fix PRs.
