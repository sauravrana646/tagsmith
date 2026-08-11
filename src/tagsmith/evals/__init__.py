"""Phase 2 evaluation library: golden sets, metrics, runner."""

from tagsmith.evals.golden import GoldenCase, load_golden_set
from tagsmith.evals.metrics import EvalReport, compute_report
from tagsmith.evals.runner import EvalCaseResult, run_eval

__all__ = [
    "EvalCaseResult",
    "EvalReport",
    "GoldenCase",
    "compute_report",
    "load_golden_set",
    "run_eval",
]
