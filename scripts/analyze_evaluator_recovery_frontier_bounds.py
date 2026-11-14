"""Exploratory Pareto sensitivity to the three recovered evaluator measurements.

This is an algebraic envelope for a historical measurement-policy split,
not a confidence interval, a replacement for frozen inference, or new evidence.
No treatments, evaluators, model calls, or human ratings are produced.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from scripts import analyze_evaluator_recovery_policy_bounds as policy
from scripts import audit_frozen_analysis_csv_inputs as frozen

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = policy.partition.VARIANTS
TASK_IDS = policy.partition.TASK_IDS
RECOVERED = frozenset(policy.partition.RECOVERED)


class FrontierEnvelopeError(ValueError):
    """The inputs cannot support a frozen-cost measurement envelope."""


def _as_fraction(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else (
        f"{value.numerator}/{value.denominator}"
    )


def _frontier(qualities: dict[str, Fraction],
              costs: dict[str, Fraction]) -> list[str]:
    """Pareto frontier: maximize quality, minimize treatment-only cost."""
    return [
        arm for arm in VARIANTS
        if not any(
            (costs[other] <= costs[arm] and qualities[other] >= qualities[arm])
            and (costs[other] < costs[arm] or qualities[other] > qualities[arm])
            for other in VARIANTS if other != arm
        )
    ]


def _p6v_frontier_entry_threshold(
    qualities: dict[str, Fraction], costs: dict[str, Fraction],
) -> tuple[Fraction | None, bool]:
    """Quality boundary for entry with all other arms and costs held fixed.

    At equal quality, a strictly cheaper rival dominates; an equally costly
    rival does not. No non-more-expensive rivals means unconditional entry.
    """
    rivals = [arm for arm in VARIANTS if arm != "P6V"
              and costs[arm] <= costs["P6V"]]
    if not rivals:
        return None, False
    boundary = max(qualities[arm] for arm in rivals)
    strict = any(costs[arm] < costs["P6V"] and qualities[arm] == boundary
                 for arm in rivals)
    return boundary, strict


def calculate_frontier_envelope(
    treatment_rows: list[dict[str, str]],
    evaluator_rows: list[dict[str, str]],
) -> dict:
    """Synthetic-testable arithmetic; production additionally pins both CSV bytes."""
    bounds = policy.calculate_bounds(evaluator_rows)
    main = frozen._paired_rows(treatment_rows, label="frontier treatment summary")
    support = frozen._paired_rows(evaluator_rows, label="frontier evaluator summary")
    expected = {(arm, task) for arm in VARIANTS for task in TASK_IDS}
    if set(main) != expected or set(support) != expected:
        raise FrontierEnvelopeError("frontier analysis requires the exact 40-cell matrix")

    scores: dict[tuple[str, str], Fraction] = {}
    costs: dict[str, Fraction] = {}
    for arm in VARIANTS:
        total_cost = Fraction()
        for task in TASK_IDS:
            cell = (arm, task)
            label = f"{arm}/{task}"
            treatment = main[cell]
            evaluated = support[cell]
            if treatment.get("completed", "").strip().lower() not in ("true", "1", "yes"):
                raise FrontierEnvelopeError(f"incomplete treatment: {label}")
            if frozen._int(treatment, "source_budget", label=label) != (
                3 if arm == "D3" else 6
            ):
                raise FrontierEnvelopeError(f"treatment-budget mismatch: {label}")
            checked = frozen._int(evaluated, "claims_checked", label=label)
            supported = frozen._int(evaluated, "supported", label=label)
            if not 1 <= checked <= 12 or not 0 <= supported <= checked:
                raise FrontierEnvelopeError(f"invalid claim support counts: {label}")
            rate = Fraction(supported, checked)
            if frozen._int(treatment, "posthoc_claims_checked", label=label) != checked:
                raise FrontierEnvelopeError(f"treatment/evaluator claim mismatch: {label}")
            try:
                raw_cost = treatment["treatment_cost_usd"]
                raw_rate = treatment["posthoc_strict_support_rate"]
                if type(raw_cost) is not str or type(raw_rate) is not str:
                    raise FrontierEnvelopeError(f"invalid treatment summary types: {label}")
                cost = Decimal(raw_cost)
                mirror = Decimal(raw_rate)
            except (KeyError, InvalidOperation, ValueError) as exc:
                raise FrontierEnvelopeError(f"invalid treatment numeric data: {label}") from exc
            if (not cost.is_finite() or cost < 0 or not mirror.is_finite()
                    or mirror < 0 or mirror > 1
                    or abs(Fraction(mirror) - rate) > Fraction(1, 10**12)):
                raise FrontierEnvelopeError(f"cost or support mirror invalid: {label}")
            total_cost += Fraction(cost)
            scores[cell] = rate
        costs[arm] = total_cost / len(TASK_IDS)

    observed_quality = {
        arm: sum((scores[(arm, task)] for task in TASK_IDS), Fraction()) / len(TASK_IDS)
        for arm in VARIANTS
    }
    held_p6v = sum(
        (scores[("P6V", task)] for task in TASK_IDS
         if ("P6V", task) not in RECOVERED),
        Fraction(),
    ) / len(TASK_IDS)
    lower = held_p6v
    upper = held_p6v + Fraction(len(RECOVERED), len(TASK_IDS))
    if (lower - observed_quality["P6"]
            != Fraction(bounds["worst_case_lower_fraction"])
            or upper - observed_quality["P6"]
            != Fraction(bounds["worst_case_upper_fraction"])
            or observed_quality["P6V"] - observed_quality["P6"]
            != Fraction(bounds["frozen_observed_contrast_fraction"])):
        raise FrontierEnvelopeError("source-linked policy envelope disagrees with cost audit")

    low = dict(observed_quality, P6V=lower)
    high = dict(observed_quality, P6V=upper)
    frozen_frontier = _frontier(observed_quality, costs)
    low_frontier = _frontier(low, costs)
    high_frontier = _frontier(high, costs)
    # Only one arm's quality varies: as its score rises it can enter, while
    # other arms can leave, but not vice versa. Endpoints suffice to classify
    # possible versus guaranteed membership across the complete [low,high].
    possible = [arm for arm in VARIANTS
                if arm in low_frontier or arm in high_frontier]
    guaranteed = [arm for arm in VARIANTS
                  if arm in low_frontier and arm in high_frontier]
    # An exact minimal-replacement certificate, not an empirical correction.
    # To maximize P6V under at most k allowed replacements, set the k
    # recovered cells with the largest (1 - observed_score) to one.
    # No other arm's quality or any treatment cost is allowed to vary.
    threshold, strict_threshold = _p6v_frontier_entry_threshold(
        observed_quality, costs
    )
    recovered_observed_sum = sum((scores[cell] for cell in RECOVERED), Fraction())
    largest_gains = sorted(
        (Fraction(1) - scores[cell] for cell in RECOVERED), reverse=True
    )
    maximum_quality_by_k: list[str] = []
    p6v_member_by_k: list[bool] = []
    cumulative_gain = Fraction()
    for k in range(len(RECOVERED) + 1):
        if k:
            cumulative_gain += largest_gains[k - 1]
        maximum_quality = observed_quality["P6V"] + cumulative_gain / len(TASK_IDS)
        maximum_quality_by_k.append(_as_fraction(maximum_quality))
        p6v_member_by_k.append(
            "P6V" in _frontier(dict(observed_quality, P6V=maximum_quality), costs)
        )
    min_replacements = next(
        (k for k, member in enumerate(p6v_member_by_k) if member), None
    )
    if p6v_member_by_k[-1] != ("P6V" in high_frontier):
        raise FrontierEnvelopeError("replacement entry certificate disagrees with envelope")

    return {
        "schema_version": 1,
        "status": "post_hoc_exploratory_recovery_policy_pareto_envelope_only",
        "study_id": "budget-main-v1",
        "cost_definition": "mean_treatment_cost_usd_excludes_common_evaluator",
        "quality_definition": "mean_per_report_strict_support_not_pooled_claims",
        "recovered_policy_cells": [f"{v}/{t}" for v, t in sorted(RECOVERED)],
        "fixed_treatment_cost_means_exact": {
            arm: _as_fraction(costs[arm]) for arm in VARIANTS
        },
        "frozen_quality_means_exact": {
            arm: _as_fraction(observed_quality[arm]) for arm in VARIANTS
        },
        "p6v_quality_lower_exact": _as_fraction(lower),
        "p6v_quality_upper_exact": _as_fraction(upper),
        "frozen_frontier": frozen_frontier,
        "lower_endpoint_frontier": low_frontier,
        "upper_endpoint_frontier": high_frontier,
        "guaranteed_frontier_members": guaranteed,
        "possible_frontier_members": possible,
        "frontier_invariant_across_envelope": low_frontier == high_frontier,
        "p6v_frontier_entry_quality_boundary_exact": (
            None if threshold is None else _as_fraction(threshold)
        ),
        "p6v_frontier_entry_requires_strictly_higher_quality": strict_threshold,
        "p6v_recovered_observed_score_sum_exact": _as_fraction(recovered_observed_sum),
        "p6v_recovered_score_sum_entry_boundary_exact": (
            None if threshold is None
            else _as_fraction(len(TASK_IDS) * (threshold - held_p6v))
        ),
        "p6v_maximum_quality_with_at_most_k_replacements_exact": maximum_quality_by_k,
        "p6v_can_enter_frontier_with_at_most_k_replacements": p6v_member_by_k,
        "p6v_minimum_recovered_measurements_to_replace_for_frontier_entry": min_replacements,
        "replacement_count_is_algebraic_not_an_observed_policy_change": True,
        "endpoints_exhaust_membership_states_under_one_arm_monotonicity": True,
        "all_other_37_scores_and_all_40_treatment_costs_fixed": True,
        "measurement_bias_estimated": False,
        "new_confirmatory_inference_performed": False,
        "original_report_trace_custody_authenticated": False,
        "original_evaluator_execution_authenticated": False,
        "human_validation_performed": False,
    }


def run_verified(root: Path = ROOT) -> dict:
    """Audit historical recovery source, frozen CSVs and re-captured original pins."""
    root = Path(root).resolve()
    verified_bounds = policy.run_verified(root)
    treatment_bytes, treatment_rows = frozen._read_csv(
        root / "outputs/main_study_runs.csv", label="frontier frozen treatment CSV"
    )
    support_bytes, support_rows = frozen._read_csv(
        root / "outputs/posthoc_support_runs.csv", label="frontier frozen evaluator CSV"
    )
    if (hashlib.sha256(treatment_bytes).hexdigest() != frozen.FROZEN_MAIN_CSV_SHA256
            or hashlib.sha256(support_bytes).hexdigest() != frozen.FROZEN_SUPPORT_CSV_SHA256):
        raise FrontierEnvelopeError("published CSV bytes changed after provenance preflight")
    result = calculate_frontier_envelope(treatment_rows, support_rows)
    if (result["frozen_quality_means_exact"]["P6V"] !=
            _as_fraction(Fraction(verified_bounds["frozen_observed_contrast_fraction"])
                         + Fraction(result["frozen_quality_means_exact"]["P6"]))):
        raise FrontierEnvelopeError("source-verified recovery bounds changed")
    result["historical_recovery_policy_source_audited"] = True
    result["published_treatment_csv_sha256"] = frozen.FROZEN_MAIN_CSV_SHA256
    result["published_evaluator_csv_sha256"] = frozen.FROZEN_SUPPORT_CSV_SHA256
    result["published_input_aggregate_sha256"] = frozen.PUBLISHED_INPUT_AGGREGATE_SHA256
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(run_verified(args.root), indent=2, sort_keys=True,
                         allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"recovery-policy Pareto envelope failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
