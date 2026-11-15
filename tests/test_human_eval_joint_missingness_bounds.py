"""Synthetic-only regression tests for joint shared-arm missingness bounds."""
from __future__ import annotations

import hashlib
import json

import pytest

from scripts import audit_human_eval_joint_missingness_bounds as joint
from scripts import human_eval_analysis_core as core


TASKS = [f"main-{i:02d}" for i in range(1, 11)]


def _fixture(*, counts=None, differences=None):
    """Construct consistent per-report coverage shared by adjacent contrasts."""
    counts = counts or {}
    differences = differences or {}
    blocks = {}
    for left, right, name in core.CONTRASTS:
        left_right = {}
        for dimension in core.DIMS:
            per_cell = {cell: [] for cell in core.RATER_COVERAGE_CELLS}
            included, missing, deltas = [], [], {}
            for task in TASKS:
                left_n = counts.get(task, {}).get(left, 2)
                right_n = counts.get(task, {}).get(right, 2)
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
    return {
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
