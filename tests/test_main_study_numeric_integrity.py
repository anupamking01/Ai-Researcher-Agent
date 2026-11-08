"""Synthetic numeric-input integrity regressions; no analyzer or treatment reruns."""

import copy

import pytest

from scripts import audit_main_study_numeric_inputs as audit


def _rows():
    main = [{
        "variant_id": "D3", "task_id": "synthetic-only",
        "completed": "true", "source_budget": "3",
        "successful_sources": "1", "failed_sources": "2", "search_calls": "1",
        "model_calls": "2", "total_tokens": "100",
        "treatment_cost_usd": "0.01", "latency_seconds": "3.5",
        "report_words": "120", "posthoc_claims_checked": "4",
        "posthoc_strict_support_rate": "0.5",
        "posthoc_evaluator_cost_usd": "0.004",
    }]
    support = [{
        "variant_id": "D3", "task_id": "synthetic-only",
        "claims_checked": "4", "supported": "2", "partially_supported": "1",
        "unsupported": "1", "contradicted": "0",
        "strict_support_rate": "0.5", "total_tokens": "80",
        "estimated_cost_usd": "0.004",
    }]
    return main, support


def _check(*, main_change=None, support_change=None):
    main, support = copy.deepcopy(_rows())
    if main_change:
        main[0].update(main_change)
    if support_change:
        support[0].update(support_change)
    return audit.audit_rows(
        main, support,
        variants=("D3",), tasks=("synthetic-only",), budgets={"D3": 3},
    )


def test_valid_synthetic_data():
    assert _check()["n_cells"] == 1


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "-0.1", "not-a-number"])
def test_invalid_treatment_measurement_rejected(bad):
    with pytest.raises(audit.NumericInputError, match="numeric|nonfinite|negative"):
        _check(main_change={"treatment_cost_usd": bad})


@pytest.mark.parametrize("bad", ["3.5", "-1", "nan", "inf", "oops"])
def test_nonintegral_or_invalid_claim_counts_rejected(bad):
    with pytest.raises(audit.NumericInputError, match="count|numeric|nonfinite|negative|fractional"):
        _check(support_change={"supported": bad})


def test_overcap_claims_rejected():
    with pytest.raises(audit.NumericInputError, match="outside frozen"):
        _check(support_change={"claims_checked": "13"})


@pytest.mark.parametrize("bad", ["0.25", "1.01", "nan", "-0.1"])
def test_exported_rate_mismatch_rejected(bad):
    with pytest.raises(audit.NumericInputError, match="strict_support_rate"):
        _check(support_change={"strict_support_rate": bad})


def test_treatment_mirrored_claims_mismatch_rejected():
    with pytest.raises(audit.NumericInputError, match="mirrored claims_checked"):
        _check(main_change={"posthoc_claims_checked": "5"})


def test_treatment_mirrored_rate_mismatch_rejected():
    with pytest.raises(audit.NumericInputError, match="posthoc_strict_support_rate"):
        _check(main_change={"posthoc_strict_support_rate": "0.75"})


def test_treatment_mirrored_evaluator_cost_mismatch_rejected():
    with pytest.raises(audit.NumericInputError, match="evaluator-cost"):
        _check(main_change={"posthoc_evaluator_cost_usd": "0.99"})


def test_duplicate_cell_rejected():
    main, support = _rows()
    with pytest.raises(audit.NumericInputError, match="duplicate"):
        audit.audit_rows(
            main + main, support,
            variants=("D3",), tasks=("synthetic-only",), budgets={"D3": 3},
        )


def test_accept_integral_decimal_and_binary_rounding_noise():
    result = _check(support_change={
        "claims_checked": "4.0",
        "supported": "2.0",
        "strict_support_rate": "0.5000000000001",
    })
    assert result["n_cells"] == 1


def test_frozen_csv_inputs_have_internally_consistent_numeric_fields():
    result = audit.audit_files()
    assert result["n_cells"] == 40
    assert result["n_tasks"] == 10
    assert result["status"].endswith("not_original_source_authenticity")
    assert len(result["input_sha256"]) == 2
