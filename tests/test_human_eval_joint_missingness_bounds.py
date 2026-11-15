"""Synthetic-only regression tests for joint shared-arm missingness bounds."""
from __future__ import annotations

import hashlib
import json
from itertools import product

import pytest

from scripts import audit_human_eval_joint_missingness_bounds as joint
from scripts import human_eval_analysis_core as core


TASKS = [f"main-{i:02d}" for i in range(1, 11)]


def _fixture(*, counts=None, differences=None, per_dimension_counts=None):
    """Construct consistent per-report coverage shared by adjacent contrasts."""
    counts = counts or {}
    differences = differences or {}
    per_dimension_counts = per_dimension_counts or {}

    def rater_count(task, arm, dimension):
        return per_dimension_counts.get(
            (dimension, task, arm), counts.get(task, {}).get(arm, 2)
        )

    blocks = {}
    for left, right, name in core.CONTRASTS:
        left_right = {}
        for dimension in core.DIMS:
            per_cell = {cell: [] for cell in core.RATER_COVERAGE_CELLS}
            included, missing, deltas = [], [], {}
            for task in TASKS:
                left_n = rater_count(task, left, dimension)
                right_n = rater_count(task, right, dimension)
                per_cell[f"{left_n}/{right_n}"].append(task)
                if left_n and right_n:
                    included.append(task)
                    deltas[task] = differences.get((task, name), 0)
                else:
                    missing.append(task)
            left_right[dimension] = {
                "task_ids_included": included,
                "missing_pair_tasks": missing,
                "task_differences": deltas,
                "n_pairs": len(included),
                "mean_difference": (
                    sum(deltas.values()) / len(included) if included else None
                ),
                "rater_coverage": {
                    "count_by_rater_pair": {
                        cell: len(ids) for cell, ids in per_cell.items()
                    },
                    "task_ids_by_rater_pair": per_cell,
                },
            }
        blocks[name] = left_right
    # Synthetic score assignments make the histogram consistent with observed
    # differences, not merely the expected number of raw ratings.
    arm_order = ("D3", "D6", "P6", "P6V")
    possible_scores = (3, 1, 5, 2, 4)
    synthetic_scores = {}
    for dimension in core.DIMS:
        for task in TASKS:
            for candidate in product(possible_scores, repeat=4):
                values = dict(zip(arm_order, candidate))
                if all(
                    not (rater_count(task, left, dimension)
                         and rater_count(task, right, dimension))
                    or values[right] - values[left] == differences.get((task, name), 0)
                    for left, right, name in core.CONTRASTS
                ):
                    break
            else:
                # Deliberately impossible paired-input fixtures must reach the
                # existing shared-arm contradiction guard before this gate.
                values = {arm: 3 for arm in arm_order}
            for arm in arm_order:
                synthetic_scores[(dimension, task, arm)] = values[arm]
    variant_summary = {}
    for arm in ("D3", "D6", "P6", "P6V"):
        variant_summary[arm] = {}
        for dimension in core.DIMS:
            counts_for_arm = [rater_count(task, arm, dimension) for task in TASKS]
            total = sum(counts_for_arm)
            variant_summary[arm][dimension] = {
                "n_reports_total": len(TASKS),
                "n_reports_scored": sum(n > 0 for n in counts_for_arm),
                "n_raw_scores": total,
                "mean_report_score": (
                    sum(
                        synthetic_scores[(dimension, task, arm)]
                        for task in TASKS if rater_count(task, arm, dimension)
                    ) / sum(n > 0 for n in counts_for_arm)
                    if any(counts_for_arm) else None
                ),
                "raw_score_distribution": {
                    str(score): sum(
                        rater_count(task, arm, dimension)
                        for task in TASKS
                        if synthetic_scores[(dimension, task, arm)] == score
                    )
                    for score in range(1, 6)
                },
            }
    return {
        "variant_summary": variant_summary,
        "study_id": "budget-main-v1",
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "n_tasks": 10,
        "task_ids": TASKS,
        "dimensions": list(core.DIMS),
        "paired_contrasts": blocks,
    }


def _cell(result, name="D6_minus_D3_retrieval_depth"):
    return result["bounds_by_contrast_and_dimension"][name][core.DIMS[0]]


