"""Run the classify pipeline against a golden set."""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from tagsmith.classify.pipeline import PipelineResult, classify_with_routing
from tagsmith.classify.rules import load_rules
from tagsmith.config import PROMPT_VERSION, Settings
from tagsmith.evals.golden import load_golden_set
from tagsmith.evals.metrics import EvalReport, compute_report
from tagsmith.gmail.parser import normalize_message
from tagsmith.taxonomy.registry import load_seed_categories
from tagsmith.telemetry import get_logger, span

log = get_logger(__name__)

ClassifyFn = Callable[..., Awaitable[PipelineResult]]


@contextmanager
def _eval_progress(*, enabled: bool, total: int) -> Iterator[Callable[[str], None]]:
    """Bottom-of-terminal progress bar showing done/total (e.g. 92/109)."""

    if not enabled or total <= 0:
        yield lambda _case_id: None
        return

    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    console = Console(stderr=True)
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]eval[/bold]"),
        BarColumn(bar_width=28),
        MofNCompleteColumn(),  # e.g. 92/109
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("left"),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.description}[/dim]"),
        console=console,
        transient=False,
        refresh_per_second=10,
    ) as progress:
        task_id = progress.add_task("", total=total)

        def advance(case_id: str) -> None:
            progress.advance(task_id)
            progress.update(task_id, description=case_id)

        yield advance


@dataclass(slots=True)
class EvalCaseResult:
    case_id: str
    expected_label_key: str | None
    predicted_label_key: str | None
    correct: bool
    source: str
    route: str
    confidence: float | None
    has_proposal: bool
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        # slots=True means no ``__dict__``; build explicitly for JSON export.
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class EvalRunResult:
    report: EvalReport
    cases: list[EvalCaseResult]

    def as_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.as_dict(),
            "cases": [c.as_dict() for c in self.cases],
        }


def _active_keys() -> list[str]:
    return [c.key for c in load_seed_categories()]


def _catalog() -> str:
    lines: list[str] = []
    for cat in load_seed_categories():
        exemplars = "; ".join(cat.exemplars[:2])
        lines.append(f"- {cat.key}: {cat.description} (e.g. {exemplars})")
    return "\n".join(lines)


