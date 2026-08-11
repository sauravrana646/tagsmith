# Phase 2 — Evals & observability

Status: **in progress on branch `cursor/phase-2-evals-observability`** (not merged until approved).

## Goals

1. Make classifier quality **measurable** before RAG (Phase 3).
2. Capture **latency, token usage, and rough cost** per classify/sync/eval.
3. Optional **Logfire / OpenTelemetry** tracing for LLM runs.

## Golden set

Path: [`evals/golden_set.jsonl`](../evals/golden_set.jsonl)

Each line is a `GoldenCase`:

```json
{
  "id": "fixture_otp_github",
  "expected_label_key": "otp-verification",
  "expected_route": "apply",
  "notes": "...",
  "message": { "... Gmail messages.get JSON ..." }
}
```

- `expected_label_key: null` → expect no existing label (hold / propose).
- `expected_route` optional; when set, both label and route must match to score correct.
- Seed today: **100+** synthetic but realistic cases across all 16 labels + holds
  (`uv run python evals/generate_golden_set.py`). Real inbox labels can be merged via
  `tagsmith eval-export-corrections`. **Live LLM baseline + threshold tuning are deferred**
  until provider API keys are available in the environment.

Grow the set by:

1. Dogfooding `tagsmith sync` + `tagsmith review`.
2. `tagsmith eval-export-corrections` → spot-check → append to `golden_set.jsonl`.
3. Hand-labeling additional saved Gmail JSON dumps (never commit secrets).

## Running evals

Offline (CI-friendly, rules only):

```bash
uv run python evals/run_eval.py --rules-only
# or
uv run tagsmith eval --rules-only
```

Live LLM (needs provider keys in `.env`):

```bash
uv run tagsmith eval --json-out /tmp/eval.json
```

Reports:

- overall accuracy
- per-label precision / recall / F1
- rule hit rate, LLM routing rate, proposal rate, hold rate
- latency p50 / p95 (LLM path)
- token totals + optional USD estimate (`TAGSMITH_COST_PER_1K_*`)

## Observability

```bash
# optional dependency
uv sync --group observability

# env
TAGSMITH_ENABLE_LOGFIRE=true
LOGFIRE_TOKEN=...   # or rely on send_to_logfire=if-token-present
```

`configure_observability()` instruments Pydantic AI and opens spans around classify/sync/eval. When Logfire is disabled/missing, spans are no-ops.

## Library layout

| Module | Role |
|--------|------|
| `tagsmith.evals.golden` | JSONL schema/loader |
| `tagsmith.evals.metrics` | Aggregate report |
| `tagsmith.evals.runner` | Pipeline over golden set |
| `tagsmith.evals.export_corrections` | Harvest review final_keys |
| `tagsmith.classify.outcome` | Tokens + latency from LLM |
| `tagsmith.telemetry` | structlog + optional Logfire |

## Live baseline (recorded)

Operator runs on Phase 2 branch with `openrouter:deepseek/deepseek-v4-flash-0731`
against `evals/golden_set.jsonl` (109 cases):

| Run | Prompt | Accuracy | Misses |
|-----|--------|----------|--------|
| Initial | v1 | 0.945 (103/109) | 6 |
| After disambiguation | v2 | **0.972 (106/109)** | 3 |

Latest metrics (v2):

| Metric | Value |
|--------|------:|
| Accuracy | **0.972** |
| Rule hit rate | 0.266 |
| LLM routing rate | 0.734 |
| Proposal / hold rate | 0.064 / 0.073 |
| Latency p50 / p95 | ~3.4s / ~8.6s |
| Tokens in / out | 266305 / 9373 |

**Remaining misses (3) after v2:**

| Case | Expected | Got | Notes |
|------|----------|-----|--------|
| `gold_tax_1099` | tax-document | hold | Over-cautious; tax transcript *is* tax-document |
| `gold_hold_medical` | hold | support-ticket | Lab portal ≠ support |
| `gold_hold_donation` | hold | support-ticket | Volunteering thanks ≠ support |

**Threshold decision:** keep defaults (`apply=0.75`, `review=0.5`). Accuracy is high
enough for a Phase 2 baseline; optional prompt tweaks for the last 3, then grow with
real inbox corrections before Phase 3.

Artifact: `evals/baseline_live.json` (local; re-run to refresh):

```bash
uv run tagsmith eval --json-out evals/baseline_live.json
```

## Phase 3 RAG baseline (recorded)

Operator run on `feature/phase-3-rag` with the same DeepSeek model and golden set
(`tagsmith eval --rag`, leave-one-out few-shots from expected labels):

| Run | Mode | Accuracy | Misses |
|-----|------|----------|--------|
| Phase 2 reference | no RAG (prompt v2) | 0.972 (106/109) | 3 |
| Phase 3 | `--rag` leave-one-out | **0.982 (107/109)** | 2 |

Latest RAG metrics:

| Metric | Value |
|--------|------:|
| Accuracy | **0.982** |
| Rule hit rate | 0.266 |
| LLM routing rate | 0.734 |
| Proposal / hold rate | 0.092 / 0.092 |
| Latency p50 / p95 | ~5.8s / ~19.4s |
| Tokens in / out | 314910 / 17015 |

**Lift vs Phase 2:** +0.010 accuracy (1 fewer miss). Both remaining misses are
cautious holds (`got=None`, `route=hold_propose`, `source=rag`), not wrong labels:

| Case | Expected | Got | Notes |
|------|----------|-----|--------|
| `gold_order_amazon2` | order-confirmation | hold | Over-cautious with RAG neighbors |
| `gold_support_resolved` | support-ticket | hold | Resolved-ticket wording → hold |

Trade-offs: prompt tokens and latency rose (few-shot injection), as expected.
Hashing embedder is sufficient for this golden set; hosted embeddings remain optional.

Artifact: `evals/baseline_rag.json` (local; re-run to refresh):

```bash
uv run tagsmith eval --rag --json-out evals/baseline_rag.json
```

## Success criteria for “Phase 2 done”

- [x] Golden set ≥ 100 labeled cases (diverse senders/labels) — synthetic seed; replace/augment with real inbox over time
- [x] Live eval baseline recorded (above; optionally commit `evals/baseline_live.json`)
- [x] Threshold tuning decision recorded (keep defaults; see above + DECISIONS.md)
- [ ] Logfire (or OTel exporter) usable for a real sync run (optional)
- [x] Address the 6 known golden misses (Chase refund rule + prompt v2 disambiguation)

### How to fix golden-set misses (playbook)

For each miss, pick **one** lever (don’t thrash all three):

1. **Rule bug** (source=`rule`, wrong label)  
   Tighten/add a builtin or user rule. Example: “Charge reversed” → `refund`, not `payment-sent`.

2. **Prompt / taxonomy ambiguity** (source=`llm`, two labels both plausible)  
   Add a disambiguation bullet to `SYSTEM_PROMPT` and/or clarify `seed.yaml` descriptions.  
   Bump `PROMPT_VERSION` when the prompt changes, then re-run eval.

3. **Wrong expected label** (model is right, golden is wrong)  
   Edit `evals/golden_set.jsonl` (or `generate_golden_set.py` + regenerate).  
   Only do this when you’d accept the model’s label in the real product.

4. **Should be hold** (forced into a weak existing label)  
   Keep `expected_label_key: null` + `expected_route: hold_propose`.  
   Teach the model via prompt: “partial overlap ≠ fit; prefer null + proposed_new”.

After any change:

```bash
uv run tagsmith eval --json-out evals/baseline_live.json
# compare accuracy + which case_ids remain in misses
```
