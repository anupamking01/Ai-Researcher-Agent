import json

import pytest

from logic.usage import UsageTracker
from logic.experiment import (
    ExperimentConfig,
    allocate_source_budgets,
    normalize_verifier_output,
    save_run_trace,
)
from logic.prompts import generate_verification_prompt
from scripts.summarize_pilot import _estimate_reported_token_cost


def test_predeclared_research_variants_are_explicit():
    direct_small = ExperimentConfig.from_variant("D3")
    direct = ExperimentConfig.from_variant("D6")
    planner = ExperimentConfig.from_variant("P6")
    verifier = ExperimentConfig.from_variant("P6V")

    assert direct_small.planning_mode == "direct"
    assert direct_small.source_budget == 3
    assert direct_small.verification_mode == "none"
    assert direct_small.stream_report is False

    assert direct.planning_mode == "direct"
    assert direct.source_budget == 6
    assert direct.verification_mode == "none"
    assert direct.stream_report is False

    assert planner.planning_mode == "planner"
    assert planner.source_budget == 6
    assert planner.verification_mode == "none"
    assert planner.stream_report is False

    assert verifier.planning_mode == "planner"
    assert verifier.source_budget == 6
    assert verifier.verification_mode == "verify"
    assert verifier.stream_report is False


def test_unknown_variant_is_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig.from_variant("P99")


def test_source_budget_is_distributed_without_exceeding_total():
    budgets = allocate_source_budgets(6, 4)
    assert budgets == [2, 2, 1, 1]
    assert sum(budgets) == 6


def test_source_budget_handles_more_queries_than_calls():
    budgets = allocate_source_budgets(3, 5)
    assert budgets == [1, 1, 1, 0, 0]
    assert sum(budgets) == 3


def test_verifier_output_is_normalized_and_recounted():
    raw = json.dumps(
        {
            "claims_checked": 999,
            "supported": 4,
            "partially_supported": 2,
            "unsupported": 1,
            "contradicted": 1,
            "examples": [{"claim": "x", "label": "supported"}] * 12,
        }
    )
    parsed = normalize_verifier_output(raw)

    assert parsed["claims_checked"] == 8
    assert parsed["supported"] == 4
    assert parsed["unsupported"] == 1
    assert parsed["contradicted"] == 1
    assert len(parsed["examples"]) == 8


def test_verifier_accepts_json_code_fence():
    raw = """```json
{"supported": 1, "partially_supported": 0, "unsupported": 0, "contradicted": 0, "examples": []}
```"""
    parsed = normalize_verifier_output(raw)
    assert parsed["claims_checked"] == 1


def test_posthoc_verifier_claim_cap_is_parameterized():
    prompt = generate_verification_prompt("q", "report", "evidence", max_claims=12)
    assert "up to 12 important atomic factual claims" in prompt
    with pytest.raises(ValueError):
        generate_verification_prompt("q", "report", "evidence", max_claims=0)


def test_usage_tracker_aggregates_provider_usage_by_model():
    tracker = UsageTracker()
    tracker.record_response(
        "model-a",
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
            }
        },
    )
    tracker.record_response(
        "model-a",
        {
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 10,
                "total_tokens": 60,
            }
        },
    )
    tracker.record_unavailable("model-b")

    usage = tracker.snapshot()
    assert usage["model_calls"] == 3
    assert usage["unavailable_calls"] == 1
    assert usage["prompt_tokens"] == 150
    assert usage["completion_tokens"] == 35
    assert usage["total_tokens"] == 185
    assert usage["by_model"]["model-a"]["model_calls"] == 2
    assert usage["by_model"]["model-b"]["unavailable_calls"] == 1


def test_frozen_cost_estimator_uses_exact_model_rates():
    pricing = {
        "models": {
            "smart": {"input": 2.0, "output": 12.0},
            "fast": {"input": 0.2, "output": 1.2},
        }
    }
    usage = {
        "smart": {"prompt_tokens": 1_000_000, "completion_tokens": 100_000},
        "fast": {"prompt_tokens": 500_000, "completion_tokens": 50_000},
    }
    cost, status = _estimate_reported_token_cost(usage, pricing)
    assert cost == pytest.approx(3.36)
    assert status == "estimated_from_frozen_uncached_rates"


def test_frozen_cost_estimator_rejects_unknown_model():
    cost, status = _estimate_reported_token_cost(
        {"unknown": {"prompt_tokens": 1, "completion_tokens": 1}},
        {"models": {}},
    )
    assert cost is None
    assert status == "unknown_model_price:unknown"


def test_trace_is_persisted_under_variant_directory(tmp_path):
    config = ExperimentConfig(
        variant_id="D6",
        planning_mode="direct",
        source_budget=6,
        verification_mode="none",
        trace_root=str(tmp_path),
        task_set_id="pilot-v1",
        task_id="pilot-01",
        stream_report=False,
    )
    output_path = save_run_trace(
        trace={"completed": True, "source_count": 6},
        config=config,
        run_id="run-123",
    )

    payload = json.loads(open(output_path, encoding="utf-8").read())
    assert payload["schema_version"] == 2
    assert payload["experiment"]["variant_id"] == "D6"
    assert payload["experiment"]["task_id"] == "pilot-01"
    assert payload["trace"]["source_count"] == 6
