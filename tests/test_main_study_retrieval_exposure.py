"""Offline synthetic regression tests for realized retrieval exposure audit."""
from __future__ import annotations

import copy

import pytest

from scripts import analyze_main_study_retrieval_exposure as diagnostic


def _matrix():
    rows = []
    for variant in ("D3", "D6", "P6", "P6V"):
        for ordinal in range(1, 11):
            budget = 3 if variant == "D3" else 6
            successes = {"D3": 2, "D6": 3, "P6": 4, "P6V": 3}[variant]
            failures = {"D3": 1, "D6": 2, "P6": 2, "P6V": 3}[variant]
            rows.append({
                "variant_id": variant,
                "task_id": f"synthetic-{ordinal:02d}",
                "completed": "True",
                "source_budget": str(budget),
                "successful_sources": str(successes),
                "failed_sources": str(failures),
                "search_calls": str(1 if variant in ("D3", "D6") else 4),
                "model_calls": "6",
                "total_tokens": "1000",
                "posthoc_strict_support_rate": "0.0",
            })
    return rows


def test_reports_all_forty_exposures_and_all_frozen_contrasts():
    summary = diagnostic.summarize_retrieval_exposure(_matrix())
    assert summary["status"] == "post_hoc_exploratory_retrieval_exposure_only"
    assert not summary["confirmatory_inference_changed"]
    assert not summary["statistical_tests_added"]
    assert not summary["human_validation_performed"]
    assert not summary["original_execution_authenticated"]
    assert len(summary["task_ids"]) == 10
    assert set(summary["variant_summaries"]) == {"D3", "D6", "P6", "P6V"}
    assert set(summary["frozen_contrast_exposure_comparisons"]) == {
        name for _, _, name in diagnostic.CONTRASTS
    }
    for arm in summary["variant_summaries"].values():
        assert len(arm["all_task_exposures"]) == 10


def test_scheduled_budget_not_equated_with_realized_successes():
    summary = diagnostic.summarize_retrieval_exposure(_matrix())
    d6 = summary["variant_summaries"]["D6"]
    assert d6["totals"]["scheduled_slots"] == 60
    assert d6["totals"]["successful_sources"] == 30
    assert d6["totals"]["failed_sources"] == 20
    assert d6["totals"]["capacity_not_accounted_for_by_source_results"] == 10
    assert d6["recorded_successful_sources_per_scheduled_slot"] == 0.5
    assert d6["accounted_source_results_per_scheduled_slot"] == pytest.approx(5 / 6)
    contrast = summary["frozen_contrast_exposure_comparisons"][
        "D6_minus_D3_retrieval_depth"
    ]
    assert contrast["scheduled_slot_delta_per_task"] == 3
    assert contrast["mean_successful_source_delta"] == 1
    assert contrast["more_successful_sources_right"] == 10
    assert {row["scheduled_slot_delta"] for row in contrast["all_task_exposure_differences"]} == {3}


def test_no_budget_difference_can_still_have_realized_source_difference():
    contrasts = diagnostic.summarize_retrieval_exposure(_matrix())[
        "frozen_contrast_exposure_comparisons"
    ]
    planning = contrasts["P6_minus_D6_planning"]
    verification = contrasts["P6V_minus_P6_verification"]
    assert planning["scheduled_slot_delta_per_task"] == 0
    assert planning["mean_successful_source_delta"] == 1
    assert planning["all_task_exposure_differences"][0]["search_call_delta"] == 3
    assert verification["scheduled_slot_delta_per_task"] == 0
    assert verification["mean_successful_source_delta"] == -1
    assert verification["fewer_successful_sources_right"] == 10


def test_an_outcome_edit_does_not_change_exposure_descriptives():
    rows = _matrix()
    baseline = diagnostic.summarize_retrieval_exposure(rows)
    for row in rows:
        row["posthoc_strict_support_rate"] = "1.0"
    assert diagnostic.summarize_retrieval_exposure(rows) == baseline


def test_shuffled_input_order_does_not_change_receipt_or_mutate_rows():
    rows = _matrix()
    original = copy.deepcopy(rows)
    first = diagnostic.summarize_retrieval_exposure(rows)
    assert rows == original
    assert diagnostic.summarize_retrieval_exposure(list(reversed(rows))) == first


@pytest.mark.parametrize("field,value", [
    ("source_budget", "9"),
    ("successful_sources", "-1"),
    ("failed_sources", "-1"),
    ("successful_sources", "2.5"),
    ("search_calls", "NaN"),
    ("model_calls", "-1"),
    ("total_tokens", "Infinity"),
])
def test_invalid_resources_rejected(field, value):
    rows = _matrix()
    rows[0][field] = value
    with pytest.raises(ValueError):
        diagnostic.summarize_retrieval_exposure(rows)


def test_exceeding_scheduled_budget_fails_closed():
    rows = _matrix()
    rows[0]["failed_sources"] = "2"
    with pytest.raises(ValueError, match="exceed scheduled budget"):
        diagnostic.summarize_retrieval_exposure(rows)


def test_incomplete_treatment_cannot_enter_exposure_receipt():
    rows = _matrix()
    rows[0]["completed"] = "False"
    with pytest.raises(ValueError, match="not completed"):
        diagnostic.summarize_retrieval_exposure(rows)


def test_missing_or_duplicate_paired_cells_are_rejected():
    rows = _matrix()
    rows[0]["task_id"] = rows[1]["task_id"]
    with pytest.raises(ValueError, match="duplicate"):
        diagnostic.summarize_retrieval_exposure(rows)


def test_uneven_task_sets_are_rejected_even_with_forty_rows():
    rows = _matrix()
    rows[0]["task_id"] = "synthetic-other"
    with pytest.raises(ValueError, match="identical task sets"):
        diagnostic.summarize_retrieval_exposure(rows)


def test_zero_success_is_retained_and_reported_not_dropped():
    rows = _matrix()
    rows[0]["successful_sources"] = "0"
    rows[0]["failed_sources"] = "2"
    result = diagnostic.summarize_retrieval_exposure(rows)
    assert result["variant_summaries"]["D3"]["reports_with_zero_successful_sources"] == 1
    assert result["variant_summaries"]["D3"]["reports_with_capacity_not_accounted_for"] == 1
    assert result["variant_summaries"]["D3"]["n_reports"] == 10


def test_published_source_preflight_and_exact_fingerprint_smoke():
    from scripts import audit_frozen_analysis_csv_inputs as audit

    summary = diagnostic.run_verified()
    assert summary["published_summary_preflight_passed"] is True
    assert summary["verified_published_treatment_csv_sha256"] == (
        audit.FROZEN_MAIN_CSV_SHA256
    )
    assert summary["published_input_aggregate_sha256_reference"] == (
        audit.PUBLISHED_INPUT_AGGREGATE_SHA256
    )
    assert summary["task_ids"] == [
        f"main-{index:02d}" for index in range(1, 11)
    ]
    assert all(
        sum(v["totals"][field] for field in (
            "accounted_source_results", "capacity_not_accounted_for_by_source_results"
        )) == v["totals"]["scheduled_slots"]
        for v in summary["variant_summaries"].values()
    )
