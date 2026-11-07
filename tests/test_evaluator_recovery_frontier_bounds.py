"""Synthetic fixtures only: no new VERA evaluation or human-rating results."""
from copy import deepcopy
from fractions import Fraction

import pytest

from scripts import analyze_evaluator_recovery_frontier_bounds as frontier
from scripts import audit_historical_evaluator_measurement_partition as partition


def fixture_rows(*, d3_supported=2, p6v_cost="4"):
    main, evaluated = [], []
    for arm in frontier.VARIANTS:
        for task in frontier.TASK_IDS:
            supported = (d3_supported if arm == "D3" else 2)
            if (arm, task) == ("P6V", "main-10"):
                supported = 0
            rate = supported / 4
            main.append({
                "variant_id": arm, "task_id": task, "completed": "True",
                "source_budget": "3" if arm == "D3" else "6",
                "posthoc_claims_checked": "4",
                "posthoc_strict_support_rate": str(rate),
                "treatment_cost_usd": (p6v_cost if arm == "P6V" else
                                       {"D3": "1", "D6": "2", "P6": "3"}[arm]),
            })
            evaluated.append({
                "variant_id": arm, "task_id": task,
                "evidence_status": partition.RECOVERED.get((arm, task), ""),
                "claims_checked": "4", "supported": str(supported),
                "partially_supported": "0",
                "unsupported": str(4 - supported),
                "contradicted": "0", "strict_support_rate": str(rate),
            })
    return main, evaluated


def test_detects_policy_sensitive_frontier_instead_of_overclaiming_invariance():
    main, evaluated = fixture_rows()
    result = frontier.calculate_frontier_envelope(main, evaluated)
    assert result["p6v_quality_lower_exact"] == "7/20"
    assert result["p6v_quality_upper_exact"] == "13/20"
    assert result["frozen_frontier"] == ["D3"]
    assert result["lower_endpoint_frontier"] == ["D3"]
    assert result["upper_endpoint_frontier"] == ["D3", "P6V"]
    assert result["guaranteed_frontier_members"] == ["D3"]
    assert result["possible_frontier_members"] == ["D3", "P6V"]
    assert result["frontier_invariant_across_envelope"] is False
    assert result["new_confirmatory_inference_performed"] is False


def test_invariant_frontier_when_cheaper_arm_remains_better_at_upper_bound():
    main, evaluated = fixture_rows(d3_supported=3)
    result = frontier.calculate_frontier_envelope(main, evaluated)
    assert result["lower_endpoint_frontier"] == ["D3"]
    assert result["upper_endpoint_frontier"] == ["D3"]
    assert result["possible_frontier_members"] == ["D3"]
    assert result["frontier_invariant_across_envelope"] is True


def test_improving_low_cost_recovered_arm_can_remove_other_frontier_members():
    main, evaluated = fixture_rows(p6v_cost="0.5")
    result = frontier.calculate_frontier_envelope(main, evaluated)
    assert result["lower_endpoint_frontier"] == ["D3", "P6V"]
    assert result["upper_endpoint_frontier"] == ["P6V"]
    assert result["guaranteed_frontier_members"] == ["P6V"]
    assert result["possible_frontier_members"] == ["D3", "P6V"]


def test_complete_result_is_deterministic_and_does_not_mutate_inputs():
    main, evaluated = fixture_rows()
    originals = deepcopy((main, evaluated))
    assert (frontier.calculate_frontier_envelope(main, evaluated)
            == frontier.calculate_frontier_envelope(main, evaluated))
    assert (main, evaluated) == originals


@pytest.mark.parametrize("mutation", ["nan", "negative", "infinite",
                                      "missing_cost", "bad_mirror",
                                      "uncompleted", "budget"])
def test_treatment_integrity_errors_fail_closed(mutation):
    main, evaluated = fixture_rows()
    row = main[0]
    if mutation == "nan":
        row["treatment_cost_usd"] = "nan"
    elif mutation == "negative":
        row["treatment_cost_usd"] = "-0.01"
    elif mutation == "infinite":
        row["treatment_cost_usd"] = "Infinity"
    elif mutation == "missing_cost":
        del row["treatment_cost_usd"]
    elif mutation == "bad_mirror":
        row["posthoc_strict_support_rate"] = "0.9"
    elif mutation == "uncompleted":
        row["completed"] = "False"
    else:
        row["source_budget"] = "6"
    with pytest.raises(ValueError):
        frontier.calculate_frontier_envelope(main, evaluated)


def test_recovered_policy_partition_cannot_be_silently_changed():
    main, evaluated = fixture_rows()
    next(row for row in evaluated
         if row["variant_id"] == "P6V" and row["task_id"] == "main-02")[
         "evidence_status"] = ""
    with pytest.raises(ValueError):
        frontier.calculate_frontier_envelope(main, evaluated)


def test_duplicate_or_missing_treatment_cell_rejected():
    main, evaluated = fixture_rows()
    with pytest.raises(ValueError):
        frontier.calculate_frontier_envelope(main[:-1] + [main[0]], evaluated)
    with pytest.raises(ValueError):
        frontier.calculate_frontier_envelope(main[:-1], evaluated)


def test_evaluator_counts_must_partition_claims():
    main, evaluated = fixture_rows()
    evaluated[0]["supported"] = "5"
    with pytest.raises(ValueError):
        frontier.calculate_frontier_envelope(main, evaluated)


def test_exact_replacement_width_three_of_ten():
    main, evaluated = fixture_rows()
    result = frontier.calculate_frontier_envelope(main, evaluated)
    assert (Fraction(result["p6v_quality_upper_exact"]) -
            Fraction(result["p6v_quality_lower_exact"])) == Fraction(3, 10)
