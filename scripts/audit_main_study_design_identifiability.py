"""Exact, outcome-free rank audit of the historical VERA treatment/position design.

The source-linked September 11 runner iterated task -> D3,D6,P6,P6V. This
script proves the resulting treatment and within-task position columns are
aliased; it cannot authenticate execution times or estimate treatment effects.
No experiment files, observed scores, model APIs, or human ratings are read.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json

HISTORICAL_RUNNER_COMMIT = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
TASK_IDS = tuple(f"main-{number:02d}" for number in range(1, 11))
VARIANTS = ("D3", "D6", "P6", "P6V")
HISTORICAL_SCHEDULE = tuple(
    (task_id, variant_id) for task_id in TASK_IDS for variant_id in VARIANTS
)


class IdentifiabilityError(ValueError):
    """A proposed design is malformed or not a complete task/arm matrix."""


def exact_rank(rows: list[list[int]]) -> int:
    """Return exact rational column rank, without numerical tolerances."""
    if not rows or not rows[0]:
        raise IdentifiabilityError("design matrix must not be empty")
    width = len(rows[0])
    if any(len(row) != width or any(type(x) is not int for x in row) for row in rows):
        raise IdentifiabilityError("design matrix must be rectangular integer data")
    matrix = [[Fraction(value) for value in row] for row in rows]
    pivot_row = 0
    for column in range(width):
        pivot = next(
            (index for index in range(pivot_row, len(matrix)) if matrix[index][column]),
            None,
        )
        if pivot is None:
            continue
        matrix[pivot_row], matrix[pivot] = matrix[pivot], matrix[pivot_row]
        for row in range(pivot_row + 1, len(matrix)):
            if not matrix[row][column]:
                continue
            ratio = matrix[row][column] / matrix[pivot_row][column]
            for current in range(column, width):
                matrix[row][current] -= ratio * matrix[pivot_row][current]
        pivot_row += 1
        if pivot_row == len(matrix):
            break
    return pivot_row


def analyze_schedule(schedule: tuple[tuple[str, str], ...]) -> dict:
    """Compute rank for task, treatment, position, and their combined design.

    One observation is a task/arm cell. Within each task, the order in the
    supplied schedule defines positions 1..4. Rows are not measured outcomes.
    Complete, unique cells are required so rank comparisons use identical N.
    """
    if type(schedule) is not tuple or len(schedule) != len(HISTORICAL_SCHEDULE):
        raise IdentifiabilityError("a complete 40-cell schedule is required")
    by_task = {task_id: [] for task_id in TASK_IDS}
    seen = set()
    for cell in schedule:
        if (type(cell) is not tuple or len(cell) != 2
                or any(type(value) is not str for value in cell)):
            raise IdentifiabilityError("each schedule cell must be (task_id, variant_id)")
        task_id, variant_id = cell
        if task_id not in by_task or variant_id not in VARIANTS or cell in seen:
            raise IdentifiabilityError("unexpected or repeated task/variant cell")
        by_task[task_id].append(variant_id)
        seen.add(cell)
    if seen != set(HISTORICAL_SCHEDULE) or any(
        len(orders) != len(VARIANTS) for orders in by_task.values()
    ):
        raise IdentifiabilityError("incomplete or duplicated task/variant coverage")

    task_rows = []
    treatment_rows = []
    position_rows = []
    for task_id in TASK_IDS:
        for position, variant_id in enumerate(by_task[task_id], 1):
            task_rows.append([int(task_id == candidate) for candidate in TASK_IDS])
            treatment_rows.append([int(variant_id == arm) for arm in VARIANTS[1:]])
            position_rows.append([int(position == slot) for slot in range(2, 5)])

    # One-hot task intercepts span the overall intercept. The omitted arm
    # and position categories are the same baselines for both rank tests.
    task_rank = exact_rank(task_rows)
    arm_rank = exact_rank([task + arm for task, arm in zip(task_rows, treatment_rows)])
    position_rank = exact_rank([
        task + slot for task, slot in zip(task_rows, position_rows)
    ])
    joint_rank = exact_rank([
        task + arm + slot
        for task, arm, slot in zip(task_rows, treatment_rows, position_rows)
    ])
    all_same_order = all(tuple(orders) == VARIANTS for orders in by_task.values())
    return {
        "schema_version": 1,
        "classification": "structural_design_identifiability_only_no_outcomes",
        "historical_runner_commit": HISTORICAL_RUNNER_COMMIT,
        "task_count": len(TASK_IDS),
        "treatment_count": len(VARIANTS),
        "planned_cells": len(schedule),
        "each_task_has_one_of_each_treatment": True,
        "all_tasks_share_historical_fixed_order": all_same_order,
        "rank_task_intercepts": task_rank,
        "rank_task_plus_treatment": arm_rank,
        "rank_task_plus_position": position_rank,
        "rank_task_plus_treatment_plus_position": joint_rank,
        "additional_treatment_rank_after_position": joint_rank - position_rank,
        "additional_position_rank_after_treatment": joint_rank - arm_rank,
        "separate_treatment_and_position_effects_identifiable": (
            joint_rank == task_rank + 2 * (len(VARIANTS) - 1)
        ),
        "original_treatment_execution_authenticated": False,
        "time_varying_provider_conditions_observed": False,
        "causal_effects_identified": False,
        "treatments_or_evaluators_rerun": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = analyze_schedule(HISTORICAL_SCHEDULE)
    if not result["all_tasks_share_historical_fixed_order"]:
        parser.exit(2, "Historical schedule unexpectedly diverged from source-linked order\n")
    if (result["rank_task_intercepts"] != 10
            or result["rank_task_plus_treatment"] != 13
            or result["rank_task_plus_position"] != 13
            or result["rank_task_plus_treatment_plus_position"] != 13
            or result["additional_position_rank_after_treatment"] != 0
            or result["additional_treatment_rank_after_position"] != 0):
        parser.exit(2, "Historical design ranks differ from the fixed-order prediction\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
