# Phase 3 — RAG few-shot retrieval

Status: **in progress on branch `feature/phase-3-rag`** (not merged until approved).

## Goal

Inject the **k most similar previously labeled emails** (plus top category blurbs)
into the classifier prompt, then measure accuracy against the Phase 2 baseline
(**0.972** on DeepSeek / 109 golden cases).

## Design

| Piece | Choice |
|-------|--------|
| Seam | Existing `classify_email(..., examples=, category_hints=)` |
| Embeddings | Deterministic `HashingEmbedder` (offline, no API) — swappable later |
| Store | SQLite table `rag_examples` (same DB as Tagsmith) |
| k | `TAGSMITH_RAG_EXAMPLE_K=5`, `TAGSMITH_RAG_CATEGORY_K=3` |
| Source stamp | `classifications.source = rag` when examples were used |

Flow on `tagsmith sync`:

1. Rules first (unchanged).
2. If miss → retrieve similar labeled examples + category hints.
3. LLM classify with few-shots.
4. On confident apply → upsert example into the store.

Human review confirms/changes also upsert into the store.

**Background catch-up:** `tagsmith schedule` and the API process (`TAGSMITH_ENABLE_BACKGROUND_SYNC`, default on) periodically:

1. Index any `LABELED` SQLite messages missing from `rag_examples`
2. Drop examples whose message is no longer labeled (including Gmail user-removed)
3. Record last catch-up time on `sync_state`

Dry-run sync does **not** index inline (avoids polluting few-shots during a preview). Catch-up still learns from SQLite `LABELED` rows afterward. Held / needs-review wait for a human confirm.

## Commands

```bash
uv run tagsmith rag status
uv run tagsmith rag catchup          # one-shot index missing / drop stale
uv run tagsmith rag reindex          # wipe + rebuild from labeled SQLite messages

# Measure lift vs Phase 2 baseline (costs LLM tokens):
uv run tagsmith eval --json-out evals/baseline_live.json          # no RAG
uv run tagsmith eval --rag --json-out evals/baseline_rag.json     # leave-one-out RAG
```

`--rag` eval indexes golden cases with their **expected** labels, then for each
case retrieves neighbors **excluding itself** (leave-one-out).

## Config

```bash
TAGSMITH_ENABLE_RAG=true
TAGSMITH_RAG_EXAMPLE_K=5
TAGSMITH_RAG_CATEGORY_K=3
TAGSMITH_RAG_EMBEDDING_DIM=256
TAGSMITH_ENABLE_BACKGROUND_SYNC=true
TAGSMITH_BACKGROUND_SYNC_APPLY=false
TAGSMITH_SCHEDULE_INTERVAL_SECONDS=300
```

## Live result (recorded)

| Mode | Accuracy | Misses |
|------|----------|--------|
| Phase 2 no-RAG (v2) | 0.972 | 3 |
| Phase 3 `--rag` leave-one-out | **0.982** | 2 (both holds) |

Details in [EVALS.md](EVALS.md). Hashing embedder delivered a clear +1pp lift; no
hosted embedding swap required for Phase 3 merge readiness.

## Success criteria

- [x] Example store + hashing embedder + retriever
- [x] Wired into sync + review indexing
- [x] Background catch-up on schedule / API loop
- [x] `tagsmith eval --rag` leave-one-out harness
- [x] Live RAG vs Phase 2 baseline numbers recorded in EVALS.md
- [ ] Optional: upgrade embedder to a hosted model if hashing lift is weak (not needed yet)
