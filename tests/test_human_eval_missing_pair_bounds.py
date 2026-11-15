"""Synthetic-only regressions for ancillary human missing-pair bounds."""
from __future__ import annotations

import hashlib
import json

import pytest

from scripts import audit_human_eval_missing_pair_bounds as audit
from scripts import human_eval_analysis_core as core


def _analysis(*, included=10, observed_difference=0.5):
    tasks = [f"main-{i:02d}" for i in range(1, 11)]
    retained, absent = tasks[:included], tasks[included:]
    return {
        "study_id": "budget-main-v1",
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "n_tasks": 10,
        "task_ids": tasks,
        "dimensions": list(core.DIMS),
        "paired_contrasts": {
            name: {
                dim: {
                    "task_ids_included": list(retained),
                    "missing_pair_tasks": list(absent),
                    "task_differences": {task: observed_difference for task in retained},
                    "n_pairs": included,
                    "mean_difference": observed_difference if included else None,
                }
                for dim in core.DIMS
            }
            for _, _, name in core.CONTRASTS
        },
    }


def _cell(result, name="D6_minus_D3_retrieval_depth", dim=None):
    return result["bounds_by_contrast_and_dimension"][name][dim or core.DIMS[0]]


def test_complete_synthetic_pairs_collapse_to_original_observed_mean():
    result = audit.audit_missing_pair_bounds(_analysis())
    assert _cell(result)["worst_case_all_task_mean_difference"] == [0.5, 0.5]
    assert _cell(result)["bound_collapses_to_observed_mean"] is True
    assert set(result["bounds_by_contrast_and_dimension"]) == {
        name for _, _, name in core.CONTRASTS
    }
    assert all(
        set(by_dim) == set(core.DIMS)
        for by_dim in result["bounds_by_contrast_and_dimension"].values()
    )


def test_two_missing_tasks_can_reverse_direction_without_changing_observed_mean():
    result = audit.audit_missing_pair_bounds(_analysis(included=8))
    cell = _cell(result)
    assert cell["observed_difference_sum"] == 4.0
    assert cell["missing_pair_count"] == 2
    assert cell["worst_case_all_task_mean_difference"] == [-0.4, 1.2]
    assert cell["missing_pair_tasks"] == ["main-09", "main-10"]
    assert result["not_a_confidence_interval"] is True
    assert result["ratings_generated"] is False


def test_no_task_pairs_have_full_rubric_difference_bounds():
    result = audit.audit_missing_pair_bounds(_analysis(included=0))
    assert _cell(result)["worst_case_all_task_mean_difference"] == [-4.0, 4.0]


def test_negative_half_point_and_extreme_differences_retain_exact_arithmetic():
    payload = _analysis(included=9, observed_difference=-0.5)
    payload["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["task_differences"]["main-01"] = -4.0
    payload["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["mean_difference"] = -8.0 / 9
    cell = _cell(audit.audit_missing_pair_bounds(payload))
    assert cell["observed_difference_sum"] == -8.0
    assert cell["worst_case_all_task_mean_difference"] == [-1.2, -0.4]


@pytest.mark.parametrize("mutation", [
    lambda x: x["task_ids"].append("main-11"),
    lambda x: x["paired_contrasts"].pop("P6V_minus_P6_verification"),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"].pop(core.DIMS[0]),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["missing_pair_tasks"].append("main-01"),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["task_differences"].update({"main-11": 1.0}),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]].update(n_pairs=True),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]].update(mean_difference=0.0),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["task_differences"].update({"main-01": 0.25}),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["task_differences"].update({"main-01": float("nan")}),
    lambda x: x["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["task_differences"].update({"main-01": 4.5}),
])
def test_fail_closed_on_inconsistent_or_unrepresentable_evidence(mutation):
    payload = _analysis(included=9)
    mutation(payload)
    with pytest.raises(ValueError):
        audit.audit_missing_pair_bounds(payload)


def test_unchanged_observed_difference_can_have_different_missingness_bounds():
    complete = _cell(audit.audit_missing_pair_bounds(_analysis(included=10)))
    partial = _cell(audit.audit_missing_pair_bounds(_analysis(included=8)))
    assert complete["worst_case_all_task_mean_difference"] == [0.5, 0.5]
    assert partial["worst_case_all_task_mean_difference"] != [0.5, 0.5]


def test_cli_gate_requires_independent_recomputation_before_read(monkeypatch, tmp_path):
    called = []
    def reject(*args, **kwargs):
        called.append("verify")
        raise ValueError("independent recomputation unavailable")
    monkeypatch.setattr(audit.verifier, "verify_bundle_against_inputs", reject)
    monkeypatch.setattr(audit.freeze, "_capture_regular_input", lambda *a, **k: called.append("read"))
    with pytest.raises(ValueError, match="independent recomputation unavailable"):
        audit.audit_verified_bundle(tmp_path)
    assert called == ["verify"]


def test_cli_gate_rejects_bytes_changed_after_independent_verification(monkeypatch, tmp_path):
    original = b'{"study_id":"budget-main-v1"}'
    tampered = b'{"study_id":"unrelated"}'
    monkeypatch.setattr(
        audit.verifier, "verify_bundle_against_inputs",
        lambda *a, **k: {
            "independent_recomputation_verified": True,
            "canonical_analysis_sha256": hashlib.sha256(original).hexdigest(),
        },
    )
    monkeypatch.setattr(
        audit.freeze, "_capture_regular_input", lambda *a, **k: tampered,
    )
    with pytest.raises(ValueError, match="changed before missingness audit"):
        audit.audit_verified_bundle(tmp_path)


def test_verified_byte_identity_uses_pure_bound_helper(monkeypatch, tmp_path):
    source = json.dumps(_analysis(included=8)).encode("utf-8")
    monkeypatch.setattr(
        audit.verifier, "verify_bundle_against_inputs",
        lambda *a, **k: {
            "independent_recomputation_verified": True,
            "canonical_analysis_sha256": hashlib.sha256(source).hexdigest(),
        },
    )
    monkeypatch.setattr(audit.freeze, "_capture_regular_input", lambda *a, **k: source)
    result = audit.audit_verified_bundle(tmp_path)
    assert _cell(result)["worst_case_all_task_mean_difference"] == [-0.4, 1.2]
    assert result["verified_source"]["independent_recomputation_verified"] is True
