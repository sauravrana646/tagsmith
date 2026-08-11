#!/usr/bin/env python3
"""Run Phase 2 evals against evals/golden_set.jsonl.

Examples:
  uv run python evals/run_eval.py --rules-only
  uv run python evals/run_eval.py                 # live LLM (needs provider keys)
  uv run python evals/run_eval.py --json-out /tmp/eval.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from tagsmith.config import get_settings  # noqa: E402
from tagsmith.evals.runner import default_golden_path, format_report, run_eval  # noqa: E402
from tagsmith.telemetry import configure_logging, configure_observability  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Tagsmith Phase 2 eval harness")
    parser.add_argument(
        "--golden",
        type=Path,
        default=default_golden_path(),
        help="Path to golden_set.jsonl",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Skip LLM; unmatched cases count as hold misses (offline CI).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write full report JSON",
    )
    parser.add_argument(
        "--logfire",
        action="store_true",
        help="Enable Logfire if LOGFIRE_TOKEN is present",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    configure_observability(enabled=args.logfire or settings.enable_logfire)

    result = asyncio.run(
        run_eval(
            args.golden,
            settings=settings,
            rules_only=args.rules_only,
        )
    )
    print(format_report(result.report, cases=result.cases))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "report": result.report.as_dict(),
            "cases": [c.__dict__ for c in result.cases],
        }
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
