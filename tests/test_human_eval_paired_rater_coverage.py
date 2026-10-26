"""Synthetic checks for treatment-pair original-rating denominator transparency.

All scores/counts are invented unit fixtures, never actual human ratings.
"""
import copy

import pytest

from scripts import analyze_human_eval
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verify


def scenario():
    categories = [(left, right) for left in (0, 1, 2) for right in (0, 1, 2)]
    tasks = [f"synthetic-task-{index}" for index in range(len(categories))]
    cells = {}
    counts = {}
    field = core.DIMS[0]
    for index, (left_count, right_count) in enumerate(categories):
        task = tasks[index]
        cells[("D3", task)] = f"blind-left-{index}"
        cells[("D6", task)] = f"blind-right-{index}"
        counts[(f"blind-left-{index}", field)] = left_count
        counts[(f"blind-right-{index}", field)] = right_count
    return counts, cells, tasks, field


def test_all_nine_two_rater_coverage_cells_partition_tasks():
    counts, cells, tasks, field = scenario()
    coverage = core._paired_rater_coverage(counts, cells, tasks, "D3", "D6", field)
    assert set(coverage["count_by_rater_pair"]) == set(core.RATER_COVERAGE_CELLS)
    assert all(value == 1 for value in coverage["count_by_rater_pair"].values())
    assert coverage["task_ids_by_rater_pair"]["1/1"] == ["synthetic-task-4"]
    assert coverage["task_ids_by_rater_pair"]["2/2"] == ["synthetic-task-8"]
    assert sum(coverage["count_by_rater_pair"].values()) == len(tasks)
    assert sum(coverage["count_by_rater_pair"][key] for key in ("1/1", "1/2", "2/1", "2/2")) == 4


def test_coverage_is_task_order_deterministic_without_effects_on_inputs():
    counts, cells, tasks, field = scenario()
    original_counts = counts.copy()
    original_cells = cells.copy()
    reversed_tasks = list(reversed(tasks))
    observed = core._paired_rater_coverage(counts, cells, reversed_tasks, "D3", "D6", field)
    expected = core._paired_rater_coverage(counts, cells, tasks, "D3", "D6", field)
    assert observed["count_by_rater_pair"] == expected["count_by_rater_pair"]
    assert counts == original_counts
    assert cells == original_cells


@pytest.mark.parametrize("invalid", [-1, 3, True, 1.5, None, "2", float("nan")])
def test_coverage_rejects_invalid_original_rater_count(invalid):
    counts, cells, tasks, field = scenario()
    counts[(cells[("D3", tasks[0])], field)] = invalid
    with pytest.raises(ValueError, match="0, 1, or 2"):
        core._paired_rater_coverage(counts, cells, tasks, "D3", "D6", field)


def test_coverage_rejects_missing_original_count():
    counts, cells, tasks, field = scenario()
    del counts[(cells[("D3", tasks[0])], field)]
    with pytest.raises(ValueError, match="missing a report/score count"):
        core._paired_rater_coverage(counts, cells, tasks, "D3", "D6", field)


def test_coverage_rejects_duplicate_task_keys():
    counts, cells, tasks, field = scenario()
    with pytest.raises(ValueError, match="unique nonempty"):
        core._paired_rater_coverage(counts, cells, [tasks[0], tasks[0]], "D3", "D6", field)


def test_coverage_rejects_empty_task_matrix():
    counts, cells, _, field = scenario()
    with pytest.raises(ValueError, match="at least one"):
        core._paired_rater_coverage(counts, cells, [], "D3", "D6", field)


def _synthetic_payload():
    from tests.test_human_eval_analysis_output_verification import _payload
    return _payload()


def test_manuscript_displays_rater_coverage_without_changing_paired_estimate():
    payload = _synthetic_payload()
    original_estimate = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]["mean_difference"]
    markdown = analyze_human_eval.render_markdown(payload)
    assert "## Original-rater coverage underlying paired scores" in markdown
    assert "| D6_minus_D3_retrieval_depth | correctness_1_5 | 2 | 0 | 0 | 0 | 0 | 2/2:task-a, task-b |" in markdown
    assert original_estimate == 0.5
    assert "A/B means the **left/right" in markdown


@pytest.mark.parametrize("mutation", ["bad_count", "duplicate_task", "omitted_task", "false_inclusion", "bad_category"])
def test_identity_gate_rejects_misleading_coverage_claim(mutation):
    payload = _synthetic_payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    coverage = block["rater_coverage"]
    if mutation == "bad_count":
        coverage["count_by_rater_pair"]["2/2"] = 1
    elif mutation == "duplicate_task":
        coverage["task_ids_by_rater_pair"]["1/1"] = ["task-a"]
        coverage["count_by_rater_pair"]["1/1"] = 1
    elif mutation == "omitted_task":
        coverage["task_ids_by_rater_pair"]["2/2"] = ["task-a"]
        coverage["count_by_rater_pair"]["2/2"] = 1
    elif mutation == "false_inclusion":
        block["task_ids_included"] = ["task-a"]
    else:
        coverage["task_ids_by_rater_pair"]["3/3"] = []
        coverage["count_by_rater_pair"]["3/3"] = 0
    with pytest.raises(ValueError, match="analysis rater coverage"):
        verify._validate_paired_rater_coverage(payload)


def test_one_rater_coverage_can_remain_included_under_frozen_rule():
    payload = _synthetic_payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    coverage = block["rater_coverage"]
    coverage["task_ids_by_rater_pair"]["2/2"] = ["task-a"]
    coverage["count_by_rater_pair"]["2/2"] = 1
    coverage["task_ids_by_rater_pair"]["1/1"] = ["task-b"]
    coverage["count_by_rater_pair"]["1/1"] = 1
    verify._validate_paired_rater_coverage(payload)
    assert block["n_pairs"] == 2
    assert block["mean_difference"] == 0.5


def test_zero_rating_side_cannot_be_claimed_as_paired():
    payload = _synthetic_payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    coverage = block["rater_coverage"]
    coverage["task_ids_by_rater_pair"]["2/2"] = ["task-a"]
    coverage["count_by_rater_pair"]["2/2"] = 1
    coverage["task_ids_by_rater_pair"]["0/1"] = ["task-b"]
    coverage["count_by_rater_pair"]["0/1"] = 1
    with pytest.raises(ValueError, match="paired denominator mismatch"):
        verify._validate_paired_rater_coverage(payload)
