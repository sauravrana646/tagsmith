"""Phase 2 evals and observability unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagsmith.classify.schema import Classification, NewCategory
from tagsmith.config import Settings
from tagsmith.evals.golden import GoldenCase, load_golden_set
from tagsmith.evals.metrics import compute_report
from tagsmith.evals.rebuild import normalized_payload_to_gmail_message
from tagsmith.evals.runner import run_eval
from tagsmith.telemetry import configure_observability, span


def test_compute_report_per_label_and_rates() -> None:
    report = compute_report(
        expected_keys=["payment-sent", "otp-verification", None, "newsletter"],
        predicted_keys=["payment-sent", "security-alert", None, "newsletter"],
        sources=["rule", "llm", "llm", "rule"],
        routes=["apply", "apply", "hold_propose", "apply"],
        has_proposals=[False, False, True, False],
        latencies_ms=[10.0, 20.0, 30.0, None],
        input_tokens=[100, 200, 50, None],
        output_tokens=[10, 20, 5, None],
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.02,
        prompt_version="v1",
        model="test",
    )
    assert report.n_cases == 4
    assert report.accuracy == 0.75
    assert report.rule_hit_rate == 0.5
    assert report.llm_routing_rate == 0.5
    assert report.proposal_rate == 0.25
    assert report.hold_rate == 0.25
    assert report.latency_p50_ms == 20.0
    assert report.total_input_tokens == 350
    assert report.cost_usd_estimate is not None
    assert report.cost_usd_estimate > 0
    by_label = {row.label: row for row in report.per_label}
    assert by_label["payment-sent"].precision == 1.0
    assert by_label["newsletter"].recall == 1.0


def test_load_golden_set_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "golden.jsonl"
    case = GoldenCase(
        id="c1",
        expected_label_key="otp-verification",
        expected_route="apply",
        notes="x",
        message={"id": "m1", "payload": {"headers": [], "body": {"data": ""}}},
    )
    path.write_text(case.model_dump_json() + "\n", encoding="utf-8")
    loaded = load_golden_set(path)
    assert len(loaded) == 1
    assert loaded[0].expected_label_key == "otp-verification"


@pytest.mark.asyncio
async def test_run_eval_rules_only_on_repo_golden(settings: Settings) -> None:
    golden = Path("evals/golden_set.jsonl")
    assert golden.exists()
    result = await run_eval(golden, settings=settings, rules_only=True, show_progress=False)
    assert result.report.n_cases >= 100
    # Fixture OTP/security/payment/newsletter should be rule hits.
    by_id = {c.case_id: c for c in result.cases}
    assert by_id["fixture_otp_github"].correct
    assert by_id["fixture_otp_github"].source == "rule"
    assert by_id["fixture_security_google"].correct
    assert by_id["fixture_payment_chase"].correct


def test_rebuild_normalized_payload() -> None:
    msg = normalized_payload_to_gmail_message(
        gmail_id="g1",
        thread_id="t1",
        payload={
            "sender": "a@b.com",
            "to": "u@example.com",
            "subject": "Hi",
            "date": "Mon, 1 Jan 2025 00:00:00 +0000",
            "body_text": "hello",
            "label_ids": ["INBOX"],
        },
    )
    assert msg["id"] == "g1"
    assert msg["payload"]["headers"][0]["value"] == "a@b.com"


def test_configure_observability_disabled_is_noop() -> None:
    assert configure_observability(enabled=False) is False
    with span("tagsmith.test.noop", x=1):
        pass


def test_golden_set_jsonl_parses() -> None:
    path = Path("evals/golden_set.jsonl")
    cases = load_golden_set(path)
    assert len(cases) >= 100
    # Every line is valid JSON with required keys
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        assert "id" in obj and "message" in obj
    labels = {c.expected_label_key for c in cases}
    # All 16 seed keys plus explicit holds (None)
    assert None in labels
    assert len(labels - {None}) >= 16


def test_classification_still_requires_proposal_when_null() -> None:
    with pytest.raises(ValueError):
        Classification(label_key=None, confidence=0.1, rationale="x", proposed_new=None)
    Classification(
        label_key=None,
        confidence=0.1,
        rationale="x",
        proposed_new=NewCategory(
            suggested_key="home-insurance-renewal",
            description="Home insurance renewal packets",
            why_no_existing_fit="No insurance category",
        ),
    )
