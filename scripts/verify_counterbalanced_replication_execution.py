"""Read-only audit of a future VERA counterbalanced replication's execution log.

Checks recorded task/arm order and UTC chronology against a recomputed,
manifest-bound *prospective* plan. Never runs a treatment or evaluator.
A passing self-reported log is not independent evidence that execution occurred.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from scripts import plan_counterbalanced_replication as design
from scripts import verify_counterbalanced_replication_plan as plan_verify

MAX_EXECUTION_LOG_BYTES = 128 * 1024
LOG_CLASSIFICATION = "prospective_replication_recorded_chronology_only"
LOG_FIELDS = frozenset({
    "schema_version", "classification", "task_set_id",
    "source_manifest_sha256", "plan_file_sha256",
    "started_at_utc", "finished_at_utc", "events",
})
EVENT_FIELDS = frozenset({
    "task_id", "variant", "run_id", "status",
    "started_at_utc", "finished_at_utc",
})
STATUSES = ("completed", "failed", "timeout", "cancelled", "not_started")
_UTC_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|\+00:00)"
)
_SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
# Run IDs become report/trace path components. Reject aliases that collide on
# ordinary case-insensitive filesystems or are reserved as Windows devices.
_WINDOWS_DEVICE_NAME = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", re.I)
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _timestamp(value: object, description: str) -> datetime:
    """Require explicit UTC seconds, with optional fractional seconds."""
    if type(value) is not str or _UTC_PATTERN.fullmatch(value) is None:
        raise design.DesignError(f"{description} must be an explicit UTC ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise design.DesignError(f"{description} is not a real UTC timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise design.DesignError(f"{description} must use UTC")
    return parsed


def _portable_run_id_key(value: object) -> str | None:
    """Return a portable filesystem identity, or reject an unsafe run path.

    On Windows, CON.json and CON.txt are both reserved device names, and
    trailing dots disappear from directory names. On common Windows/macOS
    volumes, case-only differences can select the same report/trace path.
    This is identifier validation, not proof that a run actually occurred.
    """
    if type(value) is not str or _SAFE_RUN_ID.fullmatch(value) is None:
        return None
    if value.endswith(".") or _WINDOWS_DEVICE_NAME.fullmatch(value.split(".", 1)[0]):
        return None
    return value.casefold()


def _check_pin(pin: str | None, *, label: str, actual: str) -> bool:
    if pin is None:
        return False
    if type(pin) is not str or _SHA256.fullmatch(pin) is None:
        raise design.DesignError(f"{label} must be 64 lowercase SHA-256 hex digits")
    if pin != actual:
        raise design.DesignError(f"{label} does not match exact supplied file bytes")
    return True


def audit_execution_log(
    task_manifest: bytes,
    plan_receipt: bytes,
    execution_log: bytes,
    *,
    expected_plan_file_sha256: str | None = None,
    expected_task_manifest_sha256: str | None = None,
    expected_execution_log_sha256: str | None = None,
) -> dict:
    """Verify *recorded* chronology; never certify real execution or outcomes.

    Pre-execution plan and post-execution log pins must be obtained from
    independently retained sources, not computed from candidate files at
    verification time, if they are cited as evidence of archival custody.
    """
    plan_verified = plan_verify.verify_plan(
        task_manifest, plan_receipt,
        expected_plan_file_sha256=expected_plan_file_sha256,
        expected_task_manifest_sha256=expected_task_manifest_sha256,
    )
    plan = design.build_plan(task_manifest)

    if (type(execution_log) is not bytes or
            not 0 < len(execution_log) <= MAX_EXECUTION_LOG_BYTES):
        raise design.DesignError("execution log bytes outside supported range")
    log_sha256 = hashlib.sha256(execution_log).hexdigest()
    log_pinned = _check_pin(
        expected_execution_log_sha256,
        label="expected execution-log SHA-256",
        actual=log_sha256,
    )
    try:
        log = json.loads(
            execution_log.decode("utf-8"),
            object_pairs_hook=design._distinct_keys,
            parse_constant=design._reject_nonfinite,
            parse_int=design._bounded_int,
            parse_float=design._bounded_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise design.DesignError("execution log is not unambiguous UTF-8 JSON") from exc
    if type(log) is not dict or set(log) != LOG_FIELDS:
        raise design.DesignError("execution log must use the exact audit schema")
    if type(log["schema_version"]) is not int or log["schema_version"] != 1:
        raise design.DesignError("execution log schema version must be integer 1")
    if log["classification"] != LOG_CLASSIFICATION or type(log["classification"]) is not str:
        raise design.DesignError("execution log has an invalid classification")
    for field, expected in (
        ("task_set_id", plan["task_set_id"]),
        ("source_manifest_sha256", plan["source_manifest_sha256"]),
        ("plan_file_sha256", plan_verified["plan_file_sha256"]),
    ):
        if type(log[field]) is not str or log[field] != expected:
            raise design.DesignError(f"execution log {field} differs from verified design")

    expected_cells = [
        (row["task_id"], variant)
        for row in plan["schedule"] for variant in row["arm_order"]
    ]
    events = log["events"]
    if type(events) is not list or len(events) != len(expected_cells):
        raise design.DesignError("execution log must retain all 40 planned cells")
    study_start = _timestamp(log["started_at_utc"], "study start")
    study_finish = _timestamp(log["finished_at_utc"], "study finish")
    if study_finish <= study_start:
        raise design.DesignError("study timestamps have invalid duration")

    previous_finish = study_start
    run_ids: set[str] = set()
    counts = {status: 0 for status in STATUSES}
    # Report arm-specific missingness and *recorded* paired coverage. A full
    # ledger can be mostly complete while missing one arm for several tasks.
    # These are claims in the coordinator log, never authenticated outcomes.
    status_counts_by_variant = {
        variant: {status: 0 for status in STATUSES}
        for variant in design.VARIANTS
    }
    completed_variants_by_task = {
        row["task_id"]: set() for row in plan["schedule"]
    }
    # Preserve only successfully completed, validated event start timestamps
    # for outcome-blind within-task time-separation diagnostics.
    completed_starts_by_task = {
        row["task_id"]: {} for row in plan["schedule"]
    }
    # Record elapsed wall-clock intervals for every attempted arm, even when
    # the attempt fails. Completed-only summaries must not silently include
    # timeouts, cancellations, or failed treatment runs.
    attempted_durations_by_variant = {arm: [] for arm in design.VARIANTS}
    completed_durations_by_variant = {arm: [] for arm in design.VARIANTS}
    # Within-task paired durations are needed to distinguish a treatment
    # difference from task mix when a sequential study is interrupted.
    attempted_durations_by_task = {
        row["task_id"]: {} for row in plan["schedule"]
    }
    # A balanced *planned* Williams schedule need not remain balanced among
    # actually attempted or completed cells after interruption/attrition.
    slot_keys = ("1", "2", "3", "4")
    attempted_position_counts_by_variant = {
        arm: {position: 0 for position in slot_keys}
        for arm in design.VARIANTS
    }
    completed_position_counts_by_variant = {
        arm: {position: 0 for position in slot_keys}
        for arm in design.VARIANTS
    }
    # Keep every status (including an unstarted suffix) so immediate-predecessor
    # exposure can be distinguished from successful adjacent pairs.
    status_by_task = {row["task_id"]: {} for row in plan["schedule"]}
    # The manifest has already passed strict validation in build_plan. Its
    # frozen category labels can reveal order/attrition imbalance within
    # a topic even when the pooled Williams position counts are balanced.
    # Preserve the exact coordinator-supplied labels; never recategorize
    # tasks after seeing treatment outcomes.
    frozen_category_by_task = {
        task["id"]: task["category"]
        for task in json.loads(task_manifest.decode("utf-8"))["tasks"]
    }
    category_position_exposure = {
        category: {
            "task_count": sum(
                value == category for value in frozen_category_by_task.values()
            ),
            **{
                scope: {
                    arm: {str(slot): 0 for slot in range(1, 5)}
                    for arm in design.VARIANTS
                }
                for scope in ("planned", "attempted", "completed")
            },
        }
        for category in sorted(set(frozen_category_by_task.values()))
    }
    unstarted_suffix = False
    for index, (event, (task_id, variant)) in enumerate(
        zip(events, expected_cells, strict=True), start=1
    ):
        if type(event) is not dict or set(event) != EVENT_FIELDS:
            raise design.DesignError(f"event {index} does not use the exact event schema")
        if (type(event["task_id"]) is not str or event["task_id"] != task_id or
                type(event["variant"]) is not str or event["variant"] != variant):
            raise design.DesignError(
                f"event {index} violates the frozen task-major treatment schedule"
            )
        status = event["status"]
        if type(status) is not str or status not in counts:
            raise design.DesignError(f"event {index} has an unknown status")
        status_by_task[task_id][variant] = status
        slot = str((index - 1) % len(design.VARIANTS) + 1)
        category_exposure = category_position_exposure[frozen_category_by_task[task_id]]
        category_exposure["planned"][variant][slot] += 1
        if status != "not_started":
            category_exposure["attempted"][variant][slot] += 1
        if status == "completed":
            category_exposure["completed"][variant][slot] += 1
        if status == "not_started":
            # A halted sequential study retains every unattempted planned
            # cell without inventing a run identifier or execution interval.
            if any(event[field] is not None for field in (
                "run_id", "started_at_utc", "finished_at_utc"
            )):
                raise design.DesignError(
                    f"event {index} not_started requires null run ID and timestamps"
                )
            unstarted_suffix = True
            counts[status] += 1
            status_counts_by_variant[variant][status] += 1
            continue
        if unstarted_suffix:
            raise design.DesignError(
                f"event {index} records an attempt after a not_started suffix"
            )
        run_id = event["run_id"]
        portable_run_key = _portable_run_id_key(run_id)
        if portable_run_key is None or portable_run_key in run_ids:
            raise design.DesignError(f"event {index} has an unsafe or duplicate run ID")
        run_ids.add(portable_run_key)
        attempted_position_counts_by_variant[variant][slot] += 1
        # Attempted failures/timeouts/cancellations remain visible. Never
        # conceal them as unattempted work or cherry-pick favorable reruns.
        counts[status] += 1
        status_counts_by_variant[variant][status] += 1
        if status == "completed":
            completed_variants_by_task[task_id].add(variant)
            completed_position_counts_by_variant[variant][slot] += 1
        started = _timestamp(event["started_at_utc"], f"event {index} start")
        finished = _timestamp(event["finished_at_utc"], f"event {index} finish")
        if started < previous_finish or finished <= started:
            raise design.DesignError(
                f"event {index} has overlapping or nonpositive recorded chronology"
            )
        if finished > study_finish:
            raise design.DesignError(f"event {index} finishes outside study window")
        elapsed = finished - started
        elapsed_us = (
            (elapsed.days * 86400 + elapsed.seconds) * 1_000_000
            + elapsed.microseconds
        )
        attempted_durations_by_variant[variant].append(elapsed_us)
        attempted_durations_by_task[task_id][variant] = elapsed_us
        if status == "completed":
            completed_durations_by_variant[variant].append(elapsed_us)
        previous_finish = finished
        if status == "completed":
            completed_starts_by_task[task_id][variant] = started

    if counts["not_started"] == len(events):
        raise design.DesignError(
            "execution log has no attempted cells; use the design-only verifier"
        )

    # Count *logged* completed pairs by task, not favorable outcomes or
    # non-missing score observations. Do not treat these as an authorization
    # to run confirmatory inference without authenticated source artifacts.
    # Every contrast is named <left>_minus_<right>.  Use that operand
    # orientation for both direction counts and timing strata; swapping
    # sides would silently invert the interpretation under attrition.
    primary_pairs = {
        "D6_minus_D3": ("D6", "D3"),
        "P6_minus_D6": ("P6", "D6"),
        "P6V_minus_P6": ("P6V", "P6"),
    }
    completed_pair_task_counts = {
        name: sum(
            all(arm in completed for arm in pair)
            for completed in completed_variants_by_task.values()
        )
        for name, pair in primary_pairs.items()
    }
    # The 5:5 pairwise-precedence balance is a property of the full design,
    # not necessarily of the actually completed pairs. Report both directions
    # only for jointly completed task pairs; no outcome values are consulted.
    completed_pair_order_counts = {
        name: {"left_before_right": 0, "right_before_left": 0}
        for name in primary_pairs
    }
    pair_start_separations_us = {
        name: {"left_before_right": [], "right_before_left": []}
        for name in primary_pairs
    }
    for row in plan["schedule"]:
        completed = completed_variants_by_task[row["task_id"]]
        for name, (left, right) in primary_pairs.items():
            if left not in completed or right not in completed:
                continue
            direction = (
                "left_before_right"
                if row["arm_order"].index(left) < row["arm_order"].index(right)
                else "right_before_left"
            )
            completed_pair_order_counts[name][direction] += 1
            starts = completed_starts_by_task[row["task_id"]]
            # Use integer microseconds rather than floating-point total_seconds()
            # so fractional UTC timestamps retain exact subsecond custody.
            delta = abs(starts[right] - starts[left])
            elapsed_us = (
                (delta.days * 86400 + delta.seconds) * 1_000_000
                + delta.microseconds
            )
            pair_start_separations_us[name][direction].append(elapsed_us)
    completed_pair_start_separation_us = {
        name: {
            direction: {
                "count": len(values),
                "minimum_microseconds": min(values, default=None),
                "maximum_microseconds": max(values, default=None),
                "total_microseconds": sum(values),
            }
            for direction, values in direction_values.items()
        }
        for name, direction_values in pair_start_separations_us.items()
    }

    # First-order/adjacent exposure matters separately from pair precedence:
    # an arm that occurs earlier but is not adjacent is not its predecessor.
    # Planned and attempted adjacency describe schedule/exposure, while the
    # completed matrix requires BOTH arms logged completed. A failed or
    # timed-out predecessor still precedes a completed successor, but is not
    # silently treated as a completed treatment or an authenticated carryover.
    def blank_predecessor_matrix() -> dict[str, dict[str, int]]:
        return {
            arm: {predecessor: 0 for predecessor in design.VARIANTS if predecessor != arm}
            for arm in design.VARIANTS
        }

    planned_predecessors = blank_predecessor_matrix()
    attempted_predecessors = blank_predecessor_matrix()
    completed_predecessors = blank_predecessor_matrix()
    completed_after_noncompleted_predecessor = {arm: 0 for arm in design.VARIANTS}
    for row in plan["schedule"]:
        statuses = status_by_task[row["task_id"]]
        for predecessor, successor in zip(row["arm_order"], row["arm_order"][1:]):
            planned_predecessors[successor][predecessor] += 1
            if statuses[successor] != "not_started":
                # The sequential suffix rule guarantees the predecessor was attempted.
                attempted_predecessors[successor][predecessor] += 1
            if statuses[successor] == "completed":
                if statuses[predecessor] == "completed":
                    completed_predecessors[successor][predecessor] += 1
                else:
                    completed_after_noncompleted_predecessor[successor] += 1

    # Task-major execution also has one boundary between consecutive tasks.
    # Within-task Williams balance says nothing about these nine transitions:
    # a late arm of task N may immediately precede the first arm of task N+1.
    # Report them separately, allowing same-arm boundaries (unlike within-task
    # transitions); do not claim that these recorded adjacencies cause carryover.
    def blank_cross_task_matrix() -> dict[str, dict[str, int]]:
        return {
            successor: {predecessor: 0 for predecessor in design.VARIANTS}
            for successor in design.VARIANTS
        }

    cross_task_planned = blank_cross_task_matrix()
    cross_task_attempted = blank_cross_task_matrix()
    cross_task_completed = blank_cross_task_matrix()
    cross_task_completed_after_noncompleted = {
        arm: 0 for arm in design.VARIANTS
    }
    cross_task_attempted_gaps_us: list[int] = []
    # Preserve timing by the arm that resumes execution after each task boundary.
    # An aggregate maximum alone cannot disclose which treatment followed a
    # long pause; these are recorded-clock diagnostics, not causal effects.
    cross_task_gaps_by_successor_us: dict[str, list[int]] = {
        arm: [] for arm in design.VARIANTS
    }
    for task_index, (preceding_row, following_row) in enumerate(
        zip(plan["schedule"], plan["schedule"][1:]), start=1
    ):
        predecessor = preceding_row["arm_order"][-1]
        successor = following_row["arm_order"][0]
        preceding_status = status_by_task[preceding_row["task_id"]][predecessor]
        following_status = status_by_task[following_row["task_id"]][successor]
        cross_task_planned[successor][predecessor] += 1
        if following_status == "not_started":
            continue
        # The verified contiguous unstarted-suffix contract means a following
        # attempt cannot exist without an attempted predecessor.
        cross_task_attempted[successor][predecessor] += 1
        if following_status == "completed":
            if preceding_status == "completed":
                cross_task_completed[successor][predecessor] += 1
            else:
                cross_task_completed_after_noncompleted[successor] += 1

        # Events are already validated in four-cell task-major order; a
        # boundary's elapsed gap is between the earlier finish and later start.
        # This is a recorded pause, not an independently authenticated clock.
        preceding_finish = _timestamp(
            events[task_index * len(design.VARIANTS) - 1]["finished_at_utc"],
            "cross-task predecessor finish",
        )
        following_start = _timestamp(
            events[task_index * len(design.VARIANTS)]["started_at_utc"],
            "cross-task successor start",
        )
        gap = following_start - preceding_finish
        gap_us = (gap.days * 86400 + gap.seconds) * 1_000_000 + gap.microseconds
        cross_task_attempted_gaps_us.append(gap_us)
        cross_task_gaps_by_successor_us[successor].append(gap_us)

    # The 30 within-task consecutive-arm boundaries are distinct from the
    # nine cross-task boundaries and from run execution durations. A pause
    # before one arm can be condition-correlated even when the assigned order
    # and per-arm execution durations are balanced. Retain attempted links
    # across unsuccessful attempts; classify completed links separately.
    # These are candidate timestamps, NOT independently authenticated drift.
    within_task_gaps_by_successor_us = {arm: [] for arm in design.VARIANTS}
    completed_within_task_gaps_by_successor_us = {
        arm: [] for arm in design.VARIANTS
    }
    for task_index, row in enumerate(plan["schedule"]):
        offset = task_index * len(design.VARIANTS)
        for slot in range(1, len(row["arm_order"])):
            predecessor_event = events[offset + slot - 1]
            successor_event = events[offset + slot]
            if successor_event["status"] == "not_started":
                # Chronology validation guarantees a contiguous unattempted
                # suffix, so no predecessor finish should be invented.
                continue
            predecessor_finish = _timestamp(
                predecessor_event["finished_at_utc"],
                "within-task predecessor finish",
            )
            successor_start = _timestamp(
                successor_event["started_at_utc"],
                "within-task successor start",
            )
            gap = successor_start - predecessor_finish
            gap_us = (
                (gap.days * 86400 + gap.seconds) * 1_000_000
                + gap.microseconds
            )
            successor = successor_event["variant"]
            within_task_gaps_by_successor_us[successor].append(gap_us)
            if (predecessor_event["status"] == "completed"
                    and successor_event["status"] == "completed"):
                completed_within_task_gaps_by_successor_us[successor].append(
                    gap_us
                )

    def gap_summary(values: list[int]) -> dict[str, int | None]:
        return {
            "count": len(values),
            "minimum_microseconds": min(values, default=None),
            "maximum_microseconds": max(values, default=None),
            "total_microseconds": sum(values),
        }

    # Arm-specific elapsed-time summaries expose differential recorded runtime
    # after attrition. They are not measured provider compute or per-run costs.
    attempted_duration_summary = {
        arm: gap_summary(values)
        for arm, values in attempted_durations_by_variant.items()
    }
    completed_duration_summary = {
        arm: gap_summary(values)
        for arm, values in completed_durations_by_variant.items()
    }
    cross_task_gap_summary = gap_summary(cross_task_attempted_gaps_us)
    cross_task_gap_by_successor = {
        arm: gap_summary(values)
        for arm, values in cross_task_gaps_by_successor_us.items()
    }
    within_task_gap_by_successor = {
        arm: gap_summary(values)
        for arm, values in within_task_gaps_by_successor_us.items()
    }
    completed_within_task_gap_by_successor = {
        arm: gap_summary(values)
        for arm, values in completed_within_task_gaps_by_successor_us.items()
    }

    def paired_duration_deltas(*, completed_only: bool) -> dict:
        """Signed within-task duration differences in named contrast direction.

        Failed attempts stay in the attempted denominator, never the completed
        one. No absent arm is treated as a zero-duration execution.
        """
        result = {}
        for name, (left, right) in primary_pairs.items():
            differences = []
            for task_id, durations in attempted_durations_by_task.items():
                if left not in durations or right not in durations:
                    continue
                if completed_only and not {
                    left, right
                }.issubset(completed_variants_by_task[task_id]):
                    continue
                differences.append(durations[left] - durations[right])
            result[name] = {
                "count": len(differences),
                "positive": sum(value > 0 for value in differences),
                "zero": sum(value == 0 for value in differences),
                "negative": sum(value < 0 for value in differences),
                "minimum_microseconds": min(differences, default=None),
                "maximum_microseconds": max(differences, default=None),
                "signed_total_microseconds": sum(differences),
            }
        return result

    attempted_paired_duration_deltas = paired_duration_deltas(completed_only=False)
    completed_paired_duration_deltas = paired_duration_deltas(completed_only=True)

    return {
        "status": "pass_recorded_chronology_only",
        "classification": LOG_CLASSIFICATION,
        "task_set_id": plan["task_set_id"],
        "source_manifest_sha256": plan["source_manifest_sha256"],
        "plan_file_sha256": plan_verified["plan_file_sha256"],
        "execution_log_sha256": log_sha256,
        "plan_file_external_pin_matched": plan_verified["supplied_plan_file_pin_matched"],
        "task_manifest_external_pin_matched": plan_verified["supplied_task_manifest_pin_matched"],
        "execution_log_external_pin_matched": log_pinned,
        "recorded_cells": len(events),
        "attempted_cells": len(events) - counts["not_started"],
        "unattempted_cells": counts["not_started"],
        "all_planned_cells_attempted": counts["not_started"] == 0,
        "recorded_status_counts": counts,
        "recorded_status_counts_by_variant": status_counts_by_variant,
        "recorded_attempted_duration_us_by_variant": attempted_duration_summary,
        "recorded_completed_duration_us_by_variant": completed_duration_summary,
        "recorded_attempted_primary_pair_duration_delta_us": (
            attempted_paired_duration_deltas
        ),
        "recorded_completed_primary_pair_duration_delta_us": (
            completed_paired_duration_deltas
        ),
        "recorded_attempted_position_counts_by_variant": attempted_position_counts_by_variant,
        "recorded_completed_position_counts_by_variant": completed_position_counts_by_variant,
        "recorded_position_exposure_by_frozen_task_category": category_position_exposure,
        "recorded_completed_primary_pair_order_counts": completed_pair_order_counts,
        "recorded_completed_primary_pair_start_separation_us": (
            completed_pair_start_separation_us
        ),
        "planned_immediate_predecessor_counts_by_variant": planned_predecessors,
        "recorded_attempted_immediate_predecessor_counts_by_variant": attempted_predecessors,
        "recorded_completed_immediate_predecessor_counts_by_variant": completed_predecessors,
        "recorded_completed_after_noncompleted_predecessor_counts_by_variant": (
            completed_after_noncompleted_predecessor
        ),
        "planned_cross_task_transition_counts_by_variant": cross_task_planned,
        "recorded_attempted_cross_task_transition_counts_by_variant": cross_task_attempted,
        "recorded_completed_cross_task_transition_counts_by_variant": cross_task_completed,
        "recorded_completed_after_noncompleted_cross_task_predecessor_counts_by_variant": (
            cross_task_completed_after_noncompleted
        ),
        "recorded_attempted_cross_task_boundary_gap_us": cross_task_gap_summary,
        "recorded_attempted_cross_task_boundary_gap_by_successor_us": (
            cross_task_gap_by_successor
        ),
        "recorded_attempted_within_task_boundary_gap_by_successor_us": (
            within_task_gap_by_successor
        ),
        "recorded_completed_within_task_boundary_gap_by_successor_us": (
            completed_within_task_gap_by_successor
        ),
        "recorded_fully_completed_task_count": sum(
            len(completed) == len(design.VARIANTS)
            for completed in completed_variants_by_task.values()
        ),
        "recorded_completed_primary_pair_task_counts": completed_pair_task_counts,
        "all_recorded_cells_completed": counts["completed"] == len(events),
        "actual_execution_independently_authenticated": False,
        "scientific_outcomes_validated": False,
        "historical_2026_study_validated": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-manifest", required=True, type=Path)
    parser.add_argument("--plan-file", required=True, type=Path)
    parser.add_argument("--execution-log", required=True, type=Path)
    parser.add_argument("--expected-plan-file-sha256")
    parser.add_argument("--expected-task-manifest-sha256")
    parser.add_argument("--expected-execution-log-sha256")
    args = parser.parse_args()
    try:
        result = audit_execution_log(
            design.read_manifest(args.task_manifest),
            design.read_manifest(args.plan_file),
            design.read_manifest(args.execution_log),
            expected_plan_file_sha256=args.expected_plan_file_sha256,
            expected_task_manifest_sha256=args.expected_task_manifest_sha256,
            expected_execution_log_sha256=args.expected_execution_log_sha256,
        )
    except design.DesignError as exc:
        parser.exit(2, f"PROSPECTIVE EXECUTION CHRONOLOGY: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
