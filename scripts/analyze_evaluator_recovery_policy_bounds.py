"""Exploratory worst-case bounds for the historical evaluator recovery-policy split.

This is a 0..1 measurement-replacement envelope, not a new statistical
interval, causal identification, or a correction to frozen VERA inference.
Never invokes treatments, evaluators, models, or human annotators.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from scripts import audit_frozen_analysis_csv_inputs as frozen
from scripts import audit_historical_evaluator_measurement_partition as partition

ROOT = Path(__file__).resolve().parents[1]
RECOVERED = frozenset(partition.RECOVERED)


class RecoveryPolicyBoundsError(ValueError):
    """The available 40-cell data cannot support this sensitivity envelope."""


def _format_fraction(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else (
        f"{value.numerator}/{value.denominator}"
    )


def calculate_bounds(rows: list[dict[str, str]]) -> dict:
    """Hold the 37 non-recovered cells fixed; replace all three P6V rates in [0, 1].

    Accepts synthetic rows for offline tests. The production entrypoint also
    verifies historical Git source and the published SHA-256-pinned CSVs.
    """
    matrix = frozen._paired_rows(rows, label="recovery-policy sensitivity")
    expected = {(v, t) for v in partition.VARIANTS for t in partition.TASK_IDS}
    if set(matrix) != expected or len(RECOVERED) != 3 or not RECOVERED <= expected:
        raise RecoveryPolicyBoundsError("unexpected frozen matrix or recovery cell set")
    if any(variant != "P6V" for variant, _ in RECOVERED):
        raise RecoveryPolicyBoundsError("historical recovered cells are not exclusively P6V")
    rates: dict[tuple[str, str], Fraction] = {}
    for cell, row in matrix.items():
        label = f"{cell[0]}/{cell[1]}"
        if row.get("evidence_status") != partition.RECOVERED.get(cell, ""):
            raise RecoveryPolicyBoundsError(f"recovery partition changed for {label}")
        checked = frozen._int(row, "claims_checked", label=label)
        counts = [
            frozen._int(row, field, label=label)
            for field in ("supported", "partially_supported", "unsupported", "contradicted")
        ]
        if not 1 <= checked <= 12 or min(counts) < 0 or sum(counts) != checked:
            raise RecoveryPolicyBoundsError(f"invalid frozen evaluator counts for {label}")
        rate = Fraction(counts[0], checked)
        published_rate = frozen._finite_nonnegative(
            row, "strict_support_rate", label=label
        )
        if published_rate > 1 or not math.isclose(
            published_rate, float(rate), rel_tol=0, abs_tol=1e-12
        ):
            raise RecoveryPolicyBoundsError(f"frozen strict-support mismatch for {label}")
        rates[cell] = rate

    n_tasks = len(partition.TASK_IDS)
    sum_p6 = sum((rates[("P6", t)] for t in partition.TASK_IDS), Fraction())
    retained_p6v = sum(
        (rates[("P6V", t)] for t in partition.TASK_IDS
         if ("P6V", t) not in RECOVERED), Fraction()
    )
    recovered_p6v = sum((rates[cell] for cell in RECOVERED), Fraction())
    lower = (retained_p6v - sum_p6) / n_tasks
    upper = (retained_p6v + len(RECOVERED) - sum_p6) / n_tasks
    observed = (retained_p6v + recovered_p6v - sum_p6) / n_tasks
    if not lower <= observed <= upper or upper - lower != Fraction(3, 10):
        raise RecoveryPolicyBoundsError("invalid worst-case recovery envelope")

    return {
        "schema_version": 1,
        "status": "post_hoc_exploratory_recovery_policy_measurement_envelope_only",
        "contrast": "P6V_minus_P6",
        "n_tasks": n_tasks,
        "recovered_cell_ids": [f"{v}/{t}" for v, t in sorted(RECOVERED)],
        "recovered_cells_allowed_to_vary": len(RECOVERED),
        "p6v_cells_held_fixed": n_tasks - len(RECOVERED),
        "p6_cells_held_fixed": n_tasks,
        "per_recovered_cell_possible_score_range": ["0", "1"],
        "frozen_observed_contrast_fraction": _format_fraction(observed),
        "worst_case_lower_fraction": _format_fraction(lower),
        "worst_case_upper_fraction": _format_fraction(upper),
        "worst_case_width_fraction": _format_fraction(upper - lower),
        "frozen_observed_contrast": float(observed),
        "worst_case_lower": float(lower),
        "worst_case_upper": float(upper),
        "envelope_contains_zero": lower <= 0 <= upper,
        "assumes_unrecovered_scores_unchanged": True,
        "all_three_recovery_scores_treated_as_unrestricted": True,
        "original_report_trace_custody_authenticated": False,
        "historical_evaluator_execution_authenticated": False,
        "actual_measurement_bias_identified": False,
        "causal_effect_identified": False,
        "new_statistical_inference_performed": False,
        "frozen_primary_inference_modified": False,
        "human_validation_performed": False,
    }


def run_verified(root: Path = ROOT) -> dict:
    """Run full historical source audit plus both published-input byte pins."""
    root = Path(root).resolve()
    partition_receipt = partition.audit_checkout(root)
    if (partition_receipt.get("historical_source_policy_audited") is not True
            or partition_receipt.get("frozen_treatment_evaluator_summary_preflight_passed")
            is not True):
        raise RecoveryPolicyBoundsError("historical 37+3 provenance preflight not established")
    raw, rows = frozen._read_csv(
        root / "outputs/posthoc_support_runs.csv", label="frozen evaluator CSV"
    )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != frozen.FROZEN_SUPPORT_CSV_SHA256:
        raise RecoveryPolicyBoundsError("frozen evaluator source changed between reads")
    result = calculate_bounds(rows)
    result["published_evaluator_csv_sha256"] = digest
    result["published_treatment_csv_sha256_reference"] = frozen.FROZEN_MAIN_CSV_SHA256
    result["published_input_aggregate_sha256_reference"] = (
        frozen.PUBLISHED_INPUT_AGGREGATE_SHA256
    )
    result["historical_recovery_source_and_summary_audited"] = True
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(run_verified(args.root), indent=2, sort_keys=True, allow_nan=False))
    except (OSError, ValueError, frozen.InputIntegrityError,
            partition.source.HistoricalEvaluatorPolicyError,
            partition.source.history.HistoricalDesignSourceError) as exc:
        parser.exit(1, f"recovery-policy envelope failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
