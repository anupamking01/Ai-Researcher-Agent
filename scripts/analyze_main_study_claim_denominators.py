"""Exploratory claim-denominator diagnostic for the frozen VERA automated study.

The frozen inferential estimand remains the task-macro mean of strict-support
rates. This read-only diagnostic reports whether the number of evaluator
claims checked differs by variant, and contrasts equal-report weighting with
claim-pooled weighting. Neither weighting measures answer completeness.
No treatments, evaluators, human ratings, tests of significance or CIs are run.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from scripts import audit_frozen_analysis_csv_inputs as audit

STUDY_ID = "budget-main-v1"
CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def summarize_claim_denominators(rows: list[dict[str, str]]) -> dict:
    """Compute exhaustive descriptive counts for a balanced 40-cell matrix.

    This function accepts synthetic rows for tests; the production entrypoint
    additionally enforces the separately pinned frozen source SHA-256.
    """
    matrix = audit._paired_rows(rows, label="support denominator diagnostic")
    tasks = sorted({task for _, task in matrix})
    _require(len(tasks) == audit.EXPECTED_TASKS, "expected ten frozen tasks")

    counts: dict[tuple[str, str], tuple[int, int]] = {}
    for (variant, task), row in matrix.items():
        label = f"{variant}/{task}"
        checked = audit._int(row, "claims_checked", label=label)
        supported = audit._int(row, "supported", label=label)
        partial = audit._int(row, "partially_supported", label=label)
        unsupported = audit._int(row, "unsupported", label=label)
        contradicted = audit._int(row, "contradicted", label=label)
        _require(1 <= checked <= 12, f"{label} claims_checked outside frozen cap")
        _require(
            min(supported, partial, unsupported, contradicted) >= 0
            and supported + partial + unsupported + contradicted == checked,
            f"{label} evaluator counts do not partition claims_checked",
        )
        stated = audit._finite_nonnegative(row, "strict_support_rate", label=label)
        _require(
            stated <= 1.0
            and math.isclose(stated, supported / checked, rel_tol=0.0, abs_tol=1e-12),
            f"{label} reported strict-support rate contradicts counts",
        )
        counts[(variant, task)] = (checked, supported)

    variants = {}
    for variant in audit.VARIANTS:
        values = [counts[(variant, task)] for task in tasks]
        checked_total = sum(checked for checked, _ in values)
        supported_total = sum(supported for _, supported in values)
        macro = math.fsum(supported / checked for checked, supported in values) / len(tasks)
        pooled = supported_total / checked_total
        variants[variant] = {
            "n_reports": len(tasks),
            "total_claims_checked": checked_total,
            "total_claims_supported": supported_total,
            "claims_checked_mean_per_report": checked_total / len(tasks),
            "claims_checked_min": min(checked for checked, _ in values),
            "claims_checked_max": max(checked for checked, _ in values),
            "claims_checked_histogram_1_to_12": {
                str(n): sum(checked == n for checked, _ in values)
                for n in range(1, 13)
            },
            "reports_at_12_claim_cap": sum(checked == 12 for checked, _ in values),
            "task_claim_counts": [
                {"task_id": task, "claims_checked": counts[(variant, task)][0]}
                for task in tasks
            ],
            "equal_report_macro_strict_support": macro,
            "claim_pooled_micro_strict_support": pooled,
            "micro_minus_macro_strict_support": pooled - macro,
        }

    contrasts = {}
    for left, right, name in CONTRASTS:
        per_task = [
            {
                "task_id": task,
                "left_claims_checked": counts[(left, task)][0],
                "right_claims_checked": counts[(right, task)][0],
                "right_minus_left_claims_checked": (
                    counts[(right, task)][0] - counts[(left, task)][0]
                ),
            }
            for task in tasks
        ]
        differences = [row["right_minus_left_claims_checked"] for row in per_task]
        contrasts[name] = {
            "n_paired_tasks": len(tasks),
            "mean_difference_claims_checked": math.fsum(differences) / len(tasks),
            "tasks_with_more_claims_right": sum(d > 0 for d in differences),
            "tasks_with_fewer_claims_right": sum(d < 0 for d in differences),
            "tasks_with_equal_claims": sum(d == 0 for d in differences),
            "all_task_claim_count_differences": per_task,
        }

    return {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "status": "post_hoc_exploratory_denominator_diagnostic_only",
        "task_ids": tasks,
        "variant_summaries": variants,
        "frozen_contrast_denominator_comparisons": contrasts,
        "confirmatory_primary_estimand_changed": False,
        "p_values_or_confidence_intervals_added": False,
        "human_validation_performed": False,
        "original_execution_authenticated": False,
        "interpretation": (
            "Evaluator checked-claim counts describe a capped measurement "
            "denominator, not report completeness or all report claims. "
            "The frozen confirmatory estimand is the equal-report macro rate. "
            "Claim-pooled rates are post-hoc descriptive sensitivity values."
        ),
    }


def run_verified() -> dict:
    """Read only the Git-published canonical summaries; fail on source drift."""
    # Checks both retained CSVs, the frozen manifest, original task identities,
    # and cross-file evaluator arithmetic before using any measurement.
    audit.audit_frozen_csv_inputs()
    captured, rows = audit._read_csv(
        audit.DEFAULT_SUPPORT, label="published evaluator support summary"
    )
    captured_sha = hashlib.sha256(captured).hexdigest()
    _require(
        captured_sha == audit.FROZEN_SUPPORT_CSV_SHA256,
        "published evaluator CSV changed after preflight",
    )
    result = summarize_claim_denominators(rows)
    _require(
        result["task_ids"] == [f"main-{index:02d}" for index in range(1, 11)],
        "published task identities changed after preflight",
    )
    result["verified_published_evaluator_csv_sha256"] = captured_sha
    result["published_treatment_csv_sha256_reference"] = audit.FROZEN_MAIN_CSV_SHA256
    result["published_input_aggregate_sha256_reference"] = (
        audit.PUBLISHED_INPUT_AGGREGATE_SHA256
    )
    result["published_summary_preflight_passed"] = True
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(json.dumps(run_verified(), sort_keys=True, indent=2, allow_nan=False))
    except (OSError, ValueError, audit.InputIntegrityError) as exc:
        parser.exit(1, f"CLAIM DENOMINATOR DIAGNOSTIC: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
