"""Synthetic-only adversarial checks of Pareto artifact independent verification."""
import copy
import hashlib
import json

import pytest

from scripts import analyze_main_study_pareto_influence as producer
from scripts import verify_main_study_pareto_artifact as checker
from test_main_study_pareto_influence import _fixture


def fixture():
    inference, main, support = _fixture()
    inference_raw = json.dumps(inference, sort_keys=True).encode()
    provenance_raw = json.dumps({
        "verified_execution": {"synthetic_fixture": True},
        "verified_inputs": [
            {"path": str(checker.MAIN), "sha256": hashlib.sha256(main).hexdigest()},
            {"path": str(checker.SUPPORT), "sha256": hashlib.sha256(support).hexdigest()},
        ],
    }, sort_keys=True).encode()
    report = producer.diagnostic(inference, main, support)
    report.update({
        "verified_canonical_inference_sha256": hashlib.sha256(inference_raw).hexdigest(),
        "verified_provenance_receipt_sha256": hashlib.sha256(provenance_raw).hexdigest(),
        "verified_input_sha256": {
            str(checker.MAIN): hashlib.sha256(main).hexdigest(),
            str(checker.SUPPORT): hashlib.sha256(support).hexdigest(),
        },
        "source_provenance_independently_recomputed": True,
    })
    return inference_raw, provenance_raw, main, support, report


def check(bundle):
    inference, provenance, main, support, report = bundle
    return checker.verify_bytes(
        inference, provenance, main, support, json.dumps(report, sort_keys=True).encode()
    )


def test_independent_full_recomputation_and_source_byte_binding():
    bundle = fixture()
    receipt = check(bundle)
    assert receipt["number_of_single_task_omissions"] == 10
    assert receipt["omissions_with_changed_frontier"] == 1
    assert receipt["human_validation_performed"] is False
    assert receipt["status"] == "independently_verified_post_hoc_exploratory_pareto_only"
    assert check(bundle) == receipt


@pytest.mark.parametrize("edit,diagnostic", [
    (lambda r: r["all_task_omissions"].pop(), "all ten"),
    (lambda r: r["all_task_omissions"][0].update(omitted_task_id="other"), "reordered"),
    (lambda r: r["all_task_omissions"][0].update(retained_task_count=True), "denominator"),
    (lambda r: r["all_task_omissions"][0]["variant_means"]["D3"].update(
        strict_support_rate=0.99), "source evidence"),
    (lambda r: r["all_task_omissions"][0].update(frontier=["D3"]), "frontier/dominance"),
    (lambda r: r["all_task_omissions"][0]["dominated_by"].update(D6=["D3"]),
     "frontier/dominance"),
    (lambda r: r["all_task_omissions"][0].update(
        frontier_differs_from_full_sample=False), "frontier-change flag"),
    (lambda r: r["frontier_membership_counts_of_ten_omissions"].update(D6=0),
     "membership totals"),
    (lambda r: r.update(omissions_with_changed_frontier=0), "changed-frontier"),
    (lambda r: r.update(verified_input_sha256={}), "source bytes"),
    (lambda r: r.update(source_provenance_independently_recomputed=1),
     "exploratory-only"),
    (lambda r: r.update(human_validation_performed=0), "exploratory-only"),
    (lambda r: r.update(new_inference=True), "exploratory-only"),
    (lambda r: r["full_sample_variant_means"]["D6"].update(treatment_cost_usd=True),
     "finite JSON number"),
])
def test_corruption_detected_without_cherry_picking(edit, diagnostic):
    bundle = list(fixture())
    bundle[-1] = copy.deepcopy(bundle[-1])
    edit(bundle[-1])
    with pytest.raises(ValueError, match=diagnostic):
        check(bundle)


def test_source_csv_replacement_fails_even_if_report_unmodified():
    bundle = list(fixture())
    bundle[2] += b"\n"
    with pytest.raises(ValueError, match="provenance input hashes"):
        check(bundle)


def test_rehashed_synthetic_provenance_without_verified_execution_fails():
    bundle = list(fixture())
    bundle[1] = json.dumps({"verified_inputs": [
        {"path": str(checker.MAIN), "sha256": hashlib.sha256(bundle[2]).hexdigest()},
        {"path": str(checker.SUPPORT), "sha256": hashlib.sha256(bundle[3]).hexdigest()},
    ]}).encode()
    bundle[-1]["verified_provenance_receipt_sha256"] = hashlib.sha256(bundle[1]).hexdigest()
    with pytest.raises(ValueError, match="execution binding"):
        check(bundle)


def test_duplicate_json_keys_nonfinite_and_boolean_numerics_rejected():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        checker.common._parse(b'{"k":1,"k":2}', "synthetic")
    with pytest.raises(ValueError, match="non-JSON numeric"):
        checker.common._parse(b'{"k":NaN}', "synthetic")
    with pytest.raises(ValueError, match="finite JSON number"):
        checker.number(True, "synthetic")
