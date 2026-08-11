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
- Seed today: ~19 cases (fixtures + synthetic). **Target: 100–200 hand-labeled real emails** before claiming RAG lift.

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

## Success criteria for “Phase 2 done”

- [ ] Golden set ≥ 100 labeled cases (diverse senders/labels)
- [ ] Live eval baseline checked in as a JSON artifact or docs note
- [ ] Threshold tuning decisions recorded in DECISIONS.md from eval data
- [ ] Logfire (or OTel exporter) usable for a real sync run
