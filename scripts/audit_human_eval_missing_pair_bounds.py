"""Exploratory bounds for missing *task pairs* in verified human analysis.

Run only against the already-published, independently recomputed human-analysis
bundle. No annotations, treatment data, bootstraps, or frozen analysis are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts import analyze_human_eval
from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verifier

RUBRIC_MIN = 1
RUBRIC_MAX = 5
MAX_PAIR_DIFFERENCE = RUBRIC_MAX - RUBRIC_MIN


def _halfpoint_twice(value: object, *, label: str) -> int:
    """The mean of up to two original integer ratings lies on a half-point grid."""
    if (
        type(value) not in (int, float)
        or not -MAX_PAIR_DIFFERENCE <= value <= MAX_PAIR_DIFFERENCE
        or not math.isfinite(value)
    ):
        raise ValueError(f"{label} must be a finite numerical 1–5 score difference")
    scaled = value * 2
    if scaled != int(scaled):
        raise ValueError(f"{label} is outside the valid 1–5 paired-difference lattice")
    return int(scaled)



def _validate_rater_coverage(coverage: object, *, tasks: list, included: list, label: str) -> dict:
    """Independently bind original-rater counts to every frozen task.

    Two observed report scores are required for a paired difference, but each
    report may have only one of the two planned independent ratings. Reject a
    fabricated or incomplete nine-cell coverage partition instead of silently
    treating omitted metadata as fully double-rated.
    """
    fields = {"count_by_rater_pair", "task_ids_by_rater_pair"}
    cells = set(core.RATER_COVERAGE_CELLS)
    if type(coverage) is not dict or set(coverage) != fields:
        raise ValueError(f"{label} requires the frozen original-rater coverage")
    counts = coverage["count_by_rater_pair"]
    per_cell = coverage["task_ids_by_rater_pair"]
    if (
        type(counts) is not dict or set(counts) != cells
        or type(per_cell) is not dict or set(per_cell) != cells
    ):
        raise ValueError(f"{label} has incomplete original-rater coverage cells")
    by_task = {}
    included_set = set(included)
    for cell in core.RATER_COVERAGE_CELLS:
        ids = per_cell[cell]
        count = counts[cell]
        if (
            type(ids) is not list
            or any(type(task_id) is not str for task_id in ids)
            or ids != [task_id for task_id in tasks if task_id in ids]
            or type(count) is not int
            or count != len(ids)
        ):
            raise ValueError(f"{label} has inconsistent original-rater coverage: {cell}")
        left_count, right_count = map(int, cell.split("/"))
        for task_id in ids:
            if task_id in by_task:
                raise ValueError(f"{label} repeats task in original-rater coverage: {task_id}")
            if (task_id in included_set) != (left_count > 0 and right_count > 0):
                raise ValueError(f"{label} conflicts with paired inclusion: {task_id}")
            by_task[task_id] = (left_count, right_count)
    if set(by_task) != set(tasks):
        raise ValueError(f"{label} original-rater coverage omits frozen tasks")
    return by_task

def audit_missing_pair_bounds(analysis: dict) -> dict:
    """Bound the all-task mean by assigning each unobserved *pair* [-4, +4].

    Observed task differences are fixed. Any absent task pair is entirely
    unknown within the 1–5 rubric. This is deliberately conservative when
    one of its reports was actually scored. Partially scored *raters* on an
    included pair are NOT varied, and the frozen observed-score estimand is
    not replaced. These are identification bounds, not bootstrap intervals.
    """
    if type(analysis) is not dict or (
        analysis.get("study_id") != "budget-main-v1"
        or analysis.get("status") != "human_validation_analysis"
        or analysis.get("analysis_scope") != "complementary_not_main_confirmatory"
    ):
        raise ValueError("requires the frozen complementary human-analysis payload")
    tasks = analysis.get("task_ids")
    if (
        type(tasks) is not list or len(tasks) != 10
        or any(type(t) is not str or not t or t != t.strip() for t in tasks)
        or tasks != sorted(set(tasks))
        or type(analysis.get("n_tasks")) is not int
        or analysis["n_tasks"] != len(tasks)
    ):
        raise ValueError("human-analysis task inventory must be ten unique ordered IDs")
    if analysis.get("dimensions") != list(core.DIMS):
        raise ValueError("all five frozen rubric dimensions are required")
    expected_contrasts = {name for _, _, name in core.CONTRASTS}
    contrasts = analysis.get("paired_contrasts")
    if type(contrasts) is not dict or set(contrasts) != expected_contrasts:
        raise ValueError("all three frozen human contrasts are required")

    output = {}
    for _, _, name in core.CONTRASTS:
        dimensions = contrasts[name]
        if type(dimensions) is not dict or set(dimensions) != set(core.DIMS):
            raise ValueError(f"{name} must include every frozen rubric dimension")
        output[name] = {}
        for dimension in core.DIMS:
            block = dimensions[dimension]
            if type(block) is not dict:
                raise ValueError(f"{name}/{dimension} must be a paired-analysis record")
            included = block.get("task_ids_included")
            missing = block.get("missing_pair_tasks")
            diffs = block.get("task_differences")
            if (
                type(included) is not list or type(missing) is not list
                or type(diffs) is not dict
                or any(type(t) is not str for t in included + missing)
                or len(set(included + missing)) != len(tasks)
                or [t for t in tasks if t in included] != included
                or [t for t in tasks if t in missing] != missing
                or set(included) | set(missing) != set(tasks)
                or set(diffs) != set(included)
            ):
                raise ValueError(f"{name}/{dimension} has inconsistent pair identity")
            if type(block.get("n_pairs")) is not int or block["n_pairs"] != len(included):
                raise ValueError(f"{name}/{dimension} has inconsistent paired denominator")
            observed_twice = sum(
                _halfpoint_twice(diffs[t], label=f"{name}/{dimension}/{t}")
                for t in included
            )
            reported = block.get("mean_difference")
            if included:
                if (
                    type(reported) not in (int, float)
                    or not -MAX_PAIR_DIFFERENCE <= reported <= MAX_PAIR_DIFFERENCE
                    or not math.isfinite(reported)
                    or not math.isclose(
                        reported, observed_twice / (2 * len(included)),
                        rel_tol=0, abs_tol=1e-12,
                    )
                ):
                    raise ValueError(f"{name}/{dimension} observed paired mean disagrees")
            elif reported is not None:
                raise ValueError(f"{name}/{dimension} has a mean without paired observations")

            # Bind original-rater completeness independently of pair coverage.
            # A missing second rater can hypothetically shift its report mean
            # by at most 2 (one half of the 1–5 scale width). This is NOT a
            # revision of the frozen observed-score estimand.
            by_task = _validate_rater_coverage(
                block.get("rater_coverage"),
                tasks=tasks, included=included, label=f"{name}/{dimension}",
            )
            # Multiplying differences by 2 preserves exact half-point units.
            unknown = len(missing)
            lower = (observed_twice - 2 * MAX_PAIR_DIFFERENCE * unknown) / (2 * len(tasks))
            upper = (observed_twice + 2 * MAX_PAIR_DIFFERENCE * unknown) / (2 * len(tasks))
            completion_lower_twice = -2 * MAX_PAIR_DIFFERENCE * unknown
            completion_upper_twice = 2 * MAX_PAIR_DIFFERENCE * unknown
            missing_second_rater_slots = 0
            for task_id in included:
                left_count, right_count = by_task[task_id]
                gaps = (2 - left_count) + (2 - right_count)
                missing_second_rater_slots += gaps
                difference_twice = _halfpoint_twice(
                    diffs[task_id], label=f"{name}/{dimension}/{task_id}",
                )
                # Each unobserved second rating can move the pair difference
                # by at most two points. Clip to the physical [-4,+4] rubric
                # range; this conservative envelope need not be sharp without
                # the separately observed report scores.
                completion_lower_twice += max(
                    -2 * MAX_PAIR_DIFFERENCE, difference_twice - 4 * gaps,
                )
                completion_upper_twice += min(
                    2 * MAX_PAIR_DIFFERENCE, difference_twice + 4 * gaps,
                )
            completion_bounds = [
                completion_lower_twice / (2 * len(tasks)),
                completion_upper_twice / (2 * len(tasks)),
            ]
            output[name][dimension] = {
                "observed_paired_tasks": len(included),
                "missing_pair_tasks": missing,
                "missing_pair_count": unknown,
                "all_frozen_tasks": len(tasks),
                "observed_difference_sum": observed_twice / 2,
                "worst_case_all_task_mean_difference": [lower, upper],
                "bound_collapses_to_observed_mean": unknown == 0,
                "unobserved_second_rater_slots_on_included_pairs": missing_second_rater_slots,
                "hypothetical_two_rater_completion_bounds": completion_bounds,
                "completion_bounds_collapse_to_observed_mean": (
                    unknown == 0 and missing_second_rater_slots == 0
                ),
            }
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "classification": "exploratory_human_missing_task_pair_bounds_only",
        "not_a_confidence_interval": True,
        "no_imputation_or_edited_frozen_analysis": True,
        "partially_observed_raters_on_included_pairs_are_held_fixed": True,
        "hypothetical_two_rater_completion_is_exploratory_only": True,
        "hypothetical_completion_changes_no_frozen_scores": True,
        "ratings_generated": False,
        "hypothesis_tests_performed": False,
        "task_ids": tasks,
        "bounds_by_contrast_and_dimension": output,
    }


def audit_verified_bundle(
    output_root: Path,
    *,
    freeze_root: Path = core.FREEZE_ROOT,
    packet_root: Path = core.PACKET_ROOT,
) -> dict:
    """Gate an ancillary audit on full independent source recomputation.

    Match the exact independently verified canonical JSON digest before
    parsing; observing this equality is not a claim about immutable storage
    after the read. This intentionally fails before real ratings exist.
    """
    output_root = Path(output_root)
    verification = verifier.verify_bundle_against_inputs(
        output_root,
        freeze_root=Path(freeze_root),
        packet_root=Path(packet_root),
    )
    if verification.get("independent_recomputation_verified") is not True:
        raise ValueError("human-analysis independent input recomputation is required")
    raw = freeze._capture_regular_input(
        output_root / analyze_human_eval.ANALYSIS_JSON,
        label="verified human-analysis JSON for exploratory missingness audit",
    )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != verification.get("canonical_analysis_sha256"):
        raise ValueError("verified human-analysis JSON changed before missingness audit")
    payload = verifier._load_json(raw, label="verified human-analysis JSON")
    result = audit_missing_pair_bounds(payload)
    result["verified_source"] = {
        "canonical_analysis_sha256": digest,
        "independent_recomputation_verified": True,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=analyze_human_eval.OUTPUT_ROOT)
    parser.add_argument("--freeze-root", type=Path, default=core.FREEZE_ROOT)
    parser.add_argument("--packet-root", type=Path, default=core.PACKET_ROOT)
    args = parser.parse_args()
    try:
        payload = audit_verified_bundle(
            args.output_root,
            freeze_root=args.freeze_root,
            packet_root=args.packet_root,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"HUMAN MISSING-PAIR BOUNDS: FAIL: {exc}\n")
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
