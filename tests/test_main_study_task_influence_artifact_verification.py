"""Adverse controls for independent, offline exploratory task-output verification.

All fixtures are synthetic; they never substitute for blinded human ratings.
"""
import copy
import hashlib
import json
import statistics

import pytest

from scripts import analyze_main_study_task_influence as producer
from scripts import verify_main_study_task_influence_artifact as verify


def _fixture():
    tasks = [f"synthetic-{i:02d}" for i in range(10)]
    values = [0.2, -0.1, 0.0, 0.3, -0.2, 0.1, -0.1, 0.0, 0.2, -0.1]
    inference = {
        "schema_version": 1, "study_id": "budget-main-v1",
        "n_tasks": 10, "task_ids": tasks,
        "primary_contrasts": {
            name: {"task_differences": list(values),
                   "mean_difference": statistics.mean(values)}
            for name in verify.CONTRASTS
        },
    }
    frozen = json.dumps(inference, sort_keys=True).encode()
    provenance = json.dumps({"verified_execution": {"synthetic_fixture": True}}).encode()
    report = producer.diagnostic(inference)
    report["verified_canonical_inference_sha256"] = hashlib.sha256(frozen).hexdigest()
    report["verified_provenance_receipt_sha256"] = hashlib.sha256(provenance).hexdigest()
    report["source_provenance_independently_recomputed"] = True
    return frozen, provenance, report


def _check(frozen, provenance, report):
    return verify.verify_bytes(
        frozen, provenance, json.dumps(report, sort_keys=True).encode()
    )


def test_all_thirty_omissions_recomputed_from_frozen_differences():
    frozen, provenance, report = _fixture()
    receipt = _check(frozen, provenance, report)
    assert receipt["status"] == "verified_post_hoc_exploratory_task_influence_only"
    assert receipt["contrasts_checked"] == 3
    assert receipt["paired_omission_rows_checked"] == 30
    assert receipt["task_influence_diagnostic_sha256"] == hashlib.sha256(
        json.dumps(report, sort_keys=True).encode()
    ).hexdigest()
    assert receipt["human_validation_performed"] is False


@pytest.mark.parametrize("mutation, error", [
    (lambda r: r["results"]["D6_minus_D3_retrieval_depth"][
        "all_task_omissions"].pop(), "enumerate every frozen task"),
    (lambda r: r["results"]["D6_minus_D3_retrieval_depth"][
        "all_task_omissions"][0].update(omitted_task_id="different"), "reordered"),
    (lambda r: r["results"]["D6_minus_D3_retrieval_depth"][
        "all_task_omissions"][0].update(remaining_pairs=True), "denominator"),
    (lambda r: r["results"]["D6_minus_D3_retrieval_depth"][
        "all_task_omissions"][0].update(mean_difference_without_task=0.9), "omission mean"),
    (lambda r: r["results"]["D6_minus_D3_retrieval_depth"][
        "all_task_omissions"][0].update(change_from_full_mean=0.9), "change from full"),
    (lambda r: r["results"]["D6_minus_D3_retrieval_depth"].update(
        loo_mean_min=-0.999), "min omission mean"),
    (lambda r: r["results"]["P6_minus_D6_planning"].update(
        full_sample_mean_difference=True), "finite JSON number"),
    (lambda r: r["results"].pop("P6V_minus_P6_verification"), "contrast coverage"),
    (lambda r: r.update(verified_canonical_inference_sha256="0"*64), "byte-bound"),
    (lambda r: r.update(verified_provenance_receipt_sha256="0"*64), "byte-bound"),
    (lambda r: r.update(human_validation_performed=1), "exploratory-only"),
    (lambda r: r.update(new_significance_claim=True), "exploratory-only"),
    (lambda r: r["task_ids"].reverse(), "task order"),
])
def test_corrupted_omission_or_claim_fails_closed(mutation, error):
    frozen, provenance, report = _fixture()
    mutation(report)
    with pytest.raises(ValueError, match=error):
        _check(frozen, provenance, report)


def test_input_mutation_is_not_accepted_with_old_receipt():
    frozen, provenance, report = _fixture()
    data = json.loads(frozen)
    data["primary_contrasts"]["P6V_minus_P6_verification"]["task_differences"][0] = 0.4
    changed = json.dumps(data, sort_keys=True).encode()
    with pytest.raises(ValueError, match="byte-bound"):
        _check(changed, provenance, report)


def test_missing_execution_binding_is_rejected_even_when_rehashed():
    frozen, _, report = _fixture()
    provenance = b"{}"
    report["verified_provenance_receipt_sha256"] = hashlib.sha256(provenance).hexdigest()
    with pytest.raises(ValueError, match="verified execution binding"):
        _check(frozen, provenance, report)


def test_duplicate_json_keys_and_nonfinite_numbers_fail_closed():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        verify._parse(b'{"x":1,"x":2}', "test")
    with pytest.raises(ValueError, match="non-JSON numeric"):
        verify._parse(b'{"x":NaN}', "test")
    with pytest.raises(ValueError, match="finite JSON number"):
        verify._number(True, "test")


def test_verification_is_read_only_and_deterministic():
    frozen, provenance, report = _fixture()
    original = copy.deepcopy(report)
    assert _check(frozen, provenance, report) == _check(frozen, provenance, report)
    assert report == original