def test_complete_synthetic_matrix_has_equal_frozen_and_joint_bounds():
    result = joint.audit_joint_shared_arm_bounds(_fixture())
    assert _cell(result)["shared_arm_conditioned_all_task_bounds"] == [0, 0]
    assert _cell(result)["missing_task_difference_bounds"] == {}
    assert result["no_imputation_or_new_ratings"] is True
    assert all(
        set(result["bounds_by_contrast_and_dimension"][name]) == set(core.DIMS)
        for _, _, name in core.CONTRASTS
    )


def test_shared_extreme_planning_edge_tightens_missing_retrieval_pair():
    payload = _fixture(
        counts={"main-01": {"D3": 0}},
        differences={("main-01", "P6_minus_D6_planning"): 4},
    )
    cell = _cell(joint.audit_joint_shared_arm_bounds(payload))
    assert cell["prior_rubric_only_all_task_bounds"] == [-0.4, 0.4]
    assert cell["shared_arm_conditioned_all_task_bounds"] == [-0.4, 0]
    assert cell["missing_task_difference_bounds"] == {"main-01": [-4, 0]}


def test_noninformative_neighbors_preserve_original_missing_pair_range():
    cell = _cell(joint.audit_joint_shared_arm_bounds(
        _fixture(counts={"main-01": {"D3": 0}})
    ))
    assert cell["shared_arm_conditioned_all_task_bounds"] == [-0.4, 0.4]


def test_all_unobserved_reports_leave_full_rubric_bounds():
    counts = {task: {"D3": 0, "D6": 0, "P6": 0, "P6V": 0} for task in TASKS}
    result = joint.audit_joint_shared_arm_bounds(_fixture(counts=counts))
    assert _cell(result)["shared_arm_conditioned_all_task_bounds"] == [-4, 4]
    assert _cell(result)["observed_paired_tasks"] == 0


