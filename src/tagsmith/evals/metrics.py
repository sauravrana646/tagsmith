"""Aggregate metrics for Phase 2 eval runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class LabelScores:
    label: str
    precision: float | None
    recall: float | None
    f1: float | None
    support: int  # expected count
    predicted: int


@dataclass
class EvalReport:
    n_cases: int
    accuracy: float
    per_label: list[LabelScores]
    rule_hit_rate: float
    llm_routing_rate: float
    proposal_rate: float
    hold_rate: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    avg_latency_ms: float | None
    total_input_tokens: int
    total_output_tokens: int
    cost_usd_estimate: float | None
    cost_per_email_usd: float | None
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    prompt_version: str | None = None
    model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _prf(tp: int, fp: int, fn: int) -> tuple[float | None, float | None, float | None]:
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def compute_report(
    *,
    expected_keys: list[str | None],
    predicted_keys: list[str | None],
    sources: list[str],
    routes: list[str],
    has_proposals: list[bool],
    latencies_ms: list[float | None],
    input_tokens: list[int | None],
    output_tokens: list[int | None],
    cost_per_1k_input: float = 0.0,
    cost_per_1k_output: float = 0.0,
    prompt_version: str | None = None,
    model: str | None = None,
) -> EvalReport:
    n = len(expected_keys)
    if n == 0:
        raise ValueError("cannot compute report on empty eval")
    if not (
        len(predicted_keys)
        == len(sources)
        == len(routes)
        == len(has_proposals)
        == len(latencies_ms)
        == len(input_tokens)
        == len(output_tokens)
        == n
    ):
        raise ValueError("metric input lists must be the same length")

    correct = sum(1 for e, p in zip(expected_keys, predicted_keys, strict=True) if e == p)
    accuracy = correct / n

    labels = sorted({k for k in expected_keys + predicted_keys if k is not None})
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    support: dict[str, int] = defaultdict(int)
    predicted_count: dict[str, int] = defaultdict(int)
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for exp, pred in zip(expected_keys, predicted_keys, strict=True):
        exp_s = exp or "<none>"
        pred_s = pred or "<none>"
        confusion[exp_s][pred_s] += 1
        if exp is not None:
            support[exp] += 1
        if pred is not None:
            predicted_count[pred] += 1
        if exp is not None and pred is not None:
            if exp == pred:
                tp[exp] += 1
            else:
                fp[pred] += 1
                fn[exp] += 1
        elif exp is not None and pred is None:
            fn[exp] += 1
        elif exp is None and pred is not None:
            fp[pred] += 1

    per_label: list[LabelScores] = []
    for label in labels:
        precision, recall, f1 = _prf(tp[label], fp[label], fn[label])
        per_label.append(
            LabelScores(
                label=label,
                precision=precision,
                recall=recall,
                f1=f1,
                support=support[label],
                predicted=predicted_count[label],
            )
        )

    rule_hits = sum(1 for s in sources if s == "rule")
    # Phase 3: RAG-backed LLM path counts as model routing alongside plain llm.
    llm_hits = sum(1 for s in sources if s in {"llm", "rag"})
    holds = sum(1 for r in routes if r == "hold_propose")
    proposals = sum(1 for p in has_proposals if p)

    latency_vals = sorted(v for v in latencies_ms if v is not None)
    in_tok = sum(t or 0 for t in input_tokens)
    out_tok = sum(t or 0 for t in output_tokens)
    cost = None
    if in_tok or out_tok:
        cost = (in_tok / 1000.0) * cost_per_1k_input + (out_tok / 1000.0) * cost_per_1k_output
        if cost == 0.0 and cost_per_1k_input == 0.0 and cost_per_1k_output == 0.0:
            cost = None

    return EvalReport(
        n_cases=n,
        accuracy=accuracy,
        per_label=per_label,
        rule_hit_rate=rule_hits / n,
        llm_routing_rate=llm_hits / n,
        proposal_rate=proposals / n,
        hold_rate=holds / n,
        latency_p50_ms=_percentile(latency_vals, 0.50),
        latency_p95_ms=_percentile(latency_vals, 0.95),
        avg_latency_ms=(sum(latency_vals) / len(latency_vals)) if latency_vals else None,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        cost_usd_estimate=cost,
        cost_per_email_usd=(cost / n) if cost is not None else None,
        confusion={k: dict(v) for k, v in confusion.items()},
        prompt_version=prompt_version,
        model=model,
    )
