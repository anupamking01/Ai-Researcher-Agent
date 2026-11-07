"""Regression tests for the frozen human-validation statistical implementation.

These tests use synthetic numeric vectors only. They are not collected human
ratings and do not change or inspect treatment outcomes.
"""
import pytest

from scripts import analyze_main_study as main_stats
from scripts import human_eval_analysis_core as core


def test_human_eval_owns_frozen_bootstrap_configuration():
    assert core.SEED == 20260925
    assert core.BOOTSTRAP_DRAWS == 20_000


def test_constant_paired_effect_has_exact_frozen_summary():
    result = core._paired_summary(
        [1.0, 2.0, 3.0],
        [2.0, 3.0, 4.0],
        seed=core.SEED,
    )

    assert result["n_pairs"] == 3
    assert result["left_mean"] == 2.0
    assert result["right_mean"] == 3.0
    assert result["mean_difference"] == 1.0
    assert result["median_difference"] == 1.0
    assert result["bootstrap_95pct_ci_mean_difference"] == [1.0, 1.0]
    assert result["paired_dz"] is None
    assert result["positive_tasks"] == 3
    assert result["negative_tasks"] == 0
    assert result["tied_tasks"] == 0
    assert result["task_differences"] == [1.0, 1.0, 1.0]
    assert "exact_two_sided_signflip_p" not in result


def test_human_summary_is_deterministic_and_independent_of_main_study_helpers(monkeypatch):
    left = [1.0, 2.0, 4.0, 3.0]
    right = [2.0, 2.0, 3.0, 5.0]

    expected = core._paired_summary(left, right, seed=core.SEED + 7)

    monkeypatch.setattr(main_stats, "BOOTSTRAP_DRAWS", 1)
    monkeypatch.setattr(
        main_stats,
        "_paired_summary",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("human analysis called mutable main-study inference code")
        ),
    )

    observed = core._paired_summary(left, right, seed=core.SEED + 7)
    assert observed == expected
    assert observed["task_differences"] == [1.0, 0.0, -1.0, 2.0]
    assert observed["positive_tasks"] == 2
    assert observed["negative_tasks"] == 1
    assert observed["tied_tasks"] == 1


@pytest.mark.parametrize(
    "left,right",
    [
        ([], []),
        ([1.0], []),
        ([1.0, 2.0], [1.0]),
    ],
)
def test_human_paired_summary_rejects_invalid_pair_vectors(left, right):
    with pytest.raises(ValueError, match="paired vectors must be non-empty and equal length"):
        core._paired_summary(left, right, seed=core.SEED)
