"""Synthetic anti-pseudoreplication checks for frozen human paired analysis.

These tests never load human ratings or treatment outcomes, and never revise
the frozen bootstrap procedure.
"""
import pytest

from scripts import human_eval_analysis_core as core


def test_direct_unlabelled_oversized_paired_vector_fails_before_bootstrap():
    with pytest.raises(ValueError, match="frozen ten-task analysis unit"):
        core._paired_summary([3] * 11, [4] * 11, seed=core.SEED)


def test_direct_labelled_oversized_paired_vector_fails():
    with pytest.raises(ValueError, match="frozen ten-task analysis unit"):
        core._paired_summary(
            [3] * 11, [4] * 11, seed=core.SEED,
            task_ids=(f"task-{i:02d}" for i in range(11)),
        )


@pytest.mark.parametrize(
    "ids",
    [
        ["task-01", "task-01"],
        ["task-01"],
        ["task-01", "task-02", "task-03"],
        ["task-01", ""],
        ["task-01", " task-02"],
        ["task-01", 2],
        ["task-01", None],
        "ab",
        42,
    ],
)
def test_direct_paired_summary_rejects_invalid_task_identity(ids):
    with pytest.raises(ValueError, match="paired task IDs"):
        core._paired_summary([2, 3], [3, 4], seed=core.SEED, task_ids=ids)


def test_direct_paired_summary_detects_late_duplicate_one_shot_task_ids():
    with pytest.raises(ValueError, match="uniquely identify"):
        core._paired_summary(
            [2, 3, 4], [3, 4, 5], seed=core.SEED,
            task_ids=(item for item in ("task-01", "task-02", "task-01")),
        )


def test_direct_paired_summary_preserves_valid_task_paired_statistics():
    left, right = [1.5, 2.0, 3.5], [2.5, 2.0, 4.0]
    unlabelled = core._paired_summary(left, right, seed=core.SEED)
    labelled = core._paired_summary(
        left, right, seed=core.SEED,
        task_ids=(item for item in ("task-01", "task-02", "task-03")),
    )
    assert labelled == unlabelled
    assert labelled["n_pairs"] == 3
    assert labelled["task_differences"] == [1.0, 0.0, 0.5]


def test_exact_frozen_ten_task_boundary_preserves_statistics():
    ids = [f"task-{i:02d}" for i in range(core.MAX_FROZEN_HUMAN_TASK_PAIRS)]
    result = core._paired_summary(
        [3] * len(ids), [3.5] * len(ids), seed=core.SEED, task_ids=ids,
    )
    assert result["n_pairs"] == 10
    assert result["mean_difference"] == 0.5
    assert result["bootstrap_95pct_ci_mean_difference"] == [0.5, 0.5]
