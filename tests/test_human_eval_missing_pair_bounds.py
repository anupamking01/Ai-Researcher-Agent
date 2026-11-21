"""Synthetic-only regressions for ancillary human missing-pair bounds."""
from __future__ import annotations

import hashlib
import json
from itertools import product

import pytest

from scripts import audit_human_eval_missing_pair_bounds as audit
from scripts import human_eval_analysis_core as core


def _coverage(tasks, retained):
    by_cell = {cell: [] for cell in core.RATER_COVERAGE_CELLS}
    by_cell["2/2"] = list(retained)
    by_cell["0/2"] = [task for task in tasks if task not in retained]
    return {
        "count_by_rater_pair": {cell: len(ids) for cell, ids in by_cell.items()},
        "task_ids_by_rater_pair": by_cell,
    }


def _assign_cell(payload, task_id, new_cell, *, dimension=None):
    """Synthetic fixture: move exactly one task between coverage cells."""
    block = payload["paired_contrasts"]["D6_minus_D3_retrieval_depth"][dimension or core.DIMS[0]]
    coverage = block["rater_coverage"]
    for ids in coverage["task_ids_by_rater_pair"].values():
        if task_id in ids:
            ids.remove(task_id)
    coverage["task_ids_by_rater_pair"][new_cell].append(task_id)
    for cell, ids in coverage["task_ids_by_rater_pair"].items():
        ids.sort()
        coverage["count_by_rater_pair"][cell] = len(ids)


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
                    "rater_coverage": _coverage(tasks, retained),
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



def test_partial_original_rater_coverage_expands_only_completion_envelope():
    payload = _analysis()
    _assign_cell(payload, "main-01", "1/2")
    cell = _cell(audit.audit_missing_pair_bounds(payload))
    assert cell["missing_pair_count"] == 0
    assert cell["worst_case_all_task_mean_difference"] == [0.5, 0.5]
    assert cell["unobserved_second_rater_slots_on_included_pairs"] == 1
    assert cell["hypothetical_two_rater_completion_bounds"] == [0.3, 0.7]
    assert cell["completion_bounds_collapse_to_observed_mean"] is False


def test_double_rated_and_missing_pair_envelopes_agree_when_no_partial_raters():
    result = audit.audit_missing_pair_bounds(_analysis(included=8))
    cell = _cell(result)
    assert cell["unobserved_second_rater_slots_on_included_pairs"] == 0
    assert cell["hypothetical_two_rater_completion_bounds"] == [-0.4, 1.2]
    assert result["hypothetical_two_rater_completion_is_exploratory_only"] is True


def test_partially_rated_pair_still_respects_global_rubric_difference_range():
    payload = _analysis(included=10, observed_difference=4.0)
    _assign_cell(payload, "main-01", "1/1")
    cell = _cell(audit.audit_missing_pair_bounds(payload))
    assert cell["unobserved_second_rater_slots_on_included_pairs"] == 2
    assert cell["hypothetical_two_rater_completion_bounds"] == [3.6, 4.0]


@pytest.mark.parametrize("mutation", [
    lambda p: p["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]].pop("rater_coverage"),
    lambda p: p["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["rater_coverage"]["count_by_rater_pair"].update({"2/2": 8}),
    lambda p: _assign_cell(p, "main-01", "0/2"),
    lambda p: _assign_cell(p, "main-10", "2/2"),
    lambda p: p["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["rater_coverage"]["task_ids_by_rater_pair"]["2/2"].append("main-01"),
    lambda p: p["paired_contrasts"]["D6_minus_D3_retrieval_depth"][core.DIMS[0]]["rater_coverage"]["count_by_rater_pair"].update({"2/2": True}),
])
def test_fail_closed_on_invalid_original_rater_partition(mutation):
    payload = _analysis(included=9)
    mutation(payload)
    with pytest.raises(ValueError, match="rater|coverage|inclusion"):
        audit.audit_missing_pair_bounds(payload)


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


def test_coverage_conditioned_completion_sharpens_conservative_envelope():
    payload = _analysis(observed_difference=1.0)
    _assign_cell(payload, "main-01", "1/1")
    cell = _cell(audit.audit_missing_pair_bounds(payload))
    assert cell["worst_case_all_task_mean_difference"] == [1.0, 1.0]
    assert cell["hypothetical_two_rater_completion_bounds"] == [0.6, 1.3]
    assert cell["coverage_conditioned_two_rater_completion_bounds"] == [0.75, 1.15]


def test_coverage_conditioned_bounds_preserve_complete_and_missing_pair_cases():
    complete = _cell(audit.audit_missing_pair_bounds(_analysis()))
    absent = _cell(audit.audit_missing_pair_bounds(_analysis(included=8)))
    assert complete["coverage_conditioned_two_rater_completion_bounds"] == [0.5, 0.5]
    assert absent["coverage_conditioned_two_rater_completion_bounds"] == [-0.4, 1.2]


def test_impossible_halfpoint_difference_for_two_single_raters_fails_closed():
    payload = _analysis(observed_difference=0.5)
    _assign_cell(payload, "main-01", "1/1")
    with pytest.raises(ValueError, match="incompatible with original-rater coverage"):
        audit.audit_missing_pair_bounds(payload)


@pytest.mark.parametrize(("left_count", "right_count"), [
    (1, 1), (1, 2), (2, 1), (2, 2),
])
def test_score_sum_endpoints_match_independent_four_rating_oracle(
    left_count, right_count,
):
    """Synthetic exhaustive oracle enumerates four integer scores, not sums."""
    expected = {}
    for left in product(range(1, 6), repeat=2):
        for right in product(range(1, 6), repeat=2):
            left_observed = sum(left[:left_count])
            right_observed = sum(right[:right_count])
            numerator = 2 * (
                right_observed * left_count - left_observed * right_count
            )
            denominator = left_count * right_count
            assert numerator % denominator == 0
            observed_twice = numerator // denominator
            completed_twice = sum(right) - sum(left)
            expected.setdefault(observed_twice, []).append(completed_twice)

    for observed_twice in range(-8, 9):
        if observed_twice in expected:
            assert audit._attainable_completion_twice(
                observed_twice, left_count=left_count, right_count=right_count,
            ) == (
                min(expected[observed_twice]), max(expected[observed_twice])
            )
        else:
            with pytest.raises(ValueError, match="incompatible"):
                audit._attainable_completion_twice(
                    observed_twice, left_count=left_count, right_count=right_count,
                )