def test_individually_feasible_differences_can_be_jointly_impossible():
    payload = _fixture(differences={
        ("main-01", "D6_minus_D3_retrieval_depth"): 4,
        ("main-01", "P6_minus_D6_planning"): 4,
    })
    with pytest.raises(ValueError, match="cross-contrast observed differences"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_contradictory_shared_arm_original_rater_counts_are_rejected():
    payload = _fixture()
    block = payload["paired_contrasts"]["P6_minus_D6_planning"][core.DIMS[0]]
    cells = block["rater_coverage"]["task_ids_by_rater_pair"]
    cells["2/2"].remove("main-01")
    cells["1/2"].append("main-01")
    block["rater_coverage"]["count_by_rater_pair"]["2/2"] -= 1
    block["rater_coverage"]["count_by_rater_pair"]["1/2"] += 1
    with pytest.raises(ValueError, match="cross-contrast shared-arm"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_verified_cli_refuses_unverified_human_analysis_before_read(monkeypatch, tmp_path):
    reads = []
    def refuse(*args, **kwargs):
        reads.append("verify")
        raise ValueError("no independently verified human ratings")
    monkeypatch.setattr(joint.verifier, "verify_bundle_against_inputs", refuse)
    monkeypatch.setattr(joint.freeze, "_capture_regular_input", lambda *a, **k: reads.append("read"))
    with pytest.raises(ValueError, match="no independently verified"):
        joint.audit_verified_bundle(tmp_path)
    assert reads == ["verify"]


def test_verified_cli_rejects_modified_analysis_bytes(monkeypatch, tmp_path):
    before = json.dumps(_fixture()).encode()
    after = before + b" "
    monkeypatch.setattr(joint.verifier, "verify_bundle_against_inputs", lambda *a, **k: {
        "independent_recomputation_verified": True,
        "canonical_analysis_sha256": hashlib.sha256(before).hexdigest(),
    })
    monkeypatch.setattr(joint.freeze, "_capture_regular_input", lambda *a, **k: after)
    with pytest.raises(ValueError, match="changed before joint missingness audit"):
        joint.audit_verified_bundle(tmp_path)


def test_verified_cli_uses_byte_identical_synthetic_analysis(monkeypatch, tmp_path):
    source = json.dumps(_fixture(counts={"main-01": {"D3": 0}})).encode()
    monkeypatch.setattr(joint.verifier, "verify_bundle_against_inputs", lambda *a, **k: {
        "independent_recomputation_verified": True,
        "canonical_analysis_sha256": hashlib.sha256(source).hexdigest(),
    })
    monkeypatch.setattr(joint.freeze, "_capture_regular_input", lambda *a, **k: source)
    result = joint.audit_verified_bundle(tmp_path)
    assert _cell(result)["shared_arm_conditioned_all_task_bounds"] == [-0.4, 0.4]
    assert result["verified_source"]["independent_recomputation_verified"] is True


def test_joint_completion_exposes_partial_rater_uncertainty_hidden_by_fixed_edges():
    # D3 is unobserved, D6 and P6 are singly rated, and their original
    # planning difference is +4. The shared observed scores force D6=1,
    # P6=5, but an unobserved D6 second score may reach 5. The new
    # *counterfactual completion* envelope must not be mislabeled as the
    # original fixed-observation envelope.
    payload = _fixture(
        counts={"main-01": {"D3": 0, "D6": 1, "P6": 1}},
        differences={("main-01", "P6_minus_D6_planning"): 4},
    )
    cell = _cell(joint.audit_joint_shared_arm_bounds(payload))
    assert cell["shared_arm_conditioned_all_task_bounds"] == [-0.4, 0]
    assert cell["hypothetical_shared_arm_two_rater_all_task_bounds"] == [-0.4, 0.2]
    assert cell["incomplete_original_rater_tasks"] == ["main-01"]
    assert cell["hypothetical_completed_task_difference_bounds"] == {
        "main-01": [-4, 2]
    }


def test_completed_planning_difference_respects_rater_lattice():
    payload = _fixture(
        counts={"main-01": {"D6": 1, "P6": 1}},
        differences={("main-01", "P6_minus_D6_planning"): 4},
    )
    result = joint.audit_joint_shared_arm_bounds(payload)
    cell = result["bounds_by_contrast_and_dimension"][
        "P6_minus_D6_planning"
    ][core.DIMS[0]]
    assert cell["shared_arm_conditioned_all_task_bounds"] == [0.4, 0.4]
    assert cell["hypothetical_shared_arm_two_rater_all_task_bounds"] == [0, 0.4]
    assert result["hypothetical_full_two_rater_completion_is_exploratory_only"]


def test_full_double_rating_completion_does_not_change_any_edge():
    result = joint.audit_joint_shared_arm_bounds(_fixture())
    for _, _, name in core.CONTRASTS:
        for dimension in core.DIMS:
            block = result["bounds_by_contrast_and_dimension"][name][dimension]
            assert block["hypothetical_shared_arm_two_rater_all_task_bounds"] == [0, 0]
            assert block["incomplete_original_rater_tasks"] == []
            assert block["hypothetical_completed_task_difference_bounds"] == {}


def test_joint_completion_rejects_cross_arm_impossible_observed_differences():
    payload = _fixture(differences={
        ("main-01", "D6_minus_D3_retrieval_depth"): 4,
        ("main-01", "P6_minus_D6_planning"): 4,
    })
    with pytest.raises(ValueError, match="cross-contrast observed differences"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_joint_bounds_reconcile_per_arm_summary_denominators():
    payload = _fixture(counts={"main-01": {"D3": 0, "D6": 1}})
    result = joint.audit_joint_shared_arm_bounds(payload)
    assert _cell(result)["missing_pair_tasks"] == ["main-01"]


@pytest.mark.parametrize("field,mutation", [
    ("n_reports_total", 9),
    ("n_reports_scored", 10),
    ("n_raw_scores", 19),
])
def test_joint_bounds_reject_contradictory_variant_summary_counts(field, mutation):
    payload = _fixture(counts={"main-01": {"D3": 0}})
    payload["variant_summary"]["D3"][core.DIMS[0]][field] = mutation
    with pytest.raises(ValueError, match="published arm denominators disagree"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_joint_bounds_reject_wrong_histogram_total_and_invalid_counter_type():
    payload = _fixture()
    payload["variant_summary"]["P6"][core.DIMS[0]]["raw_score_distribution"]["1"] += 1
    with pytest.raises(ValueError, match="published arm denominators disagree"):
        joint.audit_joint_shared_arm_bounds(payload)

    payload = _fixture()
    payload["variant_summary"]["P6"][core.DIMS[0]]["raw_score_distribution"]["1"] = True
    with pytest.raises(ValueError, match="invalid raw-score distribution"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_joint_bounds_require_all_arm_summaries_and_dimensions():
    payload = _fixture()
    del payload["variant_summary"]["P6V"]
    with pytest.raises(ValueError, match="every frozen variant summary"):
        joint.audit_joint_shared_arm_bounds(payload)

    payload = _fixture()
    del payload["variant_summary"]["D6"][core.DIMS[-1]]
    with pytest.raises(ValueError, match="incomplete frozen variant summary"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_joint_bounds_allow_legitimate_dimension_specific_rater_missingness():
    # Each rubric field may have its own observed-rater count. There is no
    # cross-dimension equality requirement; only the same report across
    # adjacent contrasts must have consistent counts within a dimension.
    payload = _fixture(per_dimension_counts={
        (core.DIMS[-1], "main-01", "D6"): 1,
    })
    result = joint.audit_joint_shared_arm_bounds(payload)
    first = result["bounds_by_contrast_and_dimension"][
        "P6_minus_D6_planning"
    ]
    assert first[core.DIMS[0]]["incomplete_original_rater_tasks"] == []
    assert first[core.DIMS[-1]]["incomplete_original_rater_tasks"] == ["main-01"]



def test_histogram_rejects_correct_denominator_but_incompatible_score_bins():
    payload = _fixture(differences={
        ("main-01", "P6_minus_D6_planning"): 4,
    })
    bins = payload["variant_summary"]["D6"][core.DIMS[0]]["raw_score_distribution"]
    assert bins["1"] == 2
    bins["1"] -= 2
    bins["3"] += 2  # Preserve the number of ratings; lose required score 1.
    with pytest.raises(ValueError, match="published score histogram cannot match"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_histogram_accepts_feasible_extreme_observed_difference():
    result = joint.audit_joint_shared_arm_bounds(_fixture(differences={
        ("main-01", "P6_minus_D6_planning"): 4,
    }))
    assert result["raw_histogram_feasibility_is_necessary_not_sufficient"] is True


def test_histogram_accepts_distinct_raw_scores_with_unchanged_mean():
    payload = _fixture()
    bins = payload["variant_summary"]["D6"][core.DIMS[0]]["raw_score_distribution"]
    bins["3"] -= 2
    bins["1"] += 1
    bins["5"] += 1  # A 1+5 report has mean 3, just like 3+3.
    assert _cell(joint.audit_joint_shared_arm_bounds(payload))[
        "shared_arm_conditioned_all_task_bounds"
    ] == [0, 0]


def test_histogram_rejects_insufficient_required_score_multiplicity():
    payload = _fixture(differences={
        ("main-01", "P6_minus_D6_planning"): 4,
        ("main-02", "P6_minus_D6_planning"): 4,
    })
    bins = payload["variant_summary"]["D6"][core.DIMS[0]]["raw_score_distribution"]
    assert bins["1"] == 4
    bins["1"] -= 2
    bins["3"] += 2
    with pytest.raises(ValueError, match="published score histogram cannot match"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_histogram_handles_halfpoint_two_rater_report_mean():
    payload = _fixture()
    dim = core.DIMS[0]
    block = payload["paired_contrasts"]["D6_minus_D3_retrieval_depth"][dim]
    block["task_differences"]["main-01"] = 0.5
    block["mean_difference"] = 0.05
    for arm in ("D6", "P6", "P6V"):
        bins = payload["variant_summary"][arm][dim]["raw_score_distribution"]
        bins["3"] -= 1
        bins["4"] += 1
        payload["variant_summary"][arm][dim]["mean_report_score"] += 0.05
    joint.audit_joint_shared_arm_bounds(payload)

def test_cross_arm_histogram_totals_reject_mismatched_all_task_means():
    # Every adjacent paired difference is zero. Each arm's raw histogram
    # separately admits feasible task scores, but D6's aggregate score sum
    # is too high to match D3's unchanged raw histogram.
    payload = _fixture()
    dim = core.DIMS[0]
    bins = payload["variant_summary"]["D6"][dim]["raw_score_distribution"]
    bins["3"] -= 2
    bins["4"] += 2
    arms = ["D3", "D6", "P6", "P6V"]
    counts = {arm: [2] * len(TASKS) for arm in arms}
    score_domains = {
        arm: [set(range(2, 11)) for _ in TASKS] for arm in arms
    }
    # The previous arm-by-arm guard accepts this contradiction.
    joint._validate_published_score_histograms(
        payload, arms, dim, counts, score_domains,
    )
    with pytest.raises(ValueError, match="cross-arm raw-score histogram totals"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_cross_arm_histogram_total_rejects_partial_rater_contradiction():
    # With one original score on the same task for D3 and D6, the raw
    # singleton identity is unknown. Even after allowing either assignment,
    # changing one D6 3 to a 4 cannot produce a zero all-task difference.
    payload = _fixture(counts={"main-01": {"D3": 1, "D6": 1}})
    bins = payload["variant_summary"]["D6"][core.DIMS[0]]["raw_score_distribution"]
    bins["3"] -= 1
    bins["4"] += 1
    with pytest.raises(ValueError, match="cross-arm raw-score histogram totals"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_cross_arm_aggregate_accepts_feasible_mixed_rater_histogram():
    # D6's original singly rated report can remain 3, while another
    # two-rated report scores 2+4 instead of 3+3. Both mean 3; the frozen
    # zero differences and all published aggregate bins remain attainable.
    payload = _fixture(counts={"main-01": {"D3": 1, "D6": 1}})
    bins = payload["variant_summary"]["D6"][core.DIMS[0]]["raw_score_distribution"]
    bins["3"] -= 2
    bins["2"] += 1
    bins["4"] += 1
    result = joint.audit_joint_shared_arm_bounds(payload)
    assert result["cross_arm_histogram_aggregates_are_necessary_not_sufficient"]
    assert _cell(result)["shared_arm_conditioned_all_task_bounds"] == [0, 0]


def test_cross_arm_aggregate_missing_reports_keep_conservative_range():
    # With the entire original D3 report missing, its hypothetical 1..5
    # report mean must remain available; the guard must not assume zero.
    payload = _fixture(counts={"main-01": {"D3": 0}})
    result = joint.audit_joint_shared_arm_bounds(payload)
    assert _cell(result)["shared_arm_conditioned_all_task_bounds"] == [-0.4, 0.4]



def test_published_report_mean_rejects_double_rated_histogram_disagreement():
    # With 2/2 ratings everywhere, the report-score mean is fixed by the
    # histogram's weighted total, independent of raw rating pair allocation.
    payload = _fixture()
    payload["variant_summary"]["D6"][core.DIMS[0]]["mean_report_score"] = 3.05
    with pytest.raises(ValueError, match="published report mean cannot arise"):
        joint.audit_joint_shared_arm_bounds(payload)


@pytest.mark.parametrize("invalid", [None, True, float("nan"), float("inf")])
def test_published_report_mean_rejects_invalid_observed_summary(invalid):
    payload = _fixture()
    payload["variant_summary"]["P6"][core.DIMS[0]]["mean_report_score"] = invalid
    with pytest.raises(ValueError, match="invalid published report mean"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_published_report_mean_rejects_impossible_singleton_lattice():
    # With one single-rated report and 19 raw ratings all equal to 3,
    # there is only one possible singleton subtotal: 3. An intermediate
    # reported mean of 3.05 is impossible despite lying within [1,5].
    payload = _fixture(counts={"main-01": {"D3": 1}})
    payload["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = 3.05
    with pytest.raises(ValueError, match="published report mean cannot arise"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_published_report_mean_requires_null_for_unscored_arm():
    payload = _fixture(counts={
        task: {"D3": 0} for task in TASKS
    })
    assert joint.audit_joint_shared_arm_bounds(payload)[
        "published_report_mean_feasibility_is_necessary_not_sufficient"
    ] is True
    payload["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = 3
    with pytest.raises(ValueError, match="requires scored reports"):
        joint.audit_joint_shared_arm_bounds(payload)


def test_published_report_mean_accepts_valid_partial_rater_summary():
    payload = _fixture(counts={"main-01": {"D3": 1, "D6": 1}})
    result = joint.audit_joint_shared_arm_bounds(payload)
    assert result["published_report_mean_feasibility_is_necessary_not_sufficient"]
