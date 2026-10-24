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
