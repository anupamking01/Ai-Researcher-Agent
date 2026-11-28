"""Independently replay the saved exploratory claim-denominator JSON against frozen CSVs.

A PASS establishes local arithmetic reproducibility, not treatment/evaluator
execution authenticity, statistical significance, or human validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts import audit_frozen_analysis_csv_inputs as audit

MAX_ARTIFACT_BYTES = 256 * 1024
MAX_JSON_DEPTH = 32
CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
INTERPRETATION = (
    "Evaluator checked-claim counts describe a capped measurement "
    "denominator, not report completeness or all report claims. "
    "The frozen confirmatory estimand is the equal-report macro rate. "
    "Claim-pooled rates are post-hoc descriptive sensitivity values."
)


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        _require(key not in output, f"duplicate denominator JSON key: {key}")
        output[key] = value
    return output


def _int_token(token: str) -> int:
    _require(len(token.lstrip("-")) <= 20, "denominator JSON integer token too long")
    return int(token)


def _float_token(token: str) -> float:
    value = float(token)
    _require(math.isfinite(value), "nonfinite denominator JSON number")
    return value


def _constant(token: str):
    raise ValueError(f"non-JSON denominator numeric constant: {token}")


def _parse(raw: bytes) -> dict:
    _require(0 < len(raw) <= MAX_ARTIFACT_BYTES, "denominator artifact byte limit")
    level = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (123, 91):
            level += 1
            _require(level <= MAX_JSON_DEPTH, "denominator JSON nested too deeply")
        elif char in (125, 93):
            level -= 1
    try:
        parsed = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_int=_int_token, parse_float=_float_token, parse_constant=_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("denominator artifact invalid UTF-8 JSON") from exc
    _require(type(parsed) is dict, "denominator artifact must be a JSON object")
    return parsed


def _recompute(rows: list[dict[str, str]], *, support_sha256: str,
               main_sha256: str, aggregate_sha256: str) -> dict:
    """Pure independent arithmetic, without importing the diagnostic producer."""
    matrix = audit._paired_rows(rows, label="independent denominator replay")
    tasks = sorted({task for _, task in matrix})
    _require(len(tasks) == audit.EXPECTED_TASKS, "expected ten paired tasks")
    cells = {}
    for (arm, task), row in matrix.items():
        label = f"{arm}/{task}"
        checked = audit._int(row, "claims_checked", label=label)
        supported = audit._int(row, "supported", label=label)
        partial = audit._int(row, "partially_supported", label=label)
        unsupported = audit._int(row, "unsupported", label=label)
        contradicted = audit._int(row, "contradicted", label=label)
        _require(1 <= checked <= 12, f"{label} denominator outside frozen cap")
        _require(min(supported, partial, unsupported, contradicted) >= 0
                 and sum((supported, partial, unsupported, contradicted)) == checked,
                 f"{label} claim categories do not partition denominator")
        rate = audit._finite_nonnegative(row, "strict_support_rate", label=label)
        _require(rate <= 1 and math.isclose(rate, supported / checked,
                                             abs_tol=1e-12, rel_tol=0),
                 f"{label} strict-support rate contradicts counts")
        cells[arm, task] = checked, supported

    summaries = {}
    for arm in audit.VARIANTS:
        arm_cells = [cells[arm, task] for task in tasks]
        n = len(arm_cells)
        total_checked = sum(pair[0] for pair in arm_cells)
        total_supported = sum(pair[1] for pair in arm_cells)
        macro = math.fsum(supported / checked
                          for checked, supported in arm_cells) / n
        pooled = total_supported / total_checked
        summaries[arm] = {
            "n_reports": n,
            "total_claims_checked": total_checked,
            "total_claims_supported": total_supported,
            "claims_checked_mean_per_report": total_checked / n,
            "claims_checked_min": min(pair[0] for pair in arm_cells),
            "claims_checked_max": max(pair[0] for pair in arm_cells),
            "claims_checked_histogram_1_to_12": {
                str(k): sum(pair[0] == k for pair in arm_cells) for k in range(1, 13)
            },
            "reports_at_12_claim_cap": sum(pair[0] == 12 for pair in arm_cells),
            "task_claim_counts": [
                {"task_id": task, "claims_checked": cells[arm, task][0]}
                for task in tasks
            ],
            "equal_report_macro_strict_support": macro,
            "claim_pooled_micro_strict_support": pooled,
            "micro_minus_macro_strict_support": pooled - macro,
        }

    contrasts = {}
    for left, right, name in CONTRASTS:
        pairs = [{
            "task_id": task,
            "left_claims_checked": cells[left, task][0],
            "right_claims_checked": cells[right, task][0],
            "right_minus_left_claims_checked":
                cells[right, task][0] - cells[left, task][0],
        } for task in tasks]
        differences = [row["right_minus_left_claims_checked"] for row in pairs]
        contrasts[name] = {
            "n_paired_tasks": len(tasks),
            "mean_difference_claims_checked":
                math.fsum(differences) / len(tasks),
            "tasks_with_more_claims_right": sum(d > 0 for d in differences),
            "tasks_with_fewer_claims_right": sum(d < 0 for d in differences),
            "tasks_with_equal_claims": sum(d == 0 for d in differences),
            "all_task_claim_count_differences": pairs,
        }

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "post_hoc_exploratory_denominator_diagnostic_only",
        "task_ids": tasks,
        "variant_summaries": summaries,
        "frozen_contrast_denominator_comparisons": contrasts,
        "confirmatory_primary_estimand_changed": False,
        "p_values_or_confidence_intervals_added": False,
        "human_validation_performed": False,
        "original_execution_authenticated": False,
        "interpretation": INTERPRETATION,
        "verified_published_evaluator_csv_sha256": support_sha256,
        "published_treatment_csv_sha256_reference": main_sha256,
        "published_input_aggregate_sha256_reference": aggregate_sha256,
        "published_summary_preflight_passed": True,
    }


def _compare(actual, expected, *, label="denominator artifact") -> None:
    _require(type(actual) is type(expected), f"{label} JSON type differs")
    if type(expected) is dict:
        _require(set(actual) == set(expected), f"{label} fields differ")
        for key, value in expected.items():
            _compare(actual[key], value, label=f"{label}.{key}")
    elif type(expected) is list:
        _require(len(actual) == len(expected), f"{label} row count differs")
        for index, (item, reference) in enumerate(zip(actual, expected)):
            _compare(item, reference, label=f"{label}[{index}]")
    else:
        _require(actual == expected, f"{label} differs from published-source arithmetic")


def verify_bytes(rows: list[dict[str, str]], raw: bytes, *,
                 support_sha256: str, main_sha256: str,
                 aggregate_sha256: str) -> dict:
    actual = _parse(raw)
    expected = _recompute(rows, support_sha256=support_sha256,
                          main_sha256=main_sha256,
                          aggregate_sha256=aggregate_sha256)
    _compare(actual, expected)
    return {
        "schema_version": 1,
        "status": "verified_post_hoc_exploratory_denominator_diagnostic_only",
        "diagnostic_sha256": hashlib.sha256(raw).hexdigest(),
        "verified_published_evaluator_csv_sha256": support_sha256,
        "published_treatment_csv_sha256_reference": main_sha256,
        "published_input_aggregate_sha256_reference": aggregate_sha256,
        "cells_checked": 40,
        "paired_contrast_rows_checked": 30,
        "confirmatory_primary_estimand_changed": False,
        "human_validation_performed": False,
        "original_execution_authenticated": False,
    }


def verify_published(artifact_path: Path) -> dict:
    audit.audit_frozen_csv_inputs()
    captured, rows = audit._read_csv(
        audit.DEFAULT_SUPPORT, label="published evaluator CSV for denominator replay"
    )
    sha = hashlib.sha256(captured).hexdigest()
    _require(sha == audit.FROZEN_SUPPORT_CSV_SHA256,
             "published evaluator CSV differs from frozen SHA-256")
    _require(sorted({row["task_id"] for row in rows}) ==
             [f"main-{i:02d}" for i in range(1, 11)],
             "published task IDs differ")
    # Reuse only the byte-oriented no-follow single-link descriptor capture.
    # Parsing, aggregation and result comparison remain independent.
    raw = audit._capture_csv_bytes(
        Path(artifact_path), label="saved denominator JSON artifact"
    )
    receipt = verify_bytes(
        rows, raw, support_sha256=sha,
        main_sha256=audit.FROZEN_MAIN_CSV_SHA256,
        aggregate_sha256=audit.PUBLISHED_INPUT_AGGREGATE_SHA256,
    )
    audit.audit_frozen_csv_inputs()
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = verify_published(args.artifact)
    except (OSError, ValueError, audit.InputIntegrityError) as exc:
        parser.exit(1, f"DENOMINATOR ARTIFACT: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
