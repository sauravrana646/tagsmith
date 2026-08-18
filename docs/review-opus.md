# Code review — 16 August 2026

Static review of branch `feature/phase-4-5-ops-product` at `ec6b614`. No code
was changed as part of this review.

**Method.** Findings were produced by reading the source; every Critical and
High item below was verified directly against the code (file and line quoted).
The test suite was **not** re-run for this review — the working VM had no
`.venv` — but CI was green at the last push.

**Scope.** `src/tagsmith/**`, `web/**`, `.github/workflows/ci.yml`,
`pyproject.toml`, `.gitleaks.toml`, `.gitignore`.

---

## Headline

The most urgent problems are **not** the known SaaS security gaps. Two
correctness bugs mean Tagsmith currently **mislabels a real mailbox**, and one
of them was introduced by the background-sync work in `2d1238b`
(“Keep RAG examples in sync automatically in the background”).

Recommended immediate action: set `TAGSMITH_ENABLE_BACKGROUND_SYNC=false`
until item **C-1** is fixed.

---

## Critical

### C-1 — Dry-run marks messages terminal, so later apply-runs skip them

**Files:** `src/tagsmith/services/sync.py:227-234`, `:353`;
`src/tagsmith/config.py:72-74`; `src/tagsmith/background.py`

`process_email` writes a terminal `MessageState` regardless of whether labels
were applied to Gmail:

```python
# sync.py:353
            message.state = MessageState.LABELED
```

Any later run skips terminal states:

```python
# sync.py:227-234
        terminal = {
            MessageState.LABELED,
            MessageState.HELD,
            MessageState.NEEDS_REVIEW,
            MessageState.SKIPPED,
            MessageState.USER_REMOVED,
        }
        if message.state in terminal and not reprocess:
            counts.skipped_prior += 1
```

This was survivable while dry-run was explicit. It is not survivable now,
because `tagsmith api` starts a background loop that is **on by default** and
runs with **apply off**:

```python
# config.py:72-74
    enable_background_sync: bool = True
    # Background ticks write Gmail labels only when true (default dry-run, like CLI schedule).
    background_sync_apply: bool = False
```

**Failure scenario.** The API is left running. Every ~5 minutes it classifies
unread mail, marks it `labeled` / `held` / `needs_review` in SQLite, and writes
nothing to Gmail. The user then clicks Sync with “Write to Gmail” on: every
message reports `skipped_prior` and the inbox is never labeled. LLM tokens are
spent on every message to produce a discarded result.

**Severity:** Critical. Most likely cause of “the product does nothing” during
dogfooding.

---

### C-2 — Incremental sync advances the history cursor past unprocessed changes

**Files:** `src/tagsmith/gmail/client.py:200-205`;
`src/tagsmith/services/sync.py:571`; `src/tagsmith/services/watch_ops.py:79-83`

`list_history` sets its returned cursor from the response’s **mailbox-head**
`historyId`, then stops paging once it has enough ids:

```python
# client.py:200-205
            if result.get("historyId") is not None:
                latest = str(result["historyId"])
            page_token = result.get("nextPageToken")
            if not page_token or len(ids) >= max_results:
                break
        return ids[:max_results], latest
```

The caller commits that head as the new cursor:

```python
# sync.py:571
            state.history_id = latest or self.gmail.get_profile_history_id()
```

**Failure scenario.** 150 mailbox changes with `limit=100`: 100 are processed,
the cursor jumps to “now”, and the remaining 50 are never returned by
incremental sync again. Full sync only recovers them while they are still
unread. `WatchOps.start_or_renew` has the same defect — it overwrites
`history_id` with the current head regardless of sync progress.

**Severity:** Critical. Silent data loss; nothing logs an error.

---

### C-3 — No authentication on any `/api/*` route

**Files:** `src/tagsmith/api/routes/review.py`, `sync.py`, `status.py`,
`taxonomy.py`; `src/tagsmith/api/app.py:43-57`

No route declares an auth dependency. Combined with CORS that accepts **any**
localhost origin with credentials:

```python
# app.py:43-57
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
        allow_credentials=True,
        allow_methods=["*"],
```

any other process serving a page on any localhost port (a stray `npm run dev`,
a browser extension’s local server) can read held-mail subjects and body
excerpts and POST to apply Gmail labels using the operator’s desktop token.

