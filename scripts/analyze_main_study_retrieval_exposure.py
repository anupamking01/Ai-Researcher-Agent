"""Exploratory audit of scheduled versus realized retrieval in frozen VERA runs.

This is a read-only descriptive exposure diagnostic, not confirmatory inference.
Its production entrypoint validates the exact published study CSV fingerprints
before accessing the 40 original treatment-summary rows.
"""
from __future__ import annotations

import hashlib
import json

from scripts import audit_frozen_analysis_csv_inputs as audit

STUDY_ID = "budget-main-v1"
CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
COUNT_FIELDS = ("successful_sources", "failed_sources", "search_calls",
                "model_calls", "total_tokens")


def summarize_retrieval_exposure(rows: list[dict[str, str]]) -> dict:
    """Summarize *all* frozen cells without examining support or cost outcomes.

    successful+failed is the count of recorded source results; residual
    scheduled capacity is NOT proof that no retrieval operation was attempted.
    This helper accepts synthetic unpinned rows for isolated regression tests.
    """
    matrix = audit._paired_rows(rows, label="realized retrieval exposure")
    tasks = sorted({task for _, task in matrix})
    if len(tasks) != audit.EXPECTED_TASKS:
        raise ValueError("retrieval exposure requires ten paired tasks")

    exposure = {}
    for (variant, task), row in matrix.items():
        label = f"{variant}/{task}"
        if str(row.get("completed", "")).strip().lower() not in {"true", "1", "yes"}:
            raise ValueError(f"{label} treatment was not completed")
        scheduled = audit._int(row, "source_budget", label=label)
        expected_budget = 3 if variant == "D3" else 6
        if scheduled != expected_budget:
            raise ValueError(f"{label} scheduled source budget differs from frozen design")
        counts = {field: audit._int(row, field, label=label) for field in COUNT_FIELDS}
        if any(value < 0 for value in counts.values()):
            raise ValueError(f"{label} has a negative retrieval/resource count")
        accounted = counts["successful_sources"] + counts["failed_sources"]
        if accounted > scheduled:
            raise ValueError(f"{label} recorded source results exceed scheduled budget")
        exposure[(variant, task)] = {
            "task_id": task,
            "scheduled_slots": scheduled,
            "successful_sources": counts["successful_sources"],
            "failed_sources": counts["failed_sources"],
            "accounted_source_results": accounted,
            "capacity_not_accounted_for_by_source_results": scheduled - accounted,
            "search_calls": counts["search_calls"],
            "model_calls": counts["model_calls"],
            "total_tokens": counts["total_tokens"],
        }

    metrics = (
        "scheduled_slots", "successful_sources", "failed_sources",
        "accounted_source_results", "capacity_not_accounted_for_by_source_results",
        "search_calls", "model_calls", "total_tokens",
    )
    variant_summaries = {}
    for variant in audit.VARIANTS:
        cells = [exposure[(variant, task)] for task in tasks]
        totals = {field: sum(cell[field] for cell in cells) for field in metrics}
        slots = totals["scheduled_slots"]
        variant_summaries[variant] = {
            "n_reports": len(cells),
            "totals": totals,
            "means_per_report": {field: totals[field] / len(cells) for field in metrics},
            "recorded_successful_sources_per_scheduled_slot": (
                totals["successful_sources"] / slots
            ),
            "accounted_source_results_per_scheduled_slot": (
                totals["accounted_source_results"] / slots
            ),
            "reports_with_zero_successful_sources": sum(
                cell["successful_sources"] == 0 for cell in cells
            ),
            "reports_with_capacity_not_accounted_for": sum(
                cell["capacity_not_accounted_for_by_source_results"] > 0
                for cell in cells
            ),
            "all_task_exposures": cells,
        }

    contrasts = {}
    metric_names = {
        "scheduled_slots": "scheduled_slot_delta",
        "successful_sources": "successful_source_delta",
        "failed_sources": "failed_source_delta",
        "accounted_source_results": "accounted_source_result_delta",
        "capacity_not_accounted_for_by_source_results":
            "unaccounted_capacity_delta",
        "search_calls": "search_call_delta",
        "model_calls": "model_call_delta",
        "total_tokens": "total_token_delta",
    }
    for left, right, name in CONTRASTS:
        per_task = []
        for task in tasks:
            left_cell, right_cell = exposure[(left, task)], exposure[(right, task)]
            per_task.append({
                "task_id": task,
                **{
                    out: right_cell[field] - left_cell[field]
                    for field, out in metric_names.items()
                },
            })
        success_deltas = [cell["successful_source_delta"] for cell in per_task]
        contrasts[name] = {
            "n_paired_tasks": len(per_task),
            "scheduled_slot_delta_per_task": (
                exposure[(right, tasks[0])]["scheduled_slots"]
                - exposure[(left, tasks[0])]["scheduled_slots"]
            ),
            "mean_successful_source_delta": sum(success_deltas) / len(per_task),
            "more_successful_sources_right": sum(d > 0 for d in success_deltas),
            "fewer_successful_sources_right": sum(d < 0 for d in success_deltas),
            "equal_successful_sources": sum(d == 0 for d in success_deltas),
            "all_task_exposure_differences": per_task,
        }
    return {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "status": "post_hoc_exploratory_retrieval_exposure_only",
        "task_ids": tasks,
        "variant_summaries": variant_summaries,
        "frozen_contrast_exposure_comparisons": contrasts,
        "confirmatory_inference_changed": False,
        "statistical_tests_added": False,
        "human_validation_performed": False,
        "original_execution_authenticated": False,
        "interpretation": (
            "Scheduled source slots are treatment settings; successful and "
            "failed source results are retrospective exported counts. Their "
            "sum may be less than the budget and the residual is not proof "
            "of skipped attempts. Search calls, model calls and tokens are "
            "additional resource exposure, not equal-total-compute controls. "
            "No claim outcomes, causal effects or new p-values were computed."
        ),
    }


def run_verified() -> dict:
    """Production path: audit both published CSVs, then pin the captured ledger."""
    audit.audit_frozen_csv_inputs()
    captured, rows = audit._read_csv(
        audit.DEFAULT_MAIN, label="published frozen treatment ledger"
    )
    observed_sha = hashlib.sha256(captured).hexdigest()
    if observed_sha != audit.FROZEN_MAIN_CSV_SHA256:
        raise ValueError("frozen treatment CSV changed after provenance preflight")
    result = summarize_retrieval_exposure(rows)
    if result["task_ids"] != [f"main-{n:02d}" for n in range(1, 11)]:
        raise ValueError("frozen task identities changed after provenance preflight")
    result["verified_published_treatment_csv_sha256"] = observed_sha
    result["published_evaluator_csv_sha256_reference"] = (
        audit.FROZEN_SUPPORT_CSV_SHA256
    )
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
        parser.exit(1, f"RETRIEVAL EXPOSURE DIAGNOSTIC: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
