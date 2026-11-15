"""Exploratory shared-arm bounds for missing human-evaluation task pairs.

This is a post-freeze, outcome-blind *sensitivity* audit. No human ratings,
frozen estimates, or treatment/evaluator executions are generated or modified.
For real use, require independent source recomputation before reading analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import product
from pathlib import Path

from scripts import analyze_human_eval
from scripts import audit_human_eval_missing_pair_bounds as prior
from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verifier


def _feasible_task_edge_bounds(domains: list, fixed_edges: list, *, label: str) -> tuple:
    """Bound all three edges over one *shared* four-arm score assignment.

    Scores are doubled report means. A report with one observed integer score
    has an even doubled mean; two observed scores permit half-points. An
    entirely unobserved report can hypothetically average two integer scores,
    hence all doubled values 2..10. These are *possible* scores, not ratings.
    """
    lower = [None] * len(fixed_edges)
    upper = [None] * len(fixed_edges)
    for candidate in product(*domains):
        if any(
            value is not None and candidate[i + 1] - candidate[i] != value
            for i, value in enumerate(fixed_edges)
        ):
            continue
        for i in range(len(fixed_edges)):
            difference = candidate[i + 1] - candidate[i]
            lower[i] = difference if lower[i] is None else min(lower[i], difference)
            upper[i] = difference if upper[i] is None else max(upper[i], difference)
    if any(value is None for value in lower):
        raise ValueError(
            f"{label}: cross-contrast observed differences cannot arise from "
            "one shared set of integer 1–5 report ratings"
        )
    return lower, upper


def audit_joint_shared_arm_bounds(analysis: dict) -> dict:
    """Tighten missing-*pair* envelopes jointly within each task and dimension.

    Each contrast is reported marginally; the three separate marginal extrema
    need not all occur simultaneously. Existing frozen complete-case estimates,
    prior unconditioned missing-pair bounds, and rater-completion envelopes are
    unchanged. No missing score is imputed.
    """
    baseline = prior.audit_missing_pair_bounds(analysis)
    tasks = analysis["task_ids"]
    arms = [core.CONTRASTS[0][0]] + [right for _, right, _ in core.CONTRASTS]
    if len(arms) != 4 or len(set(arms)) != 4 or any(
        core.CONTRASTS[i][0] != arms[i] for i in range(3)
    ):
        raise ValueError("expected the frozen adjacent four-arm contrast chain")
    output = {name: {} for _, _, name in core.CONTRASTS}

    for dimension in core.DIMS:
        blocks = {}
        coverage = {}
        for left, right, name in core.CONTRASTS:
            block = analysis["paired_contrasts"][name][dimension]
            blocks[name] = block
            coverage[name] = prior._validate_rater_coverage(
                block["rater_coverage"],
                tasks=tasks,
                included=block["task_ids_included"],
                label=f"{name}/{dimension}",
            )

        sums = {name: [0, 0] for _, _, name in core.CONTRASTS}
        missing_tasks = {name: {} for _, _, name in core.CONTRASTS}
        for task_id in tasks:
            arm_counts = {}
            fixed_edges = []
            for left, right, name in core.CONTRASTS:
                left_count, right_count = coverage[name][task_id]
                for arm, count in ((left, left_count), (right, right_count)):
                    if arm in arm_counts and arm_counts[arm] != count:
                        raise ValueError(
                            f"{dimension}/{task_id}: cross-contrast shared-arm "
                            f"original-rater coverage mismatch for {arm}"
                        )
                    arm_counts[arm] = count
                if task_id in blocks[name]["task_ids_included"]:
                    fixed_edges.append(prior._halfpoint_twice(
                        blocks[name]["task_differences"][task_id],
                        label=f"{name}/{dimension}/{task_id}",
                    ))
                else:
                    fixed_edges.append(None)

            domains = [
                range(2, 11, 2) if arm_counts[arm] == 1 else range(2, 11)
                for arm in arms
            ]
            lows, highs = _feasible_task_edge_bounds(
                domains, fixed_edges, label=f"{dimension}/{task_id}",
            )
            for i, (_, _, name) in enumerate(core.CONTRASTS):
                sums[name][0] += lows[i]
                sums[name][1] += highs[i]
                if fixed_edges[i] is None:
                    missing_tasks[name][task_id] = [lows[i] / 2, highs[i] / 2]

        for _, _, name in core.CONTRASTS:
            bounds = [value / (2 * len(tasks)) for value in sums[name]]
            original = baseline["bounds_by_contrast_and_dimension"][name][dimension]
            wide = original["worst_case_all_task_mean_difference"]
            if bounds[0] < wide[0] - 1e-12 or bounds[1] > wide[1] + 1e-12:
                raise ValueError("joint bounds violate the conservative rubric envelope")
            if list(missing_tasks[name]) != original["missing_pair_tasks"]:
                raise ValueError("joint missing-task identity differs from frozen analysis")
            output[name][dimension] = {
                "observed_paired_tasks": original["observed_paired_tasks"],
                "missing_pair_tasks": original["missing_pair_tasks"],
                "prior_rubric_only_all_task_bounds": wide,
                "shared_arm_conditioned_all_task_bounds": bounds,
                "missing_task_difference_bounds": missing_tasks[name],
            }

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "classification": "exploratory_shared_arm_missing_pair_sensitivity_only",
        "not_a_confidence_interval": True,
        "bounds_are_marginal_not_simultaneously_jointly_attainable": True,
        "no_imputation_or_new_ratings": True,
        "no_change_to_frozen_analysis": True,
        "task_ids": tasks,
        "bounds_by_contrast_and_dimension": output,
    }


def audit_verified_bundle(
    output_root: Path,
    *,
    freeze_root: Path = core.FREEZE_ROOT,
    packet_root: Path = core.PACKET_ROOT,
) -> dict:
    """Fail closed unless the original human analysis independently recomputes."""
    verification = verifier.verify_bundle_against_inputs(
        Path(output_root),
        freeze_root=Path(freeze_root),
        packet_root=Path(packet_root),
    )
    if verification.get("independent_recomputation_verified") is not True:
        raise ValueError("independent frozen human-input recomputation is required")
    raw = freeze._capture_regular_input(
        Path(output_root) / analyze_human_eval.ANALYSIS_JSON,
        label="verified human-analysis JSON for joint missingness audit",
    )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != verification.get("canonical_analysis_sha256"):
        raise ValueError("verified human analysis changed before joint missingness audit")
    payload = verifier._load_json(raw, label="verified human-analysis JSON")
    result = audit_joint_shared_arm_bounds(payload)
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
        result = audit_verified_bundle(
            args.output_root, freeze_root=args.freeze_root, packet_root=args.packet_root,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"HUMAN SHARED-ARM MISSINGNESS: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
