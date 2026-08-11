# Phase 3 — RAG few-shot retrieval

Status: **in progress on branch `cursor/phase-3-rag`** (not merged until approved).

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

## Commands

```bash
uv run tagsmith rag status
uv run tagsmith rag reindex          # rebuild from labeled SQLite messages

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
```

## Success criteria

- [x] Example store + hashing embedder + retriever
- [x] Wired into sync + review indexing
- [x] `tagsmith eval --rag` leave-one-out harness
- [ ] Live RAG vs no-RAG baseline numbers recorded in EVALS.md
- [ ] Optional: upgrade embedder to a hosted model if hashing lift is weak
