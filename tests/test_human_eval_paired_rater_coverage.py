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
    # Keep this synthetic manuscript fixture self-contained; tests/ is not a
    # package on every Python test runner, and imports between test modules
    # must not be required for research-integrity regression coverage.
    tasks = ["task-a", "task-b"]
    summary = {
        "n_reports_total": 2,
        "n_reports_scored": 2,
        "n_raw_scores": 4,
        "mean_report_score": 3.0,
        "median_report_score": 3.0,
        "raw_score_distribution": {"1": 0, "2": 0, "3": 4, "4": 0, "5": 0},
    }
    coverage = {
        "count_by_rater_pair": {
            cell: 2 if cell == "2/2" else 0
            for cell in core.RATER_COVERAGE_CELLS
        },
        "task_ids_by_rater_pair": {
            cell: list(tasks) if cell == "2/2" else []
            for cell in core.RATER_COVERAGE_CELLS
        },
    }
    pair = {
        "n_pairs": 2,
        "left_mean": 2.5,
        "right_mean": 3.0,
        "mean_difference": 0.5,
        "median_difference": 0.5,
        "bootstrap_95pct_ci_mean_difference": [0.0, 1.0],
        "paired_dz": 0.707,
        "positive_tasks": 1,
        "negative_tasks": 0,
        "tied_tasks": 1,
        "task_differences": {"task-a": 1.0, "task-b": 0.0},
        "task_ids_included": list(tasks),
        "missing_pair_tasks": [],
        "rater_coverage": coverage,
    }
    agreement_dimension = {
        "n_double_rated": 8,
        "n_annotator_a_only_rated": 0,
        "n_annotator_b_only_rated": 0,
        "n_neither_rated": 0,
        "raw_exact_agreement": 0.75,
        "mean_absolute_difference": 0.25,
        "quadratic_weighted_cohen_kappa": 0.8,
    }
    return {
        "bootstrap_draws": core.BOOTSTRAP_DRAWS,
        "bootstrap_seed": core.SEED,
        "task_ids": tasks,
        "variant_summary": {
            variant: {field: dict(summary) for field in core.DIMS}
            for variant in core.VARIANTS
        },
        "paired_contrasts": {
            name: {field: copy.deepcopy(pair) for field in core.DIMS}
            for _, _, name in core.CONTRASTS
        },
        "pre_unblinding_agreement": {
            "status": "pre-unblinding_pairwise_agreement",
            "n_annotators": 2,
            "pairwise": [{
                "annotator_a": "annotator-a",
                "annotator_b": "annotator-b",
                "dimensions": {
                    field: dict(agreement_dimension) for field in core.DIMS
                },
            }],
        },
    }


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


def _move_synthetic_task_coverage(payload, contrast, field, task, new_cell):
    """Change one synthetic coverage bucket while retaining local validity."""
    tasks = payload["task_ids"]
    block = payload["paired_contrasts"][contrast][field]
    coverage = block["rater_coverage"]
    groups = coverage["task_ids_by_rater_pair"]
    assert sum(task in ids for ids in groups.values()) == 1
    assert new_cell in groups
    for ids in groups.values():
        if task in ids:
            ids.remove(task)
    groups[new_cell].append(task)
    for cell, ids in groups.items():
        ids.sort(key=tasks.index)
        coverage["count_by_rater_pair"][cell] = len(ids)
    included_cells = ("1/1", "1/2", "2/1", "2/2")
    included = [
        task_id for task_id in tasks
        if any(task_id in groups[cell] for cell in included_cells)
    ]
    block["task_ids_included"] = included
    block["missing_pair_tasks"] = [task_id for task_id in tasks if task_id not in included]
    block["n_pairs"] = len(included)
    return block


def test_one_rater_coverage_can_remain_included_under_frozen_rule():
    payload = _synthetic_payload()
    field = core.DIMS[0]
    block = _move_synthetic_task_coverage(
        payload, core.CONTRASTS[0][2], field, "task-b", "1/1"
    )
    # D6 is the right arm above and the left arm below: its original count
    # must remain one for this task in both predeclared comparisons.
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[1][2], field, "task-b", "1/2"
    )
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