**Severity:** Critical for the hosted product; High locally. Treat a running
API as root-equivalent for the mailbox.

---

## Security gaps (hosted SaaS blockers)

| Gap | Where | Why it matters |
|---|---|---|
| Session cookie is an unsigned tenant id | `api/routes/oauth.py:28-37` | Sending `tagsmith_tenant=1` authenticates as that tenant. `session_signing_key` exists in `config.py:91` and is never used |
| OAuth `state` never validated | `api/routes/oauth.py:123-129` | `/auth/login` sets an `oauth_state` cookie; `/auth/callback` takes `state` as a query param and never compares them. Classic OAuth CSRF / account-linking |
| No tenant isolation | `db/models.py` | `Message`, `SyncState`, `RagExample` have no `tenant_id`; sync state is hardcoded row `id=1`. One shared queue and RAG index for all customers |
| Tenant tokens stored but never used | `api/deps.py:27-35` | Refresh tokens are encrypted on callback, then `gmail_dep` always falls back to the operator desktop token. Sign-in implies per-user access that does not exist |
| No CSRF tokens; cookie lacks `Secure` | `api/routes/oauth.py:31-37` | Required by `docs/PHASE6.md` §7 |
| `/auth/debug` and `/docs` public | `api/routes/oauth.py:70`, `api/app.py:37` | Config disclosure plus a map of unauthenticated endpoints |
| Open redirect / HTML injection via `web_app_url` | `api/routes/oauth.py:165`, `api/app.py:79-86` | Interpolated into redirects and f-string HTML without validation or escaping |
| Key derivation is a single SHA-256 pass | `security/crypto.py:14-20` | No salt, no KDF. Weak passphrase + DB backup allows offline brute force of refresh tokens |
| Stripe webhook trusts `customer_email` | `api/routes/billing.py:66-77` | Signature verification is correct, but plan upgrades key off an email in the payload, with no idempotency |
| `POST /api/sync/watch/renew` accepts any topic | `api/routes/sync.py:86-94` | Unauthenticated caller can point mailbox push notifications at their own Pub/Sub topic |
| No rate limiting | all routes | `POST /api/sync/run` accepts `limit=500` per call against the operator’s LLM billing |

---

## Other confirmed bugs

| # | Severity | Issue | Where |
|---|---|---|---|
| B-1 | High | No mutual exclusion between the background loop and manual sync — duplicate classification, duplicate LLM spend, race on `history_id` | `background.py`, `api/routes/sync.py` |
| B-2 | High | Synchronous `googleapiclient` / `httpx` calls inside `async def` handlers stall the event loop for the whole sync | `gmail/client.py:46-53`, `services/sync.py:488-499` |
| B-3 | High | Gmail labels are written **before** the DB commit, so a crash leaves Gmail and SQLite disagreeing | `services/sync.py:303-387` |
| B-4 | High | `confirm_label`, `change_label`, `approve_proposal` never remove the `AI/needs-review` label they resolve — it stays in Gmail permanently | `services/review_ops.py:257`, `:385-410`, `:427-439` |
| B-5 | High | `approve_proposal` → `reclassify_held` re-runs **every** held message with `apply`, not just the approved category’s message | `services/review_ops.py:296-298`, `services/sync.py:578-599` |
| B-6 | High | RAG catch-up indexes any `LABELED` row, defeating the “index only committed applies” gate; dry-run rows become few-shot examples. `tests/test_sync_and_review.py` currently **asserts** this behaviour, so the test encodes the bug | `rag/index.py:117-146` |
| B-7 | Medium | `except Exception` around `list_history` treats every failure (503, auth) as a stale cursor and silently falls back to full sync | `services/sync.py:540-552` |
| B-8 | Medium | SQLite engine has no WAL mode or busy timeout while two sessions write concurrently — expect `database is locked` | `db/session.py:39-44` |
| B-9 | Medium | Full sync has no per-message `try/except` (incremental does); one deleted message aborts the run and leaves `Run` unfinalized | `services/sync.py:490-492` |
| B-10 | Medium | RAG loads **all** examples and re-embeds every seed category on **every** classified message | `rag/store.py:94-127`, `rag/retriever.py:51-60` |
| B-11 | Medium | Proposal dedupe is not atomic; `reject_and_propose` filters only on `dedupe_key` then calls `.one()` — can raise, or attach another message’s proposal | `review/queue.py:105-142`, `services/review_ops.py:490-507` |
| B-12 | Medium | N+1 queries in review list endpoints | `review/queue.py:47-92` |
| B-13 | Low | `MessageState.SKIPPED` is never assigned; `messagesDeleted` is read but not requested in `historyTypes` | `db/models.py:28`, `gmail/client.py:187-193` |

