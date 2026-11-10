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


@pytest.mark.parametrize(
    "ids",
    [
        {"main-01", "main-02"},
        frozenset({"main-01", "main-02"}),
        {"main-01": 1, "main-02": 2},
    ],
)
def test_direct_paired_summary_rejects_unordered_or_mapping_task_ids(ids):
    with pytest.raises(ValueError, match="paired task IDs must be an ordered iterable"):
        core._paired_summary([1, 2], [3, 4], seed=core.SEED, task_ids=ids)


def test_task_labelled_seeded_bootstrap_invariant_to_input_pair_permutation():
    # A positional seeded bootstrap is not invariant to input order for finite
    # draw counts. Task-label canonicalization must move BOTH scores together.
    ids = ["main-01", "main-02", "main-03", "main-04"]
    left = [1.0, 2.0, 2.5, 4.0]
    right = [3.0, 4.0, 3.5, 3.0]
    canonical = core._paired_summary(left, right, seed=core.SEED, task_ids=ids)
    assert canonical["task_differences"] == [2.0, 2.0, 1.0, -1.0]
    for indices in ([3, 2, 1, 0], [2, 0, 3, 1], [1, 3, 0, 2]):
        permuted = core._paired_summary(
            [left[i] for i in indices],
            [right[i] for i in indices],
            seed=core.SEED,
            task_ids=(ids[i] for i in indices),
        )
        assert permuted == canonical


def test_legacy_unlabelled_helper_preserves_original_positional_order():
    left, right = [1.0, 2.0, 2.5], [3.0, 3.0, 5.0]
    legacy = core._paired_summary(left, right, seed=core.SEED)
    assert legacy["task_differences"] == [2.0, 1.0, 2.5]
    assert legacy["n_pairs"] == 3
