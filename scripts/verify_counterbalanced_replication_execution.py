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
            continue
        if unstarted_suffix:
            raise design.DesignError(
                f"event {index} records an attempt after a not_started suffix"
            )
        run_id = event["run_id"]
        if (type(run_id) is not str or _SAFE_RUN_ID.fullmatch(run_id) is None or
                run_id in run_ids):
            raise design.DesignError(f"event {index} has an unsafe or duplicate run ID")
        run_ids.add(run_id)
        # Attempted failures/timeouts/cancellations remain visible. Never
        # conceal them as unattempted work or cherry-pick favorable reruns.
        counts[status] += 1
        started = _timestamp(event["started_at_utc"], f"event {index} start")
        finished = _timestamp(event["finished_at_utc"], f"event {index} finish")
        if started < previous_finish or finished <= started:
            raise design.DesignError(
                f"event {index} has overlapping or nonpositive recorded chronology"
            )
        if finished > study_finish:
            raise design.DesignError(f"event {index} finishes outside study window")
        previous_finish = finished

    if counts["not_started"] == len(events):
        raise design.DesignError(
            "execution log has no attempted cells; use the design-only verifier"
        )

    return {
        "status": "pass_recorded_chronology_only",
        "classification": LOG_CLASSIFICATION,
        "task_set_id": plan["task_set_id"],
        "source_manifest_sha256": plan["source_manifest_sha256"],
        "plan_file_sha256": plan_verified["plan_file_sha256"],
        "execution_log_sha256": log_sha256,
        "plan_file_external_pin_matched": plan_verified["supplied_plan_file_pin_matched"],
        "execution_log_external_pin_matched": log_pinned,
        "recorded_cells": len(events),
        "attempted_cells": len(events) - counts["not_started"],
        "unattempted_cells": counts["not_started"],
        "all_planned_cells_attempted": counts["not_started"] == 0,
        "recorded_status_counts": counts,
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
    parser.add_argument("--expected-execution-log-sha256")
    args = parser.parse_args()
    try:
        result = audit_execution_log(
            design.read_manifest(args.task_manifest),
            design.read_manifest(args.plan_file),
            design.read_manifest(args.execution_log),
            expected_plan_file_sha256=args.expected_plan_file_sha256,
            expected_execution_log_sha256=args.expected_execution_log_sha256,
        )
    except design.DesignError as exc:
        parser.exit(2, f"PROSPECTIVE EXECUTION CHRONOLOGY: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