---

## Infrastructure and hygiene

- `.gitleaks.toml` allowlists `docs/**` entirely. This repo puts a lot of prose
  in `docs/`, so a secret pasted there would not fail CI.
- GitHub Actions are pinned to moving tags (`@v4`, `@v5`), not commit SHAs.
- `web/` has no tests and no JS dependency scanning; Python has both `pip-audit`
  and Bandit.
- `main` is 32 commits behind this branch; PR #6 is still a draft.

### Verified good (keep)

- Minimal Gmail scopes; no `https://mail.google.com/`.
- `yaml.safe_load` everywhere; no `pickle` / `eval` on untrusted input.
- No `dangerouslySetInnerHTML`; React escapes rendered subjects and senders.
- CI blocks tracked `.env` / `credentials.json` / `token.json` / `*.pem`.
- Rule hits store `confidence=NULL`, so they do not contaminate calibration.
- CI uses `pull_request` (not `pull_request_target`), so fork PRs get a
  read-only token.

---

## Resolution plan

### Stage 1 — make labeling correct before dogfooding again

Touches `services/sync.py`, `gmail/client.py`, `services/watch_ops.py`,
`services/review_ops.py`, `rag/index.py`.

- [ ] Stop writing terminal states on dry-run, or record an `applied` flag and
      skip only when Gmail actually holds the label (**C-1**)
- [ ] Advance `history_id` only to the last fully-processed history record;
      stop watch renewal from moving the cursor past unprocessed changes (**C-2**)
- [ ] Add a single-flight lock so background and manual sync cannot overlap (**B-1**)
- [ ] Remove the needs-review label on confirm / change / approve (**B-4**)
- [ ] Scope `reclassify_held` to the approved category (**B-5**)
- [ ] Gate RAG catch-up on committed applies and fix the test that asserts
      otherwise (**B-6**)

Every item needs a regression test. These are all silent failures, which is
precisely why they survived.

### Stage 2 — safe to leave running

- [ ] Move blocking Gmail calls off the event loop (`asyncio.to_thread`) (**B-2**)
- [ ] Commit the DB before the Gmail write, or make the write recoverable (**B-3**)
- [ ] Narrow `list_history` exception handling to real stale-cursor errors (**B-7**)
- [ ] Enable WAL and a busy timeout on SQLite (**B-8**)
- [ ] Add per-message error tolerance to full sync (**B-9**)
- [ ] Disable `/docs` by default; require an explicit flag for `/auth/debug`

### Stage 3 — SaaS prerequisites

Largest change; touches the data model. **Do not open the product to anyone
before this completes.**

- [ ] Add `tenant_id` to `Message`, `SyncState`, `ClassificationRecord`,
      `Proposal`, `RagExample`, and scope every query
- [ ] Sign the session cookie using the existing `session_signing_key`
- [ ] Validate OAuth `state` against the cookie, then clear it
- [ ] Wire `gmail_dep` to per-tenant decrypted refresh tokens
- [ ] Require auth on all `/api/*` routes (**C-3**)
- [ ] Replace the localhost CORS regex with an explicit production origin
- [ ] Add `Secure` cookies, CSRF protection, per-tenant rate limits
- [ ] Allowlist redirect targets; escape settings interpolated into HTML
- [ ] Use a real KDF (and plan for KMS) for the token encryption key

### Stage 4 — quality and supply chain

- [ ] Pin GitHub Actions to commit SHAs
- [ ] Narrow the gitleaks `docs/**` allowlist
- [ ] Add JS dependency scanning and a smoke test for `web/`
- [ ] Address the RAG full-table scan (**B-10**) and review-list N+1 (**B-12**)

---

## What to do first

1. Set `TAGSMITH_ENABLE_BACKGROUND_SYNC=false`. It costs nothing and stops the
   dry-run loop from silently marking mail as done.
2. Fix **C-1** and **C-2**. Those two are the difference between “labels my
   inbox” and “quietly does nothing”.
