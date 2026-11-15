"""Outcome-blind category/order diagnostic for a separately frozen prospective plan.

Replays the exact manifest-bound Williams schedule before describing category
margins. Neither category balance nor this report proves task selection
independence, prospective registration, execution, or a treatment effect.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import plan_counterbalanced_replication as design
from scripts import verify_counterbalanced_replication_plan as verifier


def audit_category_order(
    task_manifest: bytes,
    plan_file: bytes,
    *,
    expected_plan_file_sha256: str | None = None,
    expected_task_manifest_sha256: str | None = None,
) -> dict:
    """Report position and pair-order margins per *frozen* task category.

    The original schedule and receipt are never changed. Verify the submitted
    receipt against the actual task-manifest bytes before using its orders.
    """
    verified = verifier.verify_plan(
        task_manifest,
        plan_file,
        expected_plan_file_sha256=expected_plan_file_sha256,
        expected_task_manifest_sha256=expected_task_manifest_sha256,
    )
    plan = design.build_plan(task_manifest)
    # build_plan has already rejected duplicate keys, malformed JSON, unsafe
    # categories, duplicate task IDs, and all unsupported schema fields.
    payload = json.loads(task_manifest.decode("utf-8"))
    task_categories = {task["id"]: task["category"] for task in payload["tasks"]}
    pair_names = tuple(
        (left, right, f"{left}_before_{right}")
        for index, left in enumerate(design.VARIANTS)
        for right in design.VARIANTS[index + 1:]
    )
    # Direction matters: a transition into P6V is not interchangeable with
    # a transition out of P6V. Global Williams carryover balance can conceal
    # concentration within a frozen question category.
    adjacency_names = {
        (before, after): f"{before}_to_{after}"
        for before in design.VARIANTS
        for after in design.VARIANTS
        if before != after
    }
    by_category: dict[str, dict] = {}
    for row in plan["schedule"]:
        category = task_categories[row["task_id"]]
        entry = by_category.setdefault(
            category,
            {
                "category": category,
                "task_count": 0,
                "position_counts": {
                    variant: [0] * len(design.VARIANTS)
                    for variant in design.VARIANTS
                },
                "pairwise_precedence_counts": {
                    name: 0 for _, _, name in pair_names
                },
                "directed_adjacent_transition_counts": {
                    name: 0 for name in adjacency_names.values()
                },
            },
        )
        entry["task_count"] += 1
        positions = {variant: position for position, variant in enumerate(row["arm_order"])}
        for variant, position in positions.items():
            entry["position_counts"][variant][position] += 1
        for left, right, name in pair_names:
            entry["pairwise_precedence_counts"][name] += int(
                positions[left] < positions[right]
            )
        for before, after in zip(row["arm_order"], row["arm_order"][1:]):
            entry["directed_adjacent_transition_counts"][
                adjacency_names[(before, after)]
            ] += 1

    strata = []
    for category in sorted(by_category):
        entry = by_category[category]
        count = entry["task_count"]
        entry["max_position_spread"] = max(
            max(values) - min(values)
            for values in entry["position_counts"].values()
        )
        # Absolute difference in the two precedence directions for each
        # unordered pair. A gap of one is unavoidable with odd stratum size.
        entry["max_pairwise_precedence_direction_gap"] = max(
            abs(2 * before - count)
            for before in entry["pairwise_precedence_counts"].values()
        )
        adjacency = entry["directed_adjacent_transition_counts"]
        entry["total_directed_adjacent_transitions"] = sum(adjacency.values())
        if entry["total_directed_adjacent_transitions"] != (
            count * (len(design.VARIANTS) - 1)
        ):
            raise design.DesignError("category adjacent-transition total disagrees with task count")
        entry["max_directed_adjacent_transition_count_spread"] = (
            max(adjacency.values()) - min(adjacency.values())
        )
        strata.append(entry)

    if sum(row["task_count"] for row in strata) != plan["task_count"]:
        raise design.DesignError("category task counts disagree with the frozen plan")
    for variant in design.VARIANTS:
        if [
            sum(row["position_counts"][variant][slot] for row in strata)
            for slot in range(len(design.VARIANTS))
        ] != plan["position_counts"][variant]:
            raise design.DesignError("category position counts disagree with the frozen plan")
    for _, _, pair_name in pair_names:
        if sum(
            row["pairwise_precedence_counts"][pair_name] for row in strata
        ) != plan["pairwise_precedence_counts"][pair_name]:
            raise design.DesignError("category pair-order counts disagree with the frozen plan")

    # Independent of aggregate position/precedence margins: verify every
    # directed neighboring pair against the exact, manifest-replayed schedule.
    global_adjacency = design._directed_carryover_counts(plan["schedule"])
    for pair, name in adjacency_names.items():
        if sum(
            row["directed_adjacent_transition_counts"][name] for row in strata
        ) != global_adjacency[pair]:
            raise design.DesignError(
                "category directed adjacency disagrees with the frozen plan"
            )

    # A balanced *within-task* Williams schedule does not randomize the
    # order of the tasks themselves. Under the prospective task-major
    # execution contract, consecutive categories can coincide with a shared
    # web/provider time window. Audit the exact manifest-bound row order
    # without relabeling tasks, editing the plan, or looking at outcomes.
    ordered_categories = [
        task_categories[row["task_id"]] for row in plan["schedule"]
    ]
    boundaries = list(zip(ordered_categories, ordered_categories[1:]))
    same_category_boundaries = sum(
        before == after for before, after in boundaries
    )
    for entry in strata:
        category = entry["category"]
        indices = [
            index for index, label in enumerate(ordered_categories, start=1)
            if label == category
        ]
        if len(indices) != entry["task_count"]:
            raise design.DesignError("category task chronology disagrees with frozen plan")
        entry["first_task_index"] = indices[0]
        entry["last_task_index"] = indices[-1]
        entry["first_half_task_count"] = sum(
            index <= plan["task_count"] // 2 for index in indices
        )
        entry["second_half_task_count"] = (
            entry["task_count"] - entry["first_half_task_count"]
        )
        entry["adjacent_same_category_task_boundaries"] = sum(
            before == category and after == category
            for before, after in boundaries
        )
        current_run = longest_run = 0
        for label in ordered_categories:
            current_run = current_run + 1 if label == category else 0
            longest_run = max(longest_run, current_run)
        entry["longest_consecutive_task_run"] = longest_run
    if sum(
        entry["adjacent_same_category_task_boundaries"] for entry in strata
    ) != same_category_boundaries:
        raise design.DesignError("category task chronology boundary totals disagree")
    if sum(entry["first_half_task_count"] for entry in strata) != plan["task_count"] // 2:
        raise design.DesignError("category first-half task totals disagree")

    # Global Williams margins can mask position and precedence concentration
    # in early versus late *planned task-major* execution. Split the immutable
    # ten-row schedule into equal contiguous windows, without moving any task
    # or using measured outcomes. This is exposure accounting, not a test of
    # temporal drift or evidence that the plan was actually executed.
    split = plan["task_count"] // 2
    chronological_windows = []
    for window_name, start, stop in (
        ("first_half", 0, split),
        ("second_half", split, plan["task_count"]),
    ):
        rows = plan["schedule"][start:stop]
        positions_by_arm = {
            variant: [0] * len(design.VARIANTS)
            for variant in design.VARIANTS
        }
        precedence_by_pair = {name: 0 for _, _, name in pair_names}
        for row in rows:
            arm_positions = {
                arm: slot for slot, arm in enumerate(row["arm_order"])
            }
            for arm, slot in arm_positions.items():
                positions_by_arm[arm][slot] += 1
            for left, right, name in pair_names:
                precedence_by_pair[name] += int(
                    arm_positions[left] < arm_positions[right]
                )
        chronological_windows.append({
            "window": window_name,
            "task_index_range_1based_inclusive": [start + 1, stop],
            "task_count": len(rows),
            "position_counts": positions_by_arm,
            "pairwise_precedence_counts": precedence_by_pair,
            "max_position_spread": max(
                max(slots) - min(slots)
                for slots in positions_by_arm.values()
            ),
            "max_pairwise_precedence_direction_gap": max(
                abs(2 * count - len(rows))
                for count in precedence_by_pair.values()
            ),
        })
    early, late = chronological_windows
    for arm in design.VARIANTS:
        for slot in range(len(design.VARIANTS)):
            if (
                early["position_counts"][arm][slot]
                + late["position_counts"][arm][slot]
                != plan["position_counts"][arm][slot]
            ):
                raise design.DesignError(
                    "chronological half position totals disagree with frozen plan"
                )
    for _, _, pair_name in pair_names:
        if (
            early["pairwise_precedence_counts"][pair_name]
            + late["pairwise_precedence_counts"][pair_name]
            != plan["pairwise_precedence_counts"][pair_name]
        ):
            raise design.DesignError(
                "chronological half precedence totals disagree with frozen plan"
            )
    between_half_position_count_gap = max(
        abs(early["position_counts"][arm][slot]
            - late["position_counts"][arm][slot])
        for arm in design.VARIANTS
        for slot in range(len(design.VARIANTS))
    )
    between_half_precedence_count_gap = max(
        abs(early["pairwise_precedence_counts"][name]
            - late["pairwise_precedence_counts"][name])
        for _, _, name in pair_names
    )

    return {
        "schema_version": 1,
        "classification": "prospective_outcome_blind_category_order_diagnostic_only",
        "task_set_id": verified["task_set_id"],
        "source_manifest_sha256": verified["source_manifest_sha256"],
        "design_receipt_sha256": verified["design_receipt_sha256"],
        "plan_file_sha256": verified["plan_file_sha256"],
        "supplied_plan_file_pin_matched": verified["supplied_plan_file_pin_matched"],
        "supplied_task_manifest_pin_matched": verified[
            "supplied_task_manifest_pin_matched"
        ],
        "task_count": plan["task_count"],
        "category_count": len(strata),
        "category_summaries": strata,
        "global_directed_adjacent_transition_counts": {
            name: global_adjacency[pair]
            for pair, name in adjacency_names.items()
        },
        "task_order_same_category_adjacent_boundaries": same_category_boundaries,
        "task_order_category_switch_boundaries": (
            len(boundaries) - same_category_boundaries
        ),
        "task_order_category_clustering_is_descriptive_only": True,
        "chronological_half_order_summaries": chronological_windows,
        "max_between_half_arm_position_count_gap": between_half_position_count_gap,
        "max_between_half_pairwise_precedence_count_gap": between_half_precedence_count_gap,
        "chronological_half_balance_is_descriptive_only": True,
        "actual_execution_timing_authenticated": False,
        "global_order_balance_does_not_guarantee_category_balance": True,
        "category_selection_or_executions_authenticated": False,
        "historical_2026_study_reanalyzed": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--expected-task-manifest-sha256")
    parser.add_argument("--expected-plan-file-sha256")
    args = parser.parse_args()
    try:
        result = audit_category_order(
            design.read_manifest(args.task_manifest),
            design.read_manifest(args.plan_file),
            expected_task_manifest_sha256=args.expected_task_manifest_sha256,
            expected_plan_file_sha256=args.expected_plan_file_sha256,
        )
    except design.DesignError as exc:
        parser.exit(2, f"PROSPECTIVE CATEGORY ORDER AUDIT: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
