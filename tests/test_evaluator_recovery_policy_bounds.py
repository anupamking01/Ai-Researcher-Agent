"""Outcome-free synthetic tests of conservative recovered-cell measurement bounds."""
from __future__ import annotations

from fractions import Fraction
import copy

import pytest

from scripts import analyze_evaluator_recovery_policy_bounds as bounds


def _rows():
    rows = []
    for variant in bounds.partition.VARIANTS:
        for task in bounds.partition.TASK_IDS:
            rows.append({
                "variant_id": variant, "task_id": task,
                "evidence_status": bounds.partition.RECOVERED.get((variant, task), ""),
                "claims_checked": "2", "supported": "1",
                "partially_supported": "0", "unsupported": "1",
                "contradicted": "0", "strict_support_rate": "0.5",
            })
    return rows


def _set_recovered_rate(rows, supported):
    for row in rows:
        if (row["variant_id"], row["task_id"]) in bounds.RECOVERED:
            row["supported"] = str(supported)
            row["unsupported"] = str(2 - supported)
            row["strict_support_rate"] = str(supported / 2)


def test_equal_synthetic_rates_give_symmetric_envelope():
    result = bounds.calculate_bounds(_rows())
    assert result["frozen_observed_contrast_fraction"] == "0"
    assert result["worst_case_lower_fraction"] == "-3/20"
    assert result["worst_case_upper_fraction"] == "3/20"
    assert result["worst_case_width_fraction"] == "3/10"
    assert result["envelope_contains_zero"] is True
    assert result["new_statistical_inference_performed"] is False


@pytest.mark.parametrize("supported,expected", [(0, "-3/20"), (1, "0"), (2, "3/20")])
def test_recovered_scores_change_observed_not_possible_envelope(supported, expected):
    rows = _rows()
    _set_recovered_rate(rows, supported)
    result = bounds.calculate_bounds(rows)
    assert result["frozen_observed_contrast_fraction"] == expected
    assert result["worst_case_lower_fraction"] == "-3/20"
    assert result["worst_case_upper_fraction"] == "3/20"


def test_primary_comparator_remains_full_ten_task_p6():
    rows = _rows()
    for row in rows:
        if row["variant_id"] == "P6":
            row["supported"] = "2"
            row["unsupported"] = "0"
            row["strict_support_rate"] = "1"
    result = bounds.calculate_bounds(rows)
    assert result["frozen_observed_contrast_fraction"] == "-1/2"
    assert result["worst_case_lower_fraction"] == "-13/20"
    assert result["worst_case_upper_fraction"] == "-7/20"
    assert result["envelope_contains_zero"] is False


def test_order_independence():
    rows = _rows()
    assert bounds.calculate_bounds(rows) == bounds.calculate_bounds(list(reversed(rows)))


def test_duplicate_cell_rejected():
    rows = _rows()
    rows[-1] = copy.deepcopy(rows[0])
    with pytest.raises(ValueError, match="duplicate"):
        bounds.calculate_bounds(rows)


def test_missing_cell_rejected():
    with pytest.raises(ValueError, match="40"):
        bounds.calculate_bounds(_rows()[:-1])


def test_unspecified_legacy_status_cannot_be_relabelled():
    rows = _rows()
    rows[0]["evidence_status"] = "retrieved_evidence"
    with pytest.raises(bounds.RecoveryPolicyBoundsError, match="partition changed"):
        bounds.calculate_bounds(rows)


def test_recovered_cell_status_cannot_be_relabelled():
    rows = _rows()
    next(r for r in rows if (r["variant_id"], r["task_id"]) in bounds.RECOVERED)[
        "evidence_status"
    ] = ""
    with pytest.raises(bounds.RecoveryPolicyBoundsError, match="partition changed"):
        bounds.calculate_bounds(rows)


@pytest.mark.parametrize("field,value", [
    ("claims_checked", "0"),
    ("supported", "-1"),
    ("supported", "3"),
    ("unsupported", "0"),
    ("strict_support_rate", "NaN"),
    ("strict_support_rate", "1.1"),
    ("strict_support_rate", "0.25"),
    ("claims_checked", "2.5"),
])
def test_invalid_cell_measurement_rejected(field, value):
    rows = _rows()
    rows[0][field] = value
    with pytest.raises(ValueError):
        bounds.calculate_bounds(rows)


def test_exact_rational_support_rates_do_not_depend_on_decimal_rounding():
    rows = _rows()
    for row in rows:
        row.update({
            "claims_checked": "3", "supported": "1", "unsupported": "2",
            "strict_support_rate": "0.3333333333333333",
        })
    result = bounds.calculate_bounds(rows)
    assert result["worst_case_width_fraction"] == "3/10"
    assert result["frozen_observed_contrast_fraction"] == "0"
