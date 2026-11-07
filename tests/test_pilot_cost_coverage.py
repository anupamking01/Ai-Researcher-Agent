"""Synthetic regression tests for diagnostic-pilot cost missingness denominators.

These tests do not call models, rerun treatments, or change frozen pilot data.
"""
import pytest

from scripts import summarize_pilot as pilot


def row(variant, task, cost, status=None):
    return {
        "variant_id": variant,
        "task_set_id": "synthetic-pilot",
        "task_id": task,
        "run_id": f"{variant}-{task}",
        "completed": True,
        "source_count": 2,
        "successful_source_count": 1,
        "failed_source_count": 1,
        "search_call_count": 1,
        "model_call_count": 2,
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
        "latency_seconds": 2.0,
        "report_words": 10,
        "claims_checked": 0,
        "claim_support_rate": 0.0,
        "usage_accounting_status": "provider_usage_complete",
        "estimated_cost_usd": cost,
        "cost_accounting_status": (
            status or ("estimated_from_frozen_uncached_rates" if cost is not None
                       else "missing_usage_by_model")
        ),
    }


def test_variant_coverage_exposes_uncosted_denominator_and_tasks():
    rows = [
        row("D6", "task-1", 0.01),
        row("D6", "task-2", None, "unknown_model_price:provider-x"),
        row("D6", "task-3", None, "missing_usage_by_model"),
    ]
    summary = pilot._variant_summary(rows)["D6"]
    assert summary["n_runs"] == 3
    assert summary["costed_runs"] == 1
    assert summary["uncosted_runs"] == 2
    assert summary["uncosted_task_ids"] == ["task-2", "task-3"]
    assert summary["avg_estimated_cost_usd"] == pytest.approx(0.01)
    assert summary["cost_accounting_status_counts"] == {
        "estimated_from_frozen_uncached_rates": 1,
        "missing_usage_by_model": 1,
        "unknown_model_price:provider-x": 1,
    }


def test_completely_uncosted_variant_does_not_get_zero_mean():
    summary = pilot._variant_summary([row("P6V", "task-1", None)])["P6V"]
    assert summary["n_runs"] == summary["uncosted_runs"] == 1
    assert summary["costed_runs"] == 0
    assert summary["avg_estimated_cost_usd"] is None


def test_empty_arm_has_zero_coverage_not_invented_price():
    summary = pilot._variant_summary([])["D6"]
    assert summary["n_runs"] == summary["costed_runs"] == 0
    assert summary["uncosted_runs"] == 0
    assert summary["cost_accounting_status_counts"] == {}
    assert summary["avg_estimated_cost_usd"] is None


def test_paired_cost_uses_only_explicitly_costed_shared_tasks():
    rows = [
        row("D6", "task-1", 0.10), row("P6", "task-1", 0.20),
        row("D6", "task-2", 0.10),
        row("P6", "task-2", None, "unknown_model_price:unpriced"),
        row("D6", "task-3", None, "missing_usage_by_model"),
        row("P6", "task-3", 0.80),
    ]
    comparison = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert comparison["n_tasks_union"] == comparison["n_pairs"] == 3
    assert comparison["n_costed_pairs"] == 1
    assert comparison["n_uncosted_pairs"] == 2
    assert comparison["costed_pair_task_ids"] == ["task-1"]
    assert comparison["avg_estimated_cost_usd_delta"] == pytest.approx(0.10)
    assert comparison["uncosted_pair_details"] == [
        {
            "task_id": "task-2",
            "left_cost_status": "costed",
            "right_cost_status": "unknown_model_price:unpriced",
        },
        {
            "task_id": "task-3",
            "left_cost_status": "missing_usage_by_model",
            "right_cost_status": "costed",
        },
    ]
    assert [item["estimated_cost_usd_delta"] for item in comparison["pairs"]] == [
        pytest.approx(0.10), None, None
    ]


def test_both_sides_uncosted_have_both_reasons():
    rows = [
        row("D6", "task-1", None, "unknown_model_price:a"),
        row("P6", "task-1", None, "missing_usage_by_model"),
    ]
    result = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert result["n_pairs"] == result["n_uncosted_pairs"] == 1
    assert result["n_costed_pairs"] == 0
    assert result["avg_estimated_cost_usd_delta"] is None
    assert result["uncosted_pair_details"] == [{
        "task_id": "task-1",
        "left_cost_status": "unknown_model_price:a",
        "right_cost_status": "missing_usage_by_model",
    }]


def test_zero_reported_cost_is_costed_not_missing():
    rows = [row("D6", "task-1", 0.0), row("P6", "task-1", 0.0)]
    result = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert result["n_costed_pairs"] == 1
    assert result["n_uncosted_pairs"] == 0
    assert result["uncosted_pair_details"] == []
    assert result["avg_estimated_cost_usd_delta"] == 0.0


def test_unmatched_tasks_are_distinct_from_unknown_costs():
    rows = [
        row("D6", "task-1", 0.1),
        row("P6", "task-2", None, "unknown_model_price:p6"),
    ]
    result = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert result["n_tasks_union"] == 2
    assert result["n_pairs"] == 0
    assert result["n_costed_pairs"] == result["n_uncosted_pairs"] == 0
    assert result["missing_left_task_ids"] == ["task-2"]
    assert result["missing_right_task_ids"] == ["task-1"]
    assert result["uncosted_pair_details"] == []
    assert result["avg_estimated_cost_usd_delta"] is None


def test_full_costed_coverage_does_not_change_existing_mean():
    rows = [
        row("D6", "task-1", 0.1), row("P6", "task-1", 0.2),
        row("D6", "task-2", 0.2), row("P6", "task-2", 0.4),
    ]
    result = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert result["n_pairs"] == result["n_costed_pairs"] == 2
    assert result["n_uncosted_pairs"] == 0
    assert result["avg_estimated_cost_usd_delta"] == pytest.approx(0.15)


def test_cost_coverage_deterministic_under_input_order():
    rows = [
        row("D6", "task-2", None), row("P6", "task-1", 0.2),
        row("D6", "task-1", 0.1), row("P6", "task-2", 0.3),
    ]
    forward = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    reverse = pilot._paired_operational_differences(list(reversed(rows)))["P6_minus_D6"]
    assert forward == reverse


def test_cost_status_defaults_to_unspecified_for_legacy_rows():
    rows = [row("D6", "task-1", None), row("P6", "task-1", 0.1)]
    rows[0].pop("cost_accounting_status")
    result = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert result["uncosted_pair_details"][0]["left_cost_status"] == "unspecified"
    summary = pilot._variant_summary(rows)["D6"]
    assert summary["cost_accounting_status_counts"] == {"unspecified": 1}
