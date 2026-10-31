"""Independently check the *complete* exploratory task-influence artifact.

This is an offline artifact verifier, not a second confirmatory analysis. It
recomputes every nine-task mean directly from the frozen ten-task differences,
without importing the exploratory producer's diagnostic implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts.analyze_main_study_task_influence import _read_regular_bounded

INFERENCE_PATH = Path("outputs/main_study_inference.json")
PROVENANCE_PATH = Path("outputs/main_study_analysis_provenance.json")
CONTRASTS = (
    "D6_minus_D3_retrieval_depth",
    "P6_minus_D6_planning",
    "P6V_minus_P6_verification",
)
TOP_LEVEL_KEYS = {
    "schema_version", "study_id", "status", "scope",
    "confirmatory_analysis_replaced", "human_validation_performed",
    "inferential_p_values_or_intervals_added", "task_ids", "results",
    "verified_canonical_inference_sha256", "verified_provenance_receipt_sha256",
    "source_provenance_independently_recomputed",
}
CONTRAST_KEYS = {
    "full_sample_mean_difference", "n_frozen_pairs", "all_task_omissions",
    "loo_mean_min", "loo_mean_max",
}
OMISSION_KEYS = {
    "omitted_task_id", "remaining_pairs", "mean_difference_without_task",
    "change_from_full_mean",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict:
    found = {}
    for key, value in pairs:
        _require(key not in found, f"duplicate JSON key: {key!r}")
        found[key] = value
    return found


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {token}")


def _parse(raw: bytes, label: str) -> dict:
    try:
        data = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    _require(type(data) is dict, f"{label} must be an object")
    return data


def _number(value: object, label: str) -> float:
    _require(type(value) in (int, float) and math.isfinite(value),
             f"{label} must be a finite JSON number (not boolean)")
    return float(value)


def _equal_number(actual: object, expected: float, label: str) -> None:
    observed = _number(actual, label)
    _require(math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-12),
             f"{label} inconsistent with frozen paired differences")


def verify_bytes(inference_bytes: bytes, provenance_bytes: bytes,
                 diagnostic_bytes: bytes) -> dict:
    """Fail closed on omitted/forged rows, denominators, values or source IDs."""
    inference = _parse(inference_bytes, "canonical inference")
    provenance = _parse(provenance_bytes, "execution-bound provenance")
    report = _parse(diagnostic_bytes, "exploratory diagnostic")

    _require(type(provenance.get("verified_execution")) is dict,
             "provenance lacks verified execution binding")
    _require(type(inference.get("schema_version")) is int
             and inference["schema_version"] == 1
             and inference.get("study_id") == "budget-main-v1"
             and type(inference.get("n_tasks")) is int
             and inference["n_tasks"] == 10,
             "unexpected canonical study identity")
    tasks = inference.get("task_ids")
    _require(type(tasks) is list and len(tasks) == 10
             and all(type(task) is str and task and task.strip() == task
                     for task in tasks)
             and len(set(tasks)) == len(tasks),
             "ambiguous frozen task IDs")
    primary = inference.get("primary_contrasts")
    _require(type(primary) is dict and set(primary) == set(CONTRASTS),
             "unexpected frozen primary contrast family")

    _require(set(report) == TOP_LEVEL_KEYS
             and type(report.get("schema_version")) is int
             and report["schema_version"] == 1
             and report.get("study_id") == "budget-main-v1"
             and report.get("status") == "post_hoc_exploratory_task_influence_only"
             and report.get("scope") ==
                 "three_frozen_primary_contrasts_all_ten_single_task_omissions"
             and report.get("confirmatory_analysis_replaced") is False
             and report.get("human_validation_performed") is False
             and report.get("inferential_p_values_or_intervals_added") is False
             and report.get("source_provenance_independently_recomputed") is True,
             "exploratory-only declaration missing or contradictory")
    _require(report.get("task_ids") == tasks,
             "diagnostic task order differs from frozen analysis")
    _require(
        report.get("verified_canonical_inference_sha256") ==
            hashlib.sha256(inference_bytes).hexdigest()
        and report.get("verified_provenance_receipt_sha256") ==
            hashlib.sha256(provenance_bytes).hexdigest(),
        "diagnostic is not byte-bound to the retained inference/provenance",
    )
    results = report.get("results")
    _require(type(results) is dict and set(results) == set(CONTRASTS),
             "incomplete or unexpected exploratory contrast coverage")

    for name in CONTRASTS:
        original = primary[name]
        _require(type(original) is dict
                 and type(original.get("task_differences")) is list
                 and len(original["task_differences"]) == len(tasks),
                 f"{name} frozen differences incomplete")
        values = [_number(value, f"{name}/frozen difference")
                  for value in original["task_differences"]]
        _require(all(-1.0 <= value <= 1.0 for value in values),
                 f"{name} frozen difference outside strict-support range")
        full_mean = math.fsum(values) / len(values)
        _equal_number(original.get("mean_difference"), full_mean,
                      f"{name}/published mean")
        block = results[name]
        _require(type(block) is dict and set(block) == CONTRAST_KEYS
                 and type(block.get("n_frozen_pairs")) is int
                 and block["n_frozen_pairs"] == len(tasks),
                 f"{name} invalid diagnostic block/denominator")
        _equal_number(block.get("full_sample_mean_difference"), full_mean,
                      f"{name}/full-sample mean")
        rows = block.get("all_task_omissions")
        _require(type(rows) is list and len(rows) == len(tasks),
                 f"{name} must enumerate every frozen task exactly once")
        omission_means = []
        for index, (task_id, row) in enumerate(zip(tasks, rows)):
            _require(type(row) is dict and set(row) == OMISSION_KEYS
                     and row.get("omitted_task_id") == task_id
                     and type(row.get("remaining_pairs")) is int
                     and row["remaining_pairs"] == len(tasks) - 1,
                     f"{name}/{task_id} missing or reordered omission/denominator")
            retained = values[:index] + values[index + 1:]
            omitted_mean = math.fsum(retained) / len(retained)
            _equal_number(row.get("mean_difference_without_task"), omitted_mean,
                          f"{name}/{task_id}/omission mean")
            _equal_number(row.get("change_from_full_mean"), omitted_mean - full_mean,
                          f"{name}/{task_id}/change from full")
            omission_means.append(omitted_mean)
        _equal_number(block.get("loo_mean_min"), min(omission_means),
                      f"{name}/min omission mean")
        _equal_number(block.get("loo_mean_max"), max(omission_means),
                      f"{name}/max omission mean")
    return {
        "schema_version": 1,
        "status": "verified_post_hoc_exploratory_task_influence_only",
        "verified_canonical_inference_sha256":
            hashlib.sha256(inference_bytes).hexdigest(),
        "verified_provenance_receipt_sha256":
            hashlib.sha256(provenance_bytes).hexdigest(),
        "task_influence_diagnostic_sha256":
            hashlib.sha256(diagnostic_bytes).hexdigest(),
        "contrasts_checked": len(CONTRASTS),
        "paired_omission_rows_checked": len(CONTRASTS) * len(tasks),
        "confirmatory_analysis_replaced": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--receipt-implementation-commit", required=True)
    parser.add_argument("--source-selection-commit", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        receipt = verify_bytes(
            _read_regular_bounded(args.root / INFERENCE_PATH, label="inference"),
            _read_regular_bounded(args.root / PROVENANCE_PATH, label="provenance"),
            _read_regular_bounded(args.diagnostic, label="task diagnostic"),
        )
        for attr in ("checkout_sha", "receipt_implementation_commit",
                     "source_selection_commit"):
            value = getattr(args, attr)
            _require(len(value) == 40 and
                     all(character in "0123456789abcdef" for character in value),
                     f"{attr} must be an exact lowercase Git commit SHA")
        _require(args.run_id.isdecimal() and int(args.run_id) > 0,
                 "workflow run ID invalid")
        receipt.update({
            "checkout_sha": args.checkout_sha,
            "receipt_implementation_commit": args.receipt_implementation_commit,
            "source_selection_commit": args.source_selection_commit,
            "workflow_run_id": args.run_id,
        })
    except (OSError, ValueError) as exc:
        raise SystemExit(f"TASK INFLUENCE ARTIFACT VERIFICATION: FAIL: {exc}") from exc
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
