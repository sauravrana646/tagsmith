# Phase 2 golden set
#
# Grow this toward 100–200 hand-labeled emails before trusting RAG (Phase 3).
# Seed includes fixture-derived cases plus synthetic coverage across the taxonomy.
#
# Format: one JSON object per line (GoldenCase). See docs/EVALS.md.
#
# Offline CI: `uv run python evals/run_eval.py --rules-only`
# Live LLM:   `uv run python evals/run_eval.py` (requires provider API keys)
