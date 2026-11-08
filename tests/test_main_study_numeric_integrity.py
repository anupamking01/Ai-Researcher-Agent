"""Synthetic fail-closed checks for main-study numeric evidence at the paired-analysis join.

No treatment, evaluator, canonical result, or human-rating artifact is opened or rewritten.
"""

import copy

import pytest

from scripts import analyze_main_study as analysis


def _rows():
    main = [{
        "variant_id": "D3",
        "task_id": "synthetic-only",
        "completed": "true",
        "successful_sources": "1",
        "total_tokens": "100",
        "treatment_cost_usd": "0.01",
        "latency_seconds": "3.5",
        "model_calls": "2",
        "report_words": "120",
        "posthoc_claims_checked": "4",
        "posthoc_strict_support_rate": "0.5",
    }]
    support = [{
        "variant_id": "D3",
        "task_id": "synthetic-only",
        "claims_checked": "4",
        "supported": "2",
        "partially_supported": "1",
        "unsupported": "1",
        "contradicted": "0",
        "strict_support_rate": "0.5",
        "evidence_status": "",
    }]
    return main, support


def _join(monkeypatch, *, main_change=None, support_change=None):
    main, support = copy.deepcopy(_rows())
    if main_change:
        main[0].update(main_change)
    if support_change:
        support[0].update(support_change)
    monkeypatch.setattr(analysis, "VARIANTS", ("D3",))
    monkeypatch.setattr(analysis, "EXPECTED_TASKS", 1)
    monkeypatch.setattr(
        analysis, "_read_csv",
        lambda path: main if path == analysis.MAIN_CSV else support,
    )
    return analysis._build_dataset()


def test_valid_synthetic_join_retains_original_ratio(monkeypatch):
    joined, tasks = _join(monkeypatch)
    assert tasks == ["synthetic-only"]
    assert joined[("D3", "synthetic-only")]["strict_support_rate"] == 0.5


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "-0.1", "not-a-number"])
def test_nonfinite_negative_or_malformed_treatment_measurements_fail(monkeypatch, bad):
    with pytest.raises(SystemExit, match="numeric field"):
        _join(monkeypatch, main_change={"treatment_cost_usd": bad})


@pytest.mark.parametrize("bad", ["3.5", "-1", "nan", "inf", "oops"])
def test_invalid_evaluator_integer_claim_counts_fail(monkeypatch, bad):
    with pytest.raises(SystemExit, match="count|numeric field"):
        _join(monkeypatch, support_change={"supported": bad})


def test_out_of_cap_claim_count_fails(monkeypatch):
    with pytest.raises(SystemExit, match="outside frozen"):
        _join(monkeypatch, support_change={"claims_checked": "13"})


@pytest.mark.parametrize("bad", ["0.25", "1.01", "nan", "-0.1"])
def test_inconsistent_or_nonfinite_exported_rate_fails(monkeypatch, bad):
    with pytest.raises(SystemExit, match="strict-support|numeric field"):
        _join(monkeypatch, support_change={"strict_support_rate": bad})


def test_reject_mutated_treatment_claim_count_mirror(monkeypatch):
    with pytest.raises(SystemExit, match="claim-count mismatch"):
        _join(monkeypatch, main_change={"posthoc_claims_checked": "5"})


def test_reject_mutated_treatment_strict_rate_mirror(monkeypatch):
    with pytest.raises(SystemExit, match="strict-support mismatch"):
        _join(monkeypatch, main_change={"posthoc_strict_support_rate": "0.75"})


def test_accept_integral_decimal_count_and_rounding_noise_in_rate(monkeypatch):
    joined, _ = _join(
        monkeypatch,
        support_change={
            "claims_checked": "4.0",
            "supported": "2.0",
            "strict_support_rate": "0.5000000000001",
        },
    )
    assert joined[("D3", "synthetic-only")]["strict_support_rate"] == 0.5
