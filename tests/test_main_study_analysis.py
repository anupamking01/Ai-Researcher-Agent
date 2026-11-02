"""Regression tests for the preregistered main-study statistical helpers."""

import pytest

from scripts.analyze_main_study import (
    _exact_signflip_pvalue,
    _holm_adjust,
    _paired_summary,
    _percentile,
)


def test_percentile_interpolates_and_handles_singleton():
    assert _percentile([2.0], 0.25) == 2.0
    assert _percentile([0.0, 10.0], 0.25) == pytest.approx(2.5)


def test_percentile_rejects_empty_input():
    with pytest.raises(ValueError, match="percentile requires values"):
        _percentile([], 0.5)


def test_exact_signflip_pvalue_known_two_pair_case():
    # For [1, 2], two of four sign assignments have an absolute mean at
    # least as large as the observed mean, so the exact two-sided p is 0.5.
    assert _exact_signflip_pvalue([1.0, 2.0]) == pytest.approx(0.5)


def test_holm_adjust_is_monotone_and_order_independent():
    adjusted = _holm_adjust([("largest", 0.04), ("smallest", 0.01), ("middle", 0.03)])
    assert adjusted == pytest.approx(
        {"smallest": 0.03, "middle": 0.06, "largest": 0.06}
    )


def test_paired_summary_reports_direction_and_is_seed_reproducible(monkeypatch):
    # Keep the regression test fast while exercising the same seeded path.
    monkeypatch.setattr("scripts.analyze_main_study.BOOTSTRAP_DRAWS", 500)
    left = [0.2, 0.4, 0.8]
    right = [0.4, 0.4, 0.6]

    first = _paired_summary(left, right, seed=17, exact_p=True)
    second = _paired_summary(left, right, seed=17, exact_p=True)

    assert first == second
    assert first["n_pairs"] == 3
    assert first["mean_difference"] == pytest.approx(0.0)
    assert first["median_difference"] == pytest.approx(0.0)
    assert first["positive_tasks"] == 1
    assert first["negative_tasks"] == 1
    assert first["tied_tasks"] == 1
    assert first["task_differences"] == pytest.approx([0.2, 0.0, -0.2])
    assert 0.0 <= first["exact_two_sided_signflip_p"] <= 1.0
    low, high = first["bootstrap_95pct_ci_mean_difference"]
    assert low <= first["mean_difference"] <= high


def test_paired_summary_rejects_unpaired_or_empty_vectors():
    with pytest.raises(ValueError, match="non-empty and equal length"):
        _paired_summary([], [], seed=1, exact_p=False)
    with pytest.raises(ValueError, match="non-empty and equal length"):
        _paired_summary([1.0], [1.0, 2.0], seed=1, exact_p=False)


# All matrices below are fabricated solely for offline contract regression.
# They are not experimental treatments or evaluator results.
import csv

from scripts import analyze_main_study as analysis


def _write_synthetic_matrix(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def synthetic_matrix(tmp_path, monkeypatch):
    treatment, evaluator = [], []
    for variant in analysis.VARIANTS:
        for ordinal in range(1, 11):
            task = f"synthetic-{ordinal:02d}"
            treatment.append({
                "variant_id": variant, "task_id": task, "completed": "True",
                "source_budget": "3" if variant == "D3" else "6",
                "successful_sources": "2", "failed_sources": "1",
                "total_tokens": "160", "treatment_cost_usd": "0.2",
                "latency_seconds": "12.5", "model_calls": "2",
                "report_words": "15",
            })
            evaluator.append({
                "variant_id": variant, "task_id": task,
                "claims_checked": "8", "supported": "6",
                "partially_supported": "1", "unsupported": "1",
                "contradicted": "0", "evidence_status": "",
            })
    treatment_path = tmp_path / "treatment.csv"
    evaluator_path = tmp_path / "evaluator.csv"
    monkeypatch.setattr(analysis, "MAIN_CSV", treatment_path)
    monkeypatch.setattr(analysis, "SUPPORT_CSV", evaluator_path)

    def write():
        _write_synthetic_matrix(treatment_path, treatment)
        _write_synthetic_matrix(evaluator_path, evaluator)

    write()
    return treatment, evaluator, write


def test_complete_synthetic_numeric_matrix_preserves_frozen_analysis(synthetic_matrix):
    _, _, _ = synthetic_matrix
    joined, tasks = analysis._build_dataset()
    assert len(joined) == 40
    assert len(tasks) == 10
    assert joined[("D3", "synthetic-01")]["strict_support_rate"] == 0.75
    assert type(joined[("D3", "synthetic-01")]["total_tokens"]) is float
    assert analysis._int({"claims_checked": "8.0"}, "claims_checked") == 8


@pytest.mark.parametrize("value", [
    "2.5", "0.99999999999999999", "8.0000000000000000001",
    "nan", "inf", "-inf", "1e309", "9007199254740993", "oops",
])
def test_frozen_count_parser_rejects_rounded_or_nonfinite_claims(value):
    with pytest.raises(SystemExit, match="(whole number|finite|Invalid numeric|too large)"):
        analysis._int({"claims_checked": value}, "claims_checked")


@pytest.mark.parametrize("field,value,expected_error", [
    ("claims_checked", "13", "outside frozen cap"),
    ("supported", "6.5", "whole number"),
    ("supported", "-1", "category count"),
    ("supported", "9", "category count"),
    ("contradicted", "-1", "category count"),
])
def test_synthetic_evaluator_counts_fail_closed(
    synthetic_matrix, field, value, expected_error
):
    _, evaluator, write = synthetic_matrix
    evaluator[0][field] = value
    # A negative supported count can still be made to sum to eight;
    # that apparent partition must never pass the category-domain guard.
    if field == "supported" and value == "-1":
        evaluator[0]["unsupported"] = "8"
    write()
    with pytest.raises(SystemExit, match=expected_error):
        analysis._build_dataset()


@pytest.mark.parametrize("field,value,expected_error", [
    ("treatment_cost_usd", "nan", "finite"),
    ("latency_seconds", "inf", "finite"),
    ("total_tokens", "1e309", "finite"),
    ("report_words", "1.5", "whole number"),
    ("model_calls", "-1", "Negative treatment count"),
    ("treatment_cost_usd", "-0.01", "Negative treatment cost"),
    ("source_budget", "6", "retrieval budget drift"),
    ("successful_sources", "4", "source counts exceed budget"),
])
def test_synthetic_treatment_measurements_fail_closed(
    synthetic_matrix, field, value, expected_error
):
    treatment, _, write = synthetic_matrix
    treatment[0][field] = value
    write()
    with pytest.raises(SystemExit, match=expected_error):
        analysis._build_dataset()


@pytest.mark.parametrize("text,expected_error", [
    ("variant_id,task_id,variant_id\nD3,synthetic-01,D6\n", "Duplicate CSV headers"),
    ("variant_id,task_id\nD3,synthetic-01,extra\n", "Missing or extra CSV cells"),
    ("variant_id,task_id\nD3\n", "Missing or extra CSV cells"),
])
def test_inference_csv_parser_rejects_ambiguous_columns(tmp_path, text, expected_error):
    path = tmp_path / "unsafe.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit, match=expected_error):
        analysis._read_csv(path)
