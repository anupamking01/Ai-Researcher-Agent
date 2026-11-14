"""Offline arithmetic cross-check of original, frozen primary VERA inference.

Tests only inspect already-preserved CSV/JSON artifacts or altered temporary
copies; they never rerun treatments, call providers, or generate human scores.
"""
import copy
import json

import pytest

from scripts.audit_primary_inference_independently import (
    ROOT, audit_files, audit_primary,
    _exact_signflip, _bootstrap_percentile_interval,
)
from fractions import Fraction
from scripts.validate_main_study_inputs import read_csv_rows


@pytest.fixture
def evidence():
    treatment = read_csv_rows(ROOT / "outputs/main_study_runs.csv")
    evaluator = read_csv_rows(ROOT / "outputs/posthoc_support_runs.csv")
    payload = json.loads((ROOT / "outputs/main_study_inference.json").read_text())
    return treatment, evaluator, payload


def test_independent_math_matches_retained_frozen_primary_inference(evidence):
    main, evaluator, results = evidence
    audited = audit_primary(main, evaluator, results)
    assert audited["paired_tasks"] == 10
    assert audited["primary_contrasts_checked"] == 3
    assert audited["bootstrap_intervals_checked"] is True



@pytest.mark.parametrize("contrast", [
    "D6_minus_D3_retrieval_depth",
    "P6_minus_D6_planning",
    "P6V_minus_P6_verification",
])
@pytest.mark.parametrize("endpoint", [0, 1])
def test_rejects_manipulated_primary_bootstrap_endpoint(
    evidence, contrast, endpoint,
):
    main, evaluator, payload = evidence
    modified = copy.deepcopy(payload)
    modified["primary_contrasts"][contrast][
        "bootstrap_95pct_ci_mean_difference"
    ][endpoint] += 0.05
    with pytest.raises(ValueError, match="bootstrap_95pct_ci_mean_difference"):
        audit_primary(main, evaluator, modified)


@pytest.mark.parametrize("invalid", [
    [],
    [0.1],
    [0.1, 0.2, 0.3],
    [True, 0.2],
    ["0.1", 0.2],
    [float("nan"), 0.2],
    [0.1, float("inf")],
])
def test_rejects_malformed_primary_bootstrap_interval(evidence, invalid):
    main, evaluator, payload = evidence
    payload["primary_contrasts"]["D6_minus_D3_retrieval_depth"][
        "bootstrap_95pct_ci_mean_difference"
    ] = invalid
    with pytest.raises(ValueError, match="bootstrap_95pct_ci_mean_difference"):
        audit_primary(main, evaluator, payload)


def test_independent_bootstrap_preserves_constant_fraction_and_seed():
    constant = [Fraction(1, 3)] * 10
    assert _bootstrap_percentile_interval(
        constant, seed=20260914, draws=41,
    ) == (Fraction(1, 3), Fraction(1, 3))
    mixed = [Fraction(-1, 4), Fraction(1, 2)] * 5
    assert _bootstrap_percentile_interval(
        mixed, seed=20260914, draws=101,
    ) == _bootstrap_percentile_interval(mixed, seed=20260914, draws=101)


def test_read_only_cli_inputs_match_frozen_primary_inference():
    result = audit_files(
        ROOT / "outputs/main_study_runs.csv",
        ROOT / "outputs/posthoc_support_runs.csv",
        ROOT / "outputs/main_study_inference.json",
    )
    assert result["status"].endswith("not_provenance")


@pytest.mark.parametrize("field,new_value", [
    ("mean_difference", 0.99),
    ("median_difference", 0.99),
    ("exact_two_sided_signflip_p", 0.123456),
    ("holm_adjusted_p", 0.123456),
    ("left_mean", 0.123456),
    ("right_mean", 0.123456),
    ("positive_tasks", 99),
    ("n_pairs", 9),
    ("paired_dz", 0.99),
])
def test_detects_changed_primary_summary_even_with_consistent_local_json(
    evidence, field, new_value,
):
    main, evaluator, payload = evidence
    name = "D6_minus_D3_retrieval_depth"
    modified = copy.deepcopy(payload)
    modified["primary_contrasts"][name][field] = new_value
    with pytest.raises(ValueError, match="independent primary inference mismatch"):
        audit_primary(main, evaluator, modified)


def test_detects_single_changed_task_effect(evidence):
    main, evaluator, payload = evidence
    payload["primary_contrasts"]["D6_minus_D3_retrieval_depth"]["task_differences"][0] += 0.01
    with pytest.raises(ValueError, match="task_differences"):
        audit_primary(main, evaluator, payload)


def test_detects_changed_variant_mean(evidence):
    main, evaluator, payload = evidence
    payload["variant_summary"]["P6"]["means"]["strict_support_rate"] += 0.01
    with pytest.raises(ValueError, match="mean_strict_support_rate"):
        audit_primary(main, evaluator, payload)


def test_detects_task_identity_reordering(evidence):
    main, evaluator, payload = evidence
    payload["task_ids"].reverse()
    with pytest.raises(ValueError, match="task_ids"):
        audit_primary(main, evaluator, payload)


def test_detects_invalid_primary_family(evidence):
    main, evaluator, payload = evidence
    payload["primary_contrasts"]["unplanned_posthoc_comparison"] = {}
    with pytest.raises(ValueError, match="primary contrast schema mismatch"):
        audit_primary(main, evaluator, payload)


def test_signflip_calculation_is_exact_on_synthetic_ties_and_zeros():
    assert _exact_signflip([Fraction(0), Fraction(0)]) == 1
    assert _exact_signflip([Fraction(1, 3), Fraction(0)]) == 1
    assert _exact_signflip([Fraction(1), Fraction(1), Fraction(1)]) == Fraction(1, 4)


@pytest.mark.parametrize("bad_json,expected", [
    ('{"a":1,"a":2}', "duplicate inference JSON key"),
    ('{"a":NaN}', "non-finite inference JSON token"),
])
def test_rejects_ambiguous_or_nonstandard_json_before_statistical_audit(
    tmp_path, bad_json, expected,
):
    path = tmp_path / "altered.json"
    path.write_text(bad_json)
    with pytest.raises(ValueError, match=expected):
        audit_files(
            ROOT / "outputs/main_study_runs.csv",
            ROOT / "outputs/posthoc_support_runs.csv",
            path,
        )


def test_rejects_coherently_dropped_cell_even_when_both_csvs_match(evidence):
    main, evaluator, payload = evidence
    main.pop()
    evaluator[:] = [
        row for row in evaluator
        if (row["variant_id"], row["task_id"]) in
        {(item["variant_id"], item["task_id"]) for item in main}
    ]
    with pytest.raises(ValueError, match="frozen matrix mismatch"):
        audit_primary(main, evaluator, payload)


@pytest.mark.parametrize("field,replacement", [
    ("posthoc_claims_checked", "1"),
    ("posthoc_strict_support_rate", "0.123456"),
])
def test_rejects_broken_treatment_evaluator_mirror(evidence, field, replacement):
    main, evaluator, payload = evidence
    main[0][field] = replacement
    with pytest.raises(ValueError, match="evaluator mirror mismatch"):
        audit_primary(main, evaluator, payload)