@pytest.mark.parametrize(
    ("contrast_index", "contradictory_cell"),
    [
        (1, "1/2"),  # D6: two ratings in retrieval, one in planning.
        (1, "0/2"),  # D6: scored in retrieval, missing in planning.
        (2, "1/2"),  # P6: two ratings in planning, one in verification.
        (2, "0/2"),  # P6: scored in planning, missing in verification.
    ],
)
def test_rejects_inconsistent_original_rater_counts_for_shared_treatment(
    contrast_index, contradictory_cell
):
    payload = _synthetic_payload()
    contrast = core.CONTRASTS[contrast_index][2]
    _move_synthetic_task_coverage(
        payload, contrast, core.DIMS[0], "task-a", contradictory_cell
    )
    # Both contrast-local partitions and inclusion counts are sound. The
    # contradictory evidence is visible only after shared-arm reconciliation.
    with pytest.raises(ValueError, match="cross-contrast shared-arm mismatch"):
        verify._validate_paired_rater_coverage(payload)


def test_consistent_one_rater_shared_arm_remains_valid_without_imputation():
    payload = _synthetic_payload()
    field = core.DIMS[0]
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[0][2], field, "task-a", "2/1"
    )
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[1][2], field, "task-a", "1/2"
    )
    verify._validate_paired_rater_coverage(payload)
    assert payload["paired_contrasts"][core.CONTRASTS[0][2]][field]["n_pairs"] == 2
    assert payload["paired_contrasts"][core.CONTRASTS[1][2]][field]["n_pairs"] == 2


def test_consistent_zero_rater_shared_arm_excludes_only_affected_pairs():
    payload = _synthetic_payload()
    field = core.DIMS[0]
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[0][2], field, "task-a", "2/0"
    )
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[1][2], field, "task-a", "0/2"
    )
    verify._validate_paired_rater_coverage(payload)
    assert payload["paired_contrasts"][core.CONTRASTS[0][2]][field]["n_pairs"] == 1
    assert payload["paired_contrasts"][core.CONTRASTS[1][2]][field]["n_pairs"] == 1
    assert payload["paired_contrasts"][core.CONTRASTS[2][2]][field]["n_pairs"] == 2


def test_shared_arm_consistency_is_rubric_dimension_specific():
    payload = _synthetic_payload()
    field = core.DIMS[1]
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[1][2], field, "task-b", "2/1"
    )
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[2][2], field, "task-b", "1/2"
    )
    verify._validate_paired_rater_coverage(payload)
    assert payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]][
        "rater_coverage"
    ]["count_by_rater_pair"]["2/2"] == 2


def test_independent_end_arms_do_not_need_cross_contrast_duplication():
    payload = _synthetic_payload()
    field = core.DIMS[0]
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[0][2], field, "task-a", "1/2"
    )
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[2][2], field, "task-b", "2/1"
    )
    verify._validate_paired_rater_coverage(payload)


def test_analysis_preflight_rejects_conflicting_shared_arm_counts():
    payload = _synthetic_payload()
    # This focused synthetic fixture intentionally omits publication provenance,
    # but must satisfy the complete static identity contract before exercising
    # the cross-contrast preflight.
    payload.update(
        schema_version=1,
        study_id="budget-main-v1",
        status="human_validation_analysis",
        analysis_scope="complementary_not_main_confirmatory",
        human_ratings_generated=False,
        treatment_outputs_rerun=False,
        hypothesis_tests="none_predeclared_for_human_validation",
        report_score_aggregation="mean_observed_rater_scores_per_report_dimension",
        bootstrap_seed=core.SEED,
        bootstrap_draws=core.BOOTSTRAP_DRAWS,
        variants=list(core.VARIANTS),
        dimensions=list(core.DIMS),
    )
    _move_synthetic_task_coverage(
        payload, core.CONTRASTS[1][2], core.DIMS[0], "task-a", "1/2"
    )
    with pytest.raises(ValueError, match="cross-contrast shared-arm mismatch"):
        verify._validate_analysis_identity(payload)
