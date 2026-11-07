"""Verify a saved exploratory retrieval-exposure JSON against frozen CSV rows.

This checker deliberately does not import the retrieval-exposure producer.
It rederives every displayed metric, task pair and source reference from the
published input ledger, without treatment, evaluator or human-evaluation runs.
A PASS is local arithmetic/byte consistency, not historical archive custody.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

from scripts import audit_frozen_analysis_csv_inputs as audit

MAX_ARTIFACT_BYTES = 256 * 1024
MAX_JSON_DEPTH = 32
MAX_INTEGER_DIGITS = 20
CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
METRICS = (
    "scheduled_slots", "successful_sources", "failed_sources",
    "accounted_source_results", "capacity_not_accounted_for_by_source_results",
    "search_calls", "model_calls", "total_tokens",
)
DELTA_NAMES = (
    "scheduled_slot_delta", "successful_source_delta", "failed_source_delta",
    "accounted_source_result_delta", "unaccounted_capacity_delta",
    "search_call_delta", "model_call_delta", "total_token_delta",
)
INTERPRETATION = (
    "Scheduled source slots are treatment settings; successful and "
    "failed source results are retrospective exported counts. Their "
    "sum may be less than the budget and the residual is not proof "
    "of skipped attempts. Search calls, model calls and tokens are "
    "additional resource exposure, not equal-total-compute controls. "
    "No claim outcomes, causal effects or new p-values were computed."
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object_no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate retrieval-exposure JSON key: {key!r}")
        result[key] = value
    return result


def _integer(token: str) -> int:
    _require(len(token.lstrip("-")) <= MAX_INTEGER_DIGITS,
             "retrieval-exposure JSON integer token too long")
    return int(token)


def _reject_float_nonfinite(token: str):
    # Floats are allowed by the producer, but NaN and overflow-to-infinity
    # are not valid descriptive quantities.
    import math
    number = float(token)
    _require(math.isfinite(number), "nonfinite retrieval-exposure JSON number")
    return number


def _reject_constant(token: str):
    raise ValueError(f"non-JSON retrieval-exposure numeric constant: {token}")


def _check_json_depth(raw: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in raw:
        if in_string:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                in_string = False
        elif char == 34:
            in_string = True
        elif char in (123, 91):
            depth += 1
            _require(depth <= MAX_JSON_DEPTH, "retrieval-exposure JSON too deeply nested")
        elif char in (125, 93):
            depth -= 1


def _parse(raw: bytes) -> dict:
    _require(len(raw) <= MAX_ARTIFACT_BYTES,
             "retrieval-exposure artifact exceeds byte limit")
    _check_json_depth(raw)
    try:
        result = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object_no_duplicates,
            parse_int=_integer, parse_float=_reject_float_nonfinite,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("retrieval-exposure artifact is not valid UTF-8 JSON") from exc
    _require(type(result) is dict, "retrieval-exposure artifact must be an object")
    return result


def _expected(rows: list[dict[str, str]], *,
              main_sha256: str, support_sha256: str,
              aggregate_sha256: str) -> dict:
    """Independently rebuild all 40 resource cells and all 30 paired deltas."""
    matrix = audit._paired_rows(rows, label="independent retrieval-exposure verification")
    tasks = sorted({task for _, task in matrix})
    _require(len(tasks) == audit.EXPECTED_TASKS, "expected ten paired tasks")
    cells = {}
    for (variant, task), row in matrix.items():
        label = f"{variant}/{task}"
        _require(str(row.get("completed", "")).strip().lower() in
                 {"true", "1", "yes"}, f"{label} is incomplete")
        budget = audit._int(row, "source_budget", label=label)
        _require(budget == (3 if variant == "D3" else 6),
                 f"{label} has wrong scheduled budget")
        success, failure, searches, calls, tokens = (
            audit._int(row, field, label=label) for field in (
                "successful_sources", "failed_sources",
                "search_calls", "model_calls", "total_tokens"
            )
        )
        _require(min(success, failure, searches, calls, tokens) >= 0
                 and success + failure <= budget,
                 f"{label} has invalid source/resource totals")
        cells[variant, task] = {
            "task_id": task,
            "scheduled_slots": budget,
            "successful_sources": success,
            "failed_sources": failure,
            "accounted_source_results": success + failure,
            "capacity_not_accounted_for_by_source_results": budget - success - failure,
            "search_calls": searches,
            "model_calls": calls,
            "total_tokens": tokens,
        }

    arms = {}
    for variant in audit.VARIANTS:
        items = [cells[variant, task] for task in tasks]
        totals = {field: sum(item[field] for item in items) for field in METRICS}
        arms[variant] = {
            "n_reports": len(items),
            "totals": totals,
            "means_per_report": {
                field: totals[field] / len(items) for field in METRICS
            },
            "recorded_successful_sources_per_scheduled_slot":
                totals["successful_sources"] / totals["scheduled_slots"],
            "accounted_source_results_per_scheduled_slot":
                totals["accounted_source_results"] / totals["scheduled_slots"],
            "reports_with_zero_successful_sources":
                sum(item["successful_sources"] == 0 for item in items),
            "reports_with_capacity_not_accounted_for":
                sum(item["capacity_not_accounted_for_by_source_results"] > 0
                    for item in items),
            "all_task_exposures": items,
        }

    comparisons = {}
    for left, right, name in CONTRASTS:
        differences = []
        for task in tasks:
            a, b = cells[left, task], cells[right, task]
            differences.append({
                "task_id": task,
                **{delta: b[field] - a[field]
                   for field, delta in zip(METRICS, DELTA_NAMES)},
            })
        successes = [d["successful_source_delta"] for d in differences]
        comparisons[name] = {
            "n_paired_tasks": len(tasks),
            "scheduled_slot_delta_per_task":
                cells[right, tasks[0]]["scheduled_slots"]
                - cells[left, tasks[0]]["scheduled_slots"],
            "mean_successful_source_delta": sum(successes) / len(tasks),
            "more_successful_sources_right": sum(x > 0 for x in successes),
            "fewer_successful_sources_right": sum(x < 0 for x in successes),
            "equal_successful_sources": sum(x == 0 for x in successes),
            "all_task_exposure_differences": differences,
        }
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "post_hoc_exploratory_retrieval_exposure_only",
        "task_ids": tasks,
        "variant_summaries": arms,
        "frozen_contrast_exposure_comparisons": comparisons,
        "confirmatory_inference_changed": False,
        "statistical_tests_added": False,
        "human_validation_performed": False,
        "original_execution_authenticated": False,
        "interpretation": INTERPRETATION,
        "verified_published_treatment_csv_sha256": main_sha256,
        "published_evaluator_csv_sha256_reference": support_sha256,
        "published_input_aggregate_sha256_reference": aggregate_sha256,
        "published_summary_preflight_passed": True,
    }


def _compare(actual, expected, *, where: str = "artifact") -> None:
    """Exact structural and numeric equality; booleans cannot pose as counts."""
    _require(type(actual) is type(expected), f"{where} has wrong JSON type")
    if type(expected) is dict:
        _require(set(actual) == set(expected), f"{where} has missing/extra fields")
        for key in expected:
            _compare(actual[key], expected[key], where=f"{where}.{key}")
    elif type(expected) is list:
        _require(len(actual) == len(expected), f"{where} has wrong row count")
        for index, (value, reference) in enumerate(zip(actual, expected)):
            _compare(value, reference, where=f"{where}[{index}]")
    else:
        _require(actual == expected, f"{where} differs from frozen source arithmetic")


def verify_bytes(rows: list[dict[str, str]], artifact_raw: bytes, *,
                 main_sha256: str, support_sha256: str,
                 aggregate_sha256: str) -> dict:
    """Synthetic-testable source-vs-receipt contract, with no I/O or producer import."""
    observed = _parse(artifact_raw)
    expected = _expected(
        rows, main_sha256=main_sha256, support_sha256=support_sha256,
        aggregate_sha256=aggregate_sha256,
    )
    _compare(observed, expected)
    return {
        "schema_version": 1,
        "status": "verified_post_hoc_exploratory_retrieval_exposure_only",
        "diagnostic_sha256": hashlib.sha256(artifact_raw).hexdigest(),
        "verified_published_treatment_csv_sha256": main_sha256,
        "published_evaluator_csv_sha256_reference": support_sha256,
        "published_input_aggregate_sha256_reference": aggregate_sha256,
        "cells_checked": 40,
        "paired_contrast_rows_checked": 30,
        "confirmatory_inference_changed": False,
        "human_validation_performed": False,
        "original_execution_authenticated": False,
    }


def _read_artifact(path: Path) -> bytes:
    """Bound a single-link regular file and reject observed replacement/write."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                 "retrieval-exposure artifact must be a single-link regular file")
        _require(before.st_size <= MAX_ARTIFACT_BYTES,
                 "retrieval-exposure artifact exceeds byte limit")
        chunks = []
        remaining = MAX_ARTIFACT_BYTES
        while True:
            chunk = os.read(descriptor, min(65536, remaining + 1))
            if not chunk:
                break
            _require(len(chunk) <= remaining,
                     "retrieval-exposure artifact exceeds byte limit")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        visible = os.stat(path, follow_symlinks=False)
        signature = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        _require(signature(before) == signature(after) == signature(visible),
                 "retrieval-exposure artifact changed during capture")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def verify_published(artifact_path: Path) -> dict:
    """Fail closed on either changed published CSV or a forged diagnostic."""
    audit.audit_frozen_csv_inputs()
    captured, rows = audit._read_csv(
        audit.DEFAULT_MAIN, label="published treatment ledger for exposure verification"
    )
    observed = hashlib.sha256(captured).hexdigest()
    _require(observed == audit.FROZEN_MAIN_CSV_SHA256,
             "original treatment CSV differs from frozen published SHA-256")
    _require(sorted({row["task_id"] for row in rows}) ==
             [f"main-{index:02d}" for index in range(1, 11)],
             "treatment ledger has unexpected frozen task IDs")
    receipt = verify_bytes(
        rows, _read_artifact(Path(artifact_path)),
        main_sha256=observed, support_sha256=audit.FROZEN_SUPPORT_CSV_SHA256,
        aggregate_sha256=audit.PUBLISHED_INPUT_AGGREGATE_SHA256,
    )
    # A later on-disk mutation must not leave a verification PASS.
    audit.audit_frozen_csv_inputs()
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True,
                        help="Saved JSON output of analyze_main_study_retrieval_exposure")
    args = parser.parse_args()
    try:
        receipt = verify_published(args.artifact)
    except (OSError, ValueError, audit.InputIntegrityError) as exc:
        parser.exit(1, f"RETRIEVAL EXPOSURE ARTIFACT: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