async def run_eval(
    golden_path: Path,
    *,
    settings: Settings,
    rules_only: bool = False,
    use_rag: bool = False,
    classify_fn: ClassifyFn | None = None,
    show_progress: bool | None = None,
) -> EvalRunResult:
    """Evaluate pipeline predictions against a golden JSONL set.

    `rules_only`: skip LLM — unmatched emails are treated as hold_propose with
    null label (useful for offline CI). Live LLM evals should leave this False.

    `use_rag`: leave-one-out few-shots — index golden cases with expected labels,
    retrieve k examples excluding the current message (Phase 3).

    `show_progress`: bottom progress bar with done/total (e.g. 92/109). Defaults
    to on when stderr is a TTY.
    """
    cases = load_golden_set(golden_path)
    label_keys = _active_keys()
    catalog = _catalog()
    rules = load_rules(settings.rules_path, set(label_keys))
    runner = classify_fn or classify_with_routing
    if show_progress is None:
        show_progress = sys.stderr.isatty()

    results: list[EvalCaseResult] = []
    rag_session = None
    rag_retriever = None

    rag_tmpdir = None
    if use_rag and not rules_only:
        import tempfile
        from pathlib import Path

        from sqlmodel import Session

        from tagsmith.db.session import init_db, reset_engine
        from tagsmith.rag.index import make_store
        from tagsmith.rag.retriever import Retriever
        from tagsmith.rag.store import example_text_from_email

        # Use a temp file DB (not :memory:) so create_all + Session share one store.
        # sqlite:///:memory: gives each engine/connection an empty private DB.
        reset_engine()
        rag_tmpdir = tempfile.TemporaryDirectory(prefix="tagsmith-rag-eval-")
        db_path = Path(rag_tmpdir.name) / "rag_eval.db"
        tmp_settings = settings.model_copy(
            update={
                "database_url": f"sqlite:///{db_path}",
                "enable_rag": True,
            }
        )
        engine = init_db(tmp_settings)
        rag_session = Session(engine)
        store = make_store(rag_session, tmp_settings)
        for other in cases:
            if other.expected_label_key is None:
                continue
            other_email = normalize_message(
                other.message,
                body_char_limit=settings.body_char_limit,
            )
            meta = example_text_from_email(
                sender=other_email.sender,
                subject=other_email.subject,
                body_text=other_email.body_text,
            )
            store.upsert(
                gmail_id=other_email.gmail_id,
                label_key=other.expected_label_key,
                sender=meta["sender"],
                subject=meta["subject"],
                body_excerpt=meta["body_excerpt"],
            )
        rag_retriever = Retriever(
            store,
            store.embedder,
            example_k=settings.rag_example_k,
            category_k=settings.rag_category_k,
        )

    try:
        with (
            span(
                "tagsmith.eval.run",
                n_cases=len(cases),
                rules_only=rules_only,
                use_rag=use_rag,
            ),
            _eval_progress(enabled=show_progress, total=len(cases)) as tick,
        ):
            for case in cases:
                email = normalize_message(
                    case.message,
                    body_char_limit=settings.body_char_limit,
                )
                if rules_only:
                    from tagsmith.classify.rules import match_rules
                    from tagsmith.classify.schema import (
                        Classification,
                        NewCategory,
                        route_classification,
                    )

                    ruled = match_rules(email, rules)
                    if ruled and ruled.label_key:
                        pipeline = PipelineResult(
                            classification=ruled,
                            route=route_classification(
                                ruled,
                                apply_threshold=settings.confidence_apply,
                                review_threshold=settings.confidence_review,
                            ),
                            source="rule",
                        )
                    else:
                        hold = Classification(
                            label_key=None,
                            confidence=0.0,
                            rationale="rules-only eval: no rule matched",
                            proposed_new=NewCategory(
                                suggested_key="rules-only-miss",
                                description=("Placeholder for offline rules-only eval misses"),
                                why_no_existing_fit=(
                                    "No builtin/user rule matched this golden case"
                                ),
                            ),
                        )
                        pipeline = PipelineResult(
                            classification=hold,
                            route="hold_propose",
                            source="llm",
                        )
                else:
                    examples = None
                    category_hints = None
                    if rag_retriever is not None:
                        from tagsmith.rag.retriever import format_category_hints
                        from tagsmith.rag.store import example_text_from_email

                        query = example_text_from_email(
                            sender=email.sender,
                            subject=email.subject,
                            body_text=email.body_text,
                        )["text"]
                        rag_ctx = rag_retriever.retrieve(
                            query,
                            exclude_gmail_ids={email.gmail_id},
                        )
                        examples = rag_ctx.examples or None
                        category_hints = format_category_hints(rag_ctx.category_hints) or None

                    pipeline = await runner(
                        email,
                        rules=rules,
                        label_keys=label_keys,
                        catalog=catalog,
                        settings=settings,
                        examples=examples,
                        category_hints=category_hints,
                        blocked_keys=None,
                    )

                predicted = pipeline.classification.label_key
                expected = case.expected_label_key
                correct = predicted == expected
                if case.expected_route is not None:
                    correct = correct and pipeline.route == case.expected_route

                case_result = EvalCaseResult(
                    case_id=case.id,
                    expected_label_key=expected,
                    predicted_label_key=predicted,
                    correct=correct,
                    source=pipeline.source,
                    route=pipeline.route,
                    confidence=pipeline.classification.confidence,
                    has_proposal=pipeline.classification.proposed_new is not None,
                    latency_ms=pipeline.latency_ms,
                    input_tokens=pipeline.input_tokens,
                    output_tokens=pipeline.output_tokens,
                    rationale=pipeline.classification.rationale,
                )
                results.append(case_result)
                log.info(
                    "eval.case",
                    case_id=case.id,
                    expected=expected,
                    predicted=predicted,
                    correct=correct,
                    source=pipeline.source,
                    route=pipeline.route,
                )
                tick(case.id)
    finally:
        if rag_session is not None:
            rag_session.close()
        if use_rag and not rules_only:
            from tagsmith.db.session import reset_engine

            reset_engine()
        if rag_tmpdir is not None:
            rag_tmpdir.cleanup()

    report = compute_report(
        expected_keys=[r.expected_label_key for r in results],
        predicted_keys=[r.predicted_label_key for r in results],
        sources=[r.source for r in results],
        routes=[r.route for r in results],
        has_proposals=[r.has_proposal for r in results],
        latencies_ms=[r.latency_ms for r in results],
        input_tokens=[r.input_tokens for r in results],
        output_tokens=[r.output_tokens for r in results],
        cost_per_1k_input=settings.cost_per_1k_input_tokens,
        cost_per_1k_output=settings.cost_per_1k_output_tokens,
        prompt_version=PROMPT_VERSION,
        model=settings.llm_model,
    )
    return EvalRunResult(report=report, cases=results)


def default_golden_path() -> Path:
    return Path(__file__).resolve().parents[3] / "evals" / "golden_set.jsonl"


def format_report(report: EvalReport, *, cases: list[EvalCaseResult] | None = None) -> str:
    lines: list[str] = []
    lines.append(f"cases={report.n_cases} accuracy={report.accuracy:.3f}")
    lines.append(
        f"rule_hit_rate={report.rule_hit_rate:.3f} "
        f"llm_routing_rate={report.llm_routing_rate:.3f} "
        f"proposal_rate={report.proposal_rate:.3f} "
        f"hold_rate={report.hold_rate:.3f}"
    )
    lat = (
        f"latency_ms p50={report.latency_p50_ms:.1f} p95={report.latency_p95_ms:.1f}"
        if report.latency_p50_ms is not None and report.latency_p95_ms is not None
        else "latency_ms n/a (rules-only or no timings)"
    )
    lines.append(lat)
    lines.append(
        f"tokens in={report.total_input_tokens} out={report.total_output_tokens} "
        f"cost_usd={report.cost_usd_estimate} per_email={report.cost_per_email_usd}"
    )
    lines.append("per-label precision/recall/f1 (support):")
    for row in report.per_label:
        p = "n/a" if row.precision is None else f"{row.precision:.3f}"
        r = "n/a" if row.recall is None else f"{row.recall:.3f}"
        f1 = "n/a" if row.f1 is None else f"{row.f1:.3f}"
        lines.append(
            f"  {row.label}: P={p} R={r} F1={f1} support={row.support} predicted={row.predicted}"
        )
    if cases:
        misses = [c for c in cases if not c.correct]
        if misses:
            lines.append(f"misses ({len(misses)}):")
            for miss in misses[:50]:
                lines.append(
                    f"  {miss.case_id}: expected={miss.expected_label_key} "
                    f"got={miss.predicted_label_key} source={miss.source} route={miss.route}"
                )
    return "\n".join(lines)
