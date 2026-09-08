import json

import pytest

from logic.experiment import (
    ExperimentConfig,
    allocate_source_budgets,
    normalize_verifier_output,
    save_run_trace,
)


def test_initial_pilot_variants_are_explicit():
    direct = ExperimentConfig.from_variant("D6")
    planner = ExperimentConfig.from_variant("P6")
    verifier = ExperimentConfig.from_variant("P6V")

    assert direct.planning_mode == "direct"
    assert direct.source_budget == 6
    assert direct.verification_mode == "none"

    assert planner.planning_mode == "planner"
    assert planner.source_budget == 6
    assert planner.verification_mode == "none"

    assert verifier.planning_mode == "planner"
    assert verifier.source_budget == 6
    assert verifier.verification_mode == "verify"


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


def test_trace_is_persisted_under_variant_directory(tmp_path):
    config = ExperimentConfig(
        variant_id="D6",
        planning_mode="direct",
        source_budget=6,
        verification_mode="none",
        trace_root=str(tmp_path),
    )
    output_path = save_run_trace(
        trace={"completed": True, "source_count": 6},
        config=config,
        run_id="run-123",
    )

    payload = json.loads(open(output_path, encoding="utf-8").read())
    assert payload["schema_version"] == 1
    assert payload["experiment"]["variant_id"] == "D6"
    assert payload["trace"]["source_count"] == 6
