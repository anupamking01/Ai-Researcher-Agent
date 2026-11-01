"""Offline check of a *prospective* VERA task manifest and schedule receipt.

Recomputes the design from the exact proposed manifest; does not run agents,
score results, attest historical evidence, or prove pre-execution registration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from scripts import plan_counterbalanced_replication as design

MAX_RECEIPT_BYTES = 256 * 1024


def _canonical_json(value: object) -> str:
    """Keep JSON *types* distinct (Python's True == 1 is not sufficient)."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )


def verify_plan(
    task_manifest: bytes,
    receipt: bytes,
    *,
    expected_plan_file_sha256: str | None = None,
) -> dict:
    """Reconstruct every assignment, bound input hash, and receipt field.

    The optional expected file digest must come from separately retained
    pre-execution evidence; passing a locally recomputed digest is not
    independent preregistration or an archival attestation.
    """
    if (type(receipt) is not bytes or
            not 0 < len(receipt) <= MAX_RECEIPT_BYTES):
        raise design.DesignError("schedule receipt bytes outside supported range")
    if expected_plan_file_sha256 is not None and (
        type(expected_plan_file_sha256) is not str or
        re.fullmatch(r"[0-9a-f]{64}", expected_plan_file_sha256) is None
    ):
        raise design.DesignError(
            "expected plan-file SHA-256 must be exactly 64 lowercase hex digits"
        )

    expected = design.build_plan(task_manifest)
    try:
        submitted = json.loads(
            receipt.decode("utf-8"),
            object_pairs_hook=design._distinct_keys,
            parse_constant=design._reject_nonfinite,
            parse_int=design._bounded_int,
            parse_float=design._bounded_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise design.DesignError(
            "schedule receipt is not unambiguous UTF-8 JSON"
        ) from exc

    # Comparing canonical serializations rather than dicts prevents JSON
    # booleans or floating-point numbers from impersonating integer fields.
    if type(submitted) is not dict or (
        _canonical_json(submitted) != _canonical_json(expected)
    ):
        raise design.DesignError(
            "schedule receipt differs from the recomputed manifest-bound design"
        )

    file_sha256 = hashlib.sha256(receipt).hexdigest()
    if (expected_plan_file_sha256 is not None and
            file_sha256 != expected_plan_file_sha256):
        raise design.DesignError(
            "schedule receipt file SHA-256 differs from supplied external pin"
        )
    return {
        "status": "pass",
        "classification": "prospective_design_verification_only_no_executions",
        "task_set_id": expected["task_set_id"],
        "source_manifest_sha256": expected["source_manifest_sha256"],
        "semantic_task_manifest_sha256": expected[
            "semantic_task_manifest_sha256"
        ],
        "design_receipt_sha256": expected["design_receipt_sha256"],
        "plan_file_sha256": file_sha256,
        "supplied_plan_file_pin_matched": expected_plan_file_sha256 is not None,
        "historical_study_validated": False,
        "replication_or_human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-manifest", type=Path, required=True,
        help="originally frozen new task-manifest bytes",
    )
    parser.add_argument(
        "--plan-file", type=Path, required=True,
        help="retained output of plan_counterbalanced_replication.py",
    )
    parser.add_argument(
        "--expected-plan-file-sha256",
        help="OPTIONAL prior independently retained SHA-256 of exact plan-file bytes",
    )
    args = parser.parse_args()
    try:
        result = verify_plan(
            design.read_manifest(args.task_manifest),
            design.read_manifest(args.plan_file),
            expected_plan_file_sha256=args.expected_plan_file_sha256,
        )
    except design.DesignError as exc:
        parser.exit(2, f"PROSPECTIVE PLAN VERIFICATION: FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
