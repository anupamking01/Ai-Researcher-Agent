"""Verify a retained exploratory CI bundle against frozen CSVs and external run pins.

This is local, read-only arithmetic and bundle integrity verification, not
original experimental-execution authentication or human validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from scripts import audit_frozen_analysis_csv_inputs as audit
from scripts import verify_main_study_claim_denominator_artifact as denominators
from scripts import verify_main_study_retrieval_exposure_artifact as exposure

FILES = (
    "retrieval_exposure.json",
    "retrieval_exposure_verification.json",
    "claim_denominators.json",
    "claim_denominators_verification.json",
)
INDEX = "artifact_index.json"
EXPECTED_FILES = frozenset((*FILES, INDEX))
STATUS = "verified_local_post_hoc_exploratory_measurements_only"
MAX_JSON_BYTES = 256 * 1024
MAX_JSON_DEPTH = 24


def _require(condition: bool, explanation: str) -> None:
    if not condition:
        raise ValueError(explanation)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate bundle JSON key: {key}")
        result[key] = value
    return result


def _int_token(token: str) -> int:
    _require(len(token.lstrip("-")) <= 20, "bundle JSON integer exceeds safe domain")
    return int(token)


def _noninteger_number(token: str):
    raise ValueError(f"bundle metadata/receipt contains non-integer number: {token[:24]}")


def _parse_metadata(raw: bytes, *, label: str) -> dict:
    _require(0 < len(raw) <= MAX_JSON_BYTES, f"{label} byte limit exceeded")
    quoted = escaped = False
    nesting = 0
    for character in raw:
        if quoted:
            if escaped:
                escaped = False
            elif character == 92:
                escaped = True
            elif character == 34:
                quoted = False
        elif character == 34:
            quoted = True
        elif character in (123, 91):
            nesting += 1
            _require(nesting <= MAX_JSON_DEPTH, f"{label} exceeds JSON nesting limit")
        elif character in (125, 93):
            nesting -= 1
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_int=_int_token, parse_float=_noninteger_number,
            parse_constant=_noninteger_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{label} invalid JSON") from exc
    _require(type(value) is dict, f"{label} must be an object")
    return value


def _same(actual, expected, *, label: str) -> None:
    _require(type(actual) is type(expected), f"{label} type differs")
    if type(expected) is dict:
        _require(set(actual) == set(expected), f"{label} fields differ")
        for key in expected:
            _same(actual[key], expected[key], label=f"{label}.{key}")
    elif type(expected) is list:
        _require(len(actual) == len(expected), f"{label} count differs")
        for index, (left, right) in enumerate(zip(actual, expected)):
            _same(left, right, label=f"{label}[{index}]")
    else:
        _require(actual == expected, f"{label} differs from independent replay")


def _inventory(directory: Path) -> None:
    _require(".." not in directory.parts and not directory.is_symlink(),
             "bundle directory cannot be a symlink or contain traversal")
    _require(directory.is_dir(), "bundle directory does not exist")
    names = {item.name for item in directory.iterdir()}
    _require(names == EXPECTED_FILES, "bundle must contain exactly the five expected files")


def _capture(directory: Path) -> dict[str, bytes]:
    _inventory(directory)
    files = {
        name: audit._capture_csv_bytes(directory / name, label=f"bundle {name}")
        for name in sorted(EXPECTED_FILES)
    }
    _inventory(directory)
    return files


def _positive_id(value: str, *, label: str) -> None:
    _require(re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None,
             f"{label} must be a positive decimal identifier")


def verify_bundle(directory: Path, *, repository: str, checkout_sha: str,
                  run_id: str, run_attempt: str) -> dict:
    """Bind five stable bundle files to external run pins and independent CSV replay."""
    _require(re.fullmatch(r"[0-9a-f]{40}", checkout_sha) is not None,
             "expected checkout SHA must be a full lower-case commit hash")
    _require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is not None,
             "invalid expected GitHub repository")
    _positive_id(run_id, label="run ID")
    _positive_id(run_attempt, label="run attempt")
    directory = Path(directory)
    raw = _capture(directory)
    digests = {name: hashlib.sha256(raw[name]).hexdigest() for name in FILES}
    index = _parse_metadata(raw[INDEX], label="bundle index")
    _same(index, {
        "schema_version": 2,
        "status": STATUS,
        "repository": repository,
        "checkout_commit_sha": checkout_sha,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "files_sha256": dict(sorted(digests.items())),
        "frozen_confirmatory_inference_changed": False,
        "original_execution_authenticated": False,
        "human_validation_performed": False,
    }, label="bundle index")

    # Invoke verifier implementations, not the diagnostic producers. Each
    # verifier re-reads and validates the frozen CSVs independently.
    for diagnostic, receipt, verifier in (
        ("retrieval_exposure.json", "retrieval_exposure_verification.json", exposure),
        ("claim_denominators.json", "claim_denominators_verification.json", denominators),
    ):
        recorded = _parse_metadata(raw[receipt], label=receipt)
        recomputed = verifier.verify_published(directory / diagnostic)
        _same(recorded, recomputed, label=receipt)
        _require(recorded["diagnostic_sha256"] == digests[diagnostic],
                 f"{receipt} does not bind the diagnostic bytes")

    # Detect observed content changes while independently replaying source rows.
    _require(raw == _capture(directory), "bundle bytes changed during verification")
    return {
        "schema_version": 1,
        "status": STATUS,
        "repository": repository,
        "checkout_commit_sha": checkout_sha,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "files_verified": len(EXPECTED_FILES),
        "cells_checked_per_diagnostic": 40,
        "paired_contrast_rows_checked_per_diagnostic": 30,
        "frozen_confirmatory_inference_changed": False,
        "original_execution_authenticated": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-checkout-sha", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-run-attempt", required=True)
    args = parser.parse_args()
    try:
        receipt = verify_bundle(
            args.directory, repository=args.expected_repository,
            checkout_sha=args.expected_checkout_sha, run_id=args.expected_run_id,
            run_attempt=args.expected_run_attempt,
        )
    except (OSError, ValueError, audit.InputIntegrityError) as exc:
        parser.exit(1, f"EXPLORATORY BUNDLE: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
