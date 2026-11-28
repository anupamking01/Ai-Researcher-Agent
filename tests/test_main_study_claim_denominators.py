"""Synthetic-only tests for exploratory claim-denominator sensitivity."""
from __future__ import annotations

import copy

import pytest

from scripts import analyze_main_study_claim_denominators as diagnostic


def _matrix():
    rows = []
    for variant in ("D3", "D6", "P6", "P6V"):
        for task in range(1, 11):
            rows.append({
                "variant_id": variant,
                "task_id": f"synthetic-{task:02d}",
                "claims_checked": "8",
                "supported": "6",
                "partially_supported": "1",
                "unsupported": "1",
                "contradicted": "0",
                "strict_support_rate": "0.75",
            })
    return rows


def _change(row, *, checked, supported):
    row.update({
        "claims_checked": str(checked),
        "supported": str(supported),
        "partially_supported": "0",
        "unsupported": str(checked - supported),
        "contradicted": "0",
        "strict_support_rate": str(supported / checked),
    })


def test_uniform_claim_counts_make_macro_and_pooled_rate_identical():
    summary = diagnostic.summarize_claim_denominators(_matrix())
    assert summary["status"] == "post_hoc_exploratory_denominator_diagnostic_only"
    assert not summary["confirmatory_primary_estimand_changed"]
    assert not summary["p_values_or_confidence_intervals_added"]
    assert not summary["human_validation_performed"]
    assert not summary["original_execution_authenticated"]
    assert len(summary["task_ids"]) == 10
    assert set(summary["variant_summaries"]) == {"D3", "D6", "P6", "P6V"}
    for arm in summary["variant_summaries"].values():
        assert arm["total_claims_checked"] == 80
        assert arm["total_claims_supported"] == 60
        assert arm["claims_checked_histogram_1_to_12"]["8"] == 10
        assert sum(arm["claims_checked_histogram_1_to_12"].values()) == 10
        assert arm["equal_report_macro_strict_support"] == pytest.approx(0.75)
        assert arm["claim_pooled_micro_strict_support"] == pytest.approx(0.75)
    assert set(summary["frozen_contrast_denominator_comparisons"]) == {
        name for _, _, name in diagnostic.CONTRASTS
    }


def test_different_report_denominators_change_macro_vs_micro_without_new_inference():
    rows = _matrix()
    # Eight short, supported reports and two long, unsupported reports.
    # Equal-report rate is 0.8, pooled-claim rate is only 8/32 = 0.25.
    for row in rows:
        if row["variant_id"] == "D3":
            ordinal = int(row["task_id"][-2:])
            _change(
                row, checked=(1 if ordinal <= 8 else 12),
                supported=(1 if ordinal <= 8 else 0),
            )
    result = diagnostic.summarize_claim_denominators(rows)
    d3 = result["variant_summaries"]["D3"]
    d6 = result["variant_summaries"]["D6"]
    assert d3["total_claims_checked"] == 32
    assert d3["total_claims_supported"] == 8
    assert d3["reports_at_12_claim_cap"] == 2
    assert d3["equal_report_macro_strict_support"] == pytest.approx(0.8)
    assert d3["claim_pooled_micro_strict_support"] == pytest.approx(0.25)
    assert d6["equal_report_macro_strict_support"] == pytest.approx(0.75)
    assert d6["claim_pooled_micro_strict_support"] == pytest.approx(0.75)
    # This is precisely why pooled rates cannot replace frozen paired inference.
    diff = result["frozen_contrast_denominator_comparisons"][
        "D6_minus_D3_retrieval_depth"
    ]
    assert diff["mean_difference_claims_checked"] == pytest.approx(4.8)
    assert diff["tasks_with_more_claims_right"] == 8
    assert diff["tasks_with_fewer_claims_right"] == 2
    assert diff["tasks_with_equal_claims"] == 0


def test_order_invariant_and_no_input_mutation():
    rows = _matrix()
    original = copy.deepcopy(rows)
    first = diagnostic.summarize_claim_denominators(rows)
    assert rows == original
    assert diagnostic.summarize_claim_denominators(list(reversed(rows))) == first


@pytest.mark.parametrize("field,value", [
    ("claims_checked", "0"),
    ("claims_checked", "13"),
    ("claims_checked", "1.5"),
    ("supported", "-1"),
    ("partially_supported", "4"),
    ("strict_support_rate", "0.76"),
    ("claims_checked", "NaN"),
])
def test_invalid_denominators_and_inconsistent_evaluator_rows_fail(field, value):
    rows = _matrix()
    rows[0][field] = value
    with pytest.raises(ValueError):
        diagnostic.summarize_claim_denominators(rows)


def test_duplicate_cell_cannot_replace_task_and_forge_denominator_distribution():
    rows = _matrix()
    rows[1]["task_id"] = rows[0]["task_id"]
    with pytest.raises(ValueError, match="duplicate"):
        diagnostic.summarize_claim_denominators(rows)


def test_mismatched_variant_task_sets_fail_even_when_there_are_40_rows():
    rows = _matrix()
    rows[0]["task_id"] = "synthetic-missing"
    with pytest.raises(ValueError, match="identical task sets"):
        diagnostic.summarize_claim_denominators(rows)


def test_nonfinite_rate_fails_closed():
    rows = _matrix()
    rows[0]["strict_support_rate"] = "inf"
    with pytest.raises(ValueError):
        diagnostic.summarize_claim_denominators(rows)


def test_published_summary_reproduces_frozen_variant_macro_rates():
    """Production gate accepts only published bytes and leaves inference intact."""
    import json
    from scripts import audit_frozen_analysis_csv_inputs as audit

    result = diagnostic.run_verified()
    assert result["published_summary_preflight_passed"] is True
    assert result["verified_published_evaluator_csv_sha256"] == (
        audit.FROZEN_SUPPORT_CSV_SHA256
    )
    assert result["published_input_aggregate_sha256_reference"] == (
        audit.PUBLISHED_INPUT_AGGREGATE_SHA256
    )
    inference = json.loads(
        (audit.REPO_ROOT / "outputs/main_study_inference.json").read_text(
            encoding="utf-8"
        )
    )
    for variant in audit.VARIANTS:
        observed = result["variant_summaries"][variant][
            "equal_report_macro_strict_support"
        ]
        frozen = inference["variant_summary"][variant]["means"][
            "strict_support_rate"
        ]
        assert observed == pytest.approx(frozen, abs=1e-12)
