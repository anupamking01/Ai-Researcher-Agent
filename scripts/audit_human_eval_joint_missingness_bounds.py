"""Exploratory shared-arm bounds for missing human-evaluation task pairs.

This is a post-freeze, outcome-blind *sensitivity* audit. No human ratings,
frozen estimates, or treatment/evaluator executions are generated or modified.
For real use, require independent source recomputation before reading analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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



def _feasible_completed_task_edge_bounds(
    arm_counts: list[int], fixed_edges: list[int | None], *, label: str,
) -> tuple[list[int], list[int]]:
    """Marginal endpoints after hypothetically completing all four reports to 2/2.

    Enumerate *possible observed rating sums*, not invented annotator scores.
    For count n, each integer sum n..5n is achievable with n genuine 1–5
    scores; count zero contributes an empty sum. A known adjacent difference
    constrains both report sums on the same task. Complete every missing
    rating at its permitted endpoint for the requested edge, respecting
    shared-arm observed sums. Bounds are separately attainable per edge,
    not necessarily all three at once.
    """
    if len(arm_counts) != 4 or len(fixed_edges) != 3 or any(
        type(n) is not int or n not in (0, 1, 2) for n in arm_counts
    ):
        raise ValueError(f"{label}: invalid original-rater counts or contrast chain")
    domains = [range(n, 5 * n + 1) if n else (0,) for n in arm_counts]
    lower = [None] * 3
    upper = [None] * 3
    for sums in product(*domains):
        if any(
            difference is not None and (
                arm_counts[i] == 0 or arm_counts[i + 1] == 0
                or 2 * (
                    sums[i + 1] * arm_counts[i]
                    - sums[i] * arm_counts[i + 1]
                ) != difference * arm_counts[i] * arm_counts[i + 1]
            )
            for i, difference in enumerate(fixed_edges)
        ):
            continue
        for i in range(3):
            # A fully completed report mean, doubled, is its two-rating
            # sum. Unknown ratings contribute integer values in [1,5].
            minimum = (
                sums[i + 1] + (2 - arm_counts[i + 1])
                - sums[i] - 5 * (2 - arm_counts[i])
            )
            maximum = (
                sums[i + 1] + 5 * (2 - arm_counts[i + 1])
                - sums[i] - (2 - arm_counts[i])
            )
            lower[i] = minimum if lower[i] is None else min(lower[i], minimum)
            upper[i] = maximum if upper[i] is None else max(upper[i], maximum)
    if any(value is None for value in lower):
        raise ValueError(
            f"{label}: hypothetical two-rater completion is inconsistent "
            "with the observed shared-arm score differences"
        )
    return lower, upper



def _validate_published_arm_denominators(
    analysis: dict, arms: list[str], dimension: str,
    report_counts: dict[str, list[int]], task_count: int,
) -> None:
    """Reconcile pair-level rater coverage against independent arm summaries.

    The same report enters two adjacent contrasts. Its original rating count
    must also agree with the per-arm analysis denominator and the raw-score
    histogram. No individual rating or treatment score is reconstructed.
    Counts are dimension-specific: an annotator may leave one rubric field
    unscored while completing another.
    """
    summaries = analysis.get("variant_summary")
    if type(summaries) is not dict or set(summaries) != set(arms):
        raise ValueError("joint missingness requires every frozen variant summary")
    for arm in arms:
        per_dimension = summaries[arm]
        if type(per_dimension) is not dict or set(per_dimension) != set(core.DIMS):
            raise ValueError(f"{arm}: incomplete frozen variant summary dimensions")
        record = per_dimension[dimension]
        if type(record) is not dict:
            raise ValueError(f"{arm}/{dimension}: invalid variant summary")
        counts = report_counts[arm]
        histogram = record.get("raw_score_distribution")
        if (
            type(histogram) is not dict
            or set(histogram) != {str(score) for score in range(1, 6)}
            or any(type(n) is not int or n < 0 for n in histogram.values())
        ):
            raise ValueError(f"{arm}/{dimension}: invalid raw-score distribution")
        if (
            type(record.get("n_reports_total")) is not int
            or record["n_reports_total"] != task_count
            or type(record.get("n_reports_scored")) is not int
            or record["n_reports_scored"] != sum(n > 0 for n in counts)
            or type(record.get("n_raw_scores")) is not int
            or record["n_raw_scores"] != sum(counts)
            or sum(histogram.values()) != sum(counts)
        ):
            raise ValueError(
                f"{arm}/{dimension}: published arm denominators disagree "
                "with shared-report rater coverage"
            )



def _possible_original_score_sums(
    counts: list[int], fixed_edges: list[int | None], *, label: str,
) -> list[set[int]]:
    """Project feasible original score sums on the four shared reports.

    The sums range over *possible* integer 1–5 ratings; this neither
    reconstructs individual human scores nor asserts that ratings exist.
    """
    options = [range(n, 5 * n + 1) if n else (0,) for n in counts]
    projected = [set() for _ in counts]
    for sums in product(*options):
        if any(
            edge is not None and (
                not counts[i] or not counts[i + 1]
                or 2 * (sums[i + 1] * counts[i] - sums[i] * counts[i + 1])
                != edge * counts[i] * counts[i + 1]
            )
            for i, edge in enumerate(fixed_edges)
        ):
            continue
        for target, value in zip(projected, sums):
            target.add(value)
    if any(not domain for domain in projected):
        raise ValueError(f"{label}: no jointly feasible original rating sums")
    return projected


def _raw_score_histogram_options(count: int, allowed_sums: set[int]) -> set[tuple[int, ...]]:
    """All raw 1–5 histograms for one zero-, one-, or two-rated report."""
    if count == 0:
        return {(0, 0, 0, 0, 0)}
    options = set()
    for first in range(1, 6):
        for second in (range(first, 6) if count == 2 else (0,)):
            if first + second not in allowed_sums:
                continue
            bins = [0] * 5
            bins[first - 1] += 1
            if count == 2:
                bins[second - 1] += 1
            options.add(tuple(bins))
    return options


def _validate_published_score_histograms(
    analysis: dict, arms: list[str], dimension: str,
    report_counts: dict[str, list[int]], score_domains: dict[str, list[set[int]]],
) -> None:
    """Require each arm's published histogram to be reachable across tasks.

    This is a *necessary* per-arm condition, not proof that the four separate
    arm histograms have one simultaneously feasible cross-arm assignment.
    The observed adjacent task differences still constrain each report's
    possible score sums through the same four-arm chain.
    """
    for arm in arms:
        histogram = analysis["variant_summary"][arm][dimension]["raw_score_distribution"]
        target = tuple(histogram[str(score)] for score in range(1, 6))
        reachable = {(0, 0, 0, 0, 0)}
        for task_index, (count, sums) in enumerate(
            zip(report_counts[arm], score_domains[arm], strict=True), start=1
        ):
            choices = _raw_score_histogram_options(count, sums)
            if not choices:
                raise ValueError(
                    f"{arm}/{dimension}: no possible original raw scores for task {task_index}"
                )
            updated = set()
            for current in reachable:
                for increment in choices:
                    vector = tuple(a + b for a, b in zip(current, increment))
                    if all(a <= b for a, b in zip(vector, target)):
                        updated.add(vector)
            if not updated:
                raise ValueError(
                    f"{arm}/{dimension}: published score histogram cannot match "
                    f"task differences and rater coverage by task {task_index}"
                )
            reachable = updated
        if target not in reachable:
            raise ValueError(
                f"{arm}/{dimension}: published score histogram cannot match "
                "task differences and rater coverage"
            )


def _arm_total_doubled_mean_bounds(
    histogram: dict[str, int], counts: list[int],
) -> tuple[int, int]:
    """Conservative aggregate score bounds from raw bins and rater coverage.

    Twice the sum of observed report means equals the raw score total plus
    the sum of scores assigned to singly rated reports. To avoid inferring
    which raw score belonged to which report, bound that singleton subtotal
    by choosing the smallest or largest available scores. Completely
    unrated reports contribute hypothetical doubled means of 2..10.
    """
    raw_scores = [
        score for score in range(1, 6)
        for _ in range(histogram[str(score)])
    ]
    n_single = sum(count == 1 for count in counts)
    n_missing = sum(count == 0 for count in counts)
    raw_total = sum(raw_scores)
    low_single = sum(raw_scores[:n_single])
    high_single = sum(raw_scores[-n_single:]) if n_single else 0
    return (
        raw_total + low_single + 2 * n_missing,
        raw_total + high_single + 10 * n_missing,
    )


def _possible_singleton_rating_totals(
    histogram: dict[str, int], singleton_reports: int,
) -> set[int]:
    """Conservatively select the original scores from one-rated reports.

    Exactly one raw rating belongs to each singleton report, while the
    remaining ratings are from double-rated reports. The published histogram
    omits report identity, so enumerate every possible singleton subset sum
    without reconstructing or assigning scores to any individual report.
    """
    reachable = {(0, 0)}
    for score in range(1, 6):
        next_reachable = set()
        for used, total in reachable:
            for taken in range(min(histogram[str(score)], singleton_reports - used) + 1):
                next_reachable.add((used + taken, total + score * taken))
        reachable = next_reachable
    return {total for used, total in reachable if used == singleton_reports}


def _validate_published_report_means(
    analysis: dict, arms: list[str], dimension: str,
    report_counts: dict[str, list[int]],
) -> None:
    """Check descriptive report means against independent original-score bins.

    If S is the sum of all raw scores and T is the sum of the ratings
    belonging to singly scored reports, twice the sum of scored report
    means is S + T. Double-rated reports contribute their original raw
    sum; singly rated reports contribute twice their one score. Missing
    reports are excluded from the published mean, not imputed as zero.
    This subset-sum test is necessary, not sufficient for a per-task joint
    score assignment respecting the observed paired differences.
    """
    for arm in arms:
        record = analysis["variant_summary"][arm][dimension]
        observed_counts = report_counts[arm]
        n_scored = sum(count > 0 for count in observed_counts)
        reported = record.get("mean_report_score")
        if not n_scored:
            if reported is not None:
                raise ValueError(
                    f"{arm}/{dimension}: published report mean requires scored reports"
                )
            continue
        if (
            type(reported) not in (int, float)
            or not math.isfinite(reported)
            or not 1 <= reported <= 5
        ):
            raise ValueError(f"{arm}/{dimension}: invalid published report mean")
        histogram = record["raw_score_distribution"]
        raw_total = sum(score * histogram[str(score)] for score in range(1, 6))
        n_single = sum(count == 1 for count in observed_counts)
        possible = _possible_singleton_rating_totals(histogram, n_single)
        if not any(
            math.isclose(reported * (2 * n_scored), raw_total + subtotal,
                         rel_tol=0, abs_tol=1e-10)
            for subtotal in possible
        ):
            raise ValueError(
                f"{arm}/{dimension}: published report mean cannot arise from "
                "the raw-score histogram and original-rater coverage"
            )


def _validate_cross_arm_published_report_means(
    analysis: dict, arms: list[str], dimension: str,
    report_counts: dict[str, list[int]],
    task_edge_bounds: dict[str, list[int]],
) -> None:
    """Check published arm means against the *same* task-paired differences.

    For each arm, the observed mean fixes the sum of doubled report means
    over scored reports. Every genuinely unscored report may contribute any
    doubled value from 2 to 10. Comparing the resulting cross-arm interval
    with the independently computed task-edge envelope is a necessary gate.
    This does not impute missing ratings or assert joint histogram feasibility.
    """
    totals = {}
    for arm in arms:
        counts = report_counts[arm]
        scored = sum(count > 0 for count in counts)
        missing = len(counts) - scored
        reported = analysis["variant_summary"][arm][dimension]["mean_report_score"]
        observed_total = 2 * scored * reported if scored else 0
        totals[arm] = (
            observed_total + 2 * missing,
            observed_total + 10 * missing,
        )
    # Preserve serialization rounding safety without allowing a material
    # discrepancy on the half-point 1..5 rating lattice.
    tolerance = 1e-9
    for left, right, name in core.CONTRASTS:
        task_min, task_max = task_edge_bounds[name]
        mean_min = totals[right][0] - totals[left][1]
        mean_max = totals[right][1] - totals[left][0]
        if task_max < mean_min - tolerance or mean_max < task_min - tolerance:
            raise ValueError(
                f"{name}/{dimension}: published cross-arm report means "
                "contradict the paired task-difference bounds"
            )


def _validate_cross_arm_histogram_aggregates(
    analysis: dict, arms: list[str], dimension: str,
    report_counts: dict[str, list[int]],
    task_edge_bounds: dict[str, list[int]],
) -> None:
    """Reject aggregate raw-score totals incompatible with paired contrasts.

    Each contrast's task-level lower/upper sum (in doubled-score units) must
    overlap the conservative difference of its two arms' independently
    published raw-score histograms. This necessary check detects some
    cross-arm contradictions that every per-arm histogram DP alone accepts.
    The intervals need not admit a globally joint task-by-task assignment.
    """
    totals = {
        arm: _arm_total_doubled_mean_bounds(
            analysis["variant_summary"][arm][dimension]["raw_score_distribution"],
            report_counts[arm],
        )
        for arm in arms
    }
    for left, right, name in core.CONTRASTS:
        task_min, task_max = task_edge_bounds[name]
        histogram_min = totals[right][0] - totals[left][1]
        histogram_max = totals[right][1] - totals[left][0]
        if task_max < histogram_min or histogram_max < task_min:
            raise ValueError(
                f"{name}/{dimension}: published cross-arm raw-score histogram "
                "totals contradict the paired task-difference bounds"
            )


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
        completed_sums = {name: [0, 0] for _, _, name in core.CONTRASTS}
        report_counts = {arm: [] for arm in arms}
        score_domains = {arm: [] for arm in arms}
        missing_tasks = {name: {} for _, _, name in core.CONTRASTS}
        incomplete_rater_tasks = {name: {} for _, _, name in core.CONTRASTS}
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

            for arm in arms:
                report_counts[arm].append(arm_counts[arm])

            domains = [
                range(2, 11, 2) if arm_counts[arm] == 1 else range(2, 11)
                for arm in arms
            ]
            lows, highs = _feasible_task_edge_bounds(
                domains, fixed_edges, label=f"{dimension}/{task_id}",
            )
            completed_lows, completed_highs = _feasible_completed_task_edge_bounds(
                [arm_counts[arm] for arm in arms],
                fixed_edges,
                label=f"{dimension}/{task_id}",
            )
            projected = _possible_original_score_sums(
                [arm_counts[arm] for arm in arms],
                fixed_edges, label=f"{dimension}/{task_id}",
            )
            for arm, possible_sums in zip(arms, projected):
                score_domains[arm].append(possible_sums)

            for i, (left, right, name) in enumerate(core.CONTRASTS):
                sums[name][0] += lows[i]
                sums[name][1] += highs[i]
                completed_sums[name][0] += completed_lows[i]
                completed_sums[name][1] += completed_highs[i]
                if fixed_edges[i] is None:
                    missing_tasks[name][task_id] = [lows[i] / 2, highs[i] / 2]
                if arm_counts[left] < 2 or arm_counts[right] < 2:
                    incomplete_rater_tasks[name][task_id] = [
                        completed_lows[i] / 2, completed_highs[i] / 2,
                    ]

        _validate_published_arm_denominators(
            analysis, arms, dimension, report_counts, len(tasks),
        )
        _validate_published_score_histograms(
            analysis, arms, dimension, report_counts, score_domains,
        )
        _validate_cross_arm_histogram_aggregates(
            analysis, arms, dimension, report_counts, sums,
        )
        _validate_published_report_means(
            analysis, arms, dimension, report_counts,
        )
        _validate_cross_arm_published_report_means(
            analysis, arms, dimension, report_counts, sums,
        )

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
                "hypothetical_shared_arm_two_rater_all_task_bounds": [
                    value / (2 * len(tasks)) for value in completed_sums[name]
                ],
                "incomplete_original_rater_tasks": list(incomplete_rater_tasks[name]),
                "hypothetical_completed_task_difference_bounds": incomplete_rater_tasks[name],
            }

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "classification": "exploratory_shared_arm_missing_pair_sensitivity_only",
        "not_a_confidence_interval": True,
        "bounds_are_marginal_not_simultaneously_jointly_attainable": True,
        "no_imputation_or_new_ratings": True,
        "hypothetical_full_two_rater_completion_is_exploratory_only": True,
        "no_change_to_frozen_analysis": True,
        "raw_histogram_feasibility_is_necessary_not_sufficient": True,
        "cross_arm_histogram_aggregates_are_necessary_not_sufficient": True,
        "published_report_mean_feasibility_is_necessary_not_sufficient": True,
        "cross_arm_report_mean_consistency_is_necessary_not_sufficient": True,
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
