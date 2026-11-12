"""Offline replay of a downloaded VERA CI log and its exact-revision receipt.

A successful replay establishes local consistency with explicitly supplied run
identity and checked-out dependency pins; it does not attest GitHub Actions,
runner network isolation, or scientific experiment provenance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from scripts import verify_ci_test_evidence as producer
from scripts import verify_ci_python_runtime as runtime

MAX_RECEIPT_BYTES = 16 * 1024
PYTHON_VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key in retained CI receipt: {key}")
        result[key] = value
    return result


def _reject_float(token: str) -> float:
    raise ValueError("floating-point values are not valid in retained CI receipt")


def _reject_constant(token: str) -> float:
    raise ValueError("nonfinite value in retained CI receipt")


def _strictly_equal(actual: object, expected: object) -> bool:
    """Avoid bool==1 and recursive JSON coercion passing schema comparisons."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _strictly_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _strictly_equal(a, b) for a, b in zip(actual, expected)
        )
    return actual == expected


def verify_retained_evidence(
    log: bytes,
    receipt_bytes: bytes,
    *,
    checkout_sha: str,
    run_id: str,
    run_attempt: str,
    event: str,
    dependency_bytes: dict[str, bytes],
) -> dict:
    """Recompute all fields except informational producer Python patch version.

    The checkout SHA, run, attempt and event must come from a source separate
    from the untrusted receipt; never populate expectations by reading it.
    """
    if type(receipt_bytes) is not bytes or not 0 < len(receipt_bytes) <= MAX_RECEIPT_BYTES:
        raise ValueError("retained CI receipt is missing or oversized")
    try:
        receipt = json.loads(
            receipt_bytes.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("retained CI receipt is not valid UTF-8 JSON") from exc
    if type(receipt) is not dict:
        raise ValueError("retained CI receipt must be a JSON object")
    canonical = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True)
                 + "\n").encode("utf-8")
    if receipt_bytes != canonical:
        raise ValueError("retained CI receipt does not match producer serialization")
    version = receipt.get("python_version")
    if type(version) is not str or not PYTHON_VERSION_PATTERN.fullmatch(version):
        raise ValueError("invalid producer Python version")
    if version != runtime.PINNED_VERSION_TEXT:
        raise ValueError("retained CI receipt Python version differs from the pinned test runtime")

    expected = producer.build_receipt(
        log,
        context={
            "GITHUB_REPOSITORY": "anupamking01/Ai-Researcher-Agent",
            "GITHUB_SHA": checkout_sha,
            "GITHUB_RUN_ID": run_id,
            "GITHUB_RUN_ATTEMPT": run_attempt,
            "GITHUB_EVENT_NAME": event,
        },
        checkout_sha=checkout_sha,
        dependency_bytes=dependency_bytes,
    )
    # The audit host need not use the same Python patch release as CI.
    expected["python_version"] = version
    if not _strictly_equal(receipt, expected):
        raise ValueError("retained CI receipt does not match log, pins, or independently supplied run identity")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--event", choices=("push", "pull_request", "workflow_dispatch"), required=True)
    args = parser.parse_args()
    try:
        # Checkout must already be exactly the tested SHA, including synthetic
        # merge commits for pull-request workflows.
        current_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=producer.ROOT, text=True
        ).strip()
        if current_sha != args.checkout_sha:
            raise ValueError("current checkout is not the explicitly supplied tested SHA")
        if args.receipt.stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError("retained CI receipt exceeds size limit")
        if args.log.stat().st_size > producer.MAX_LOG_BYTES:
            raise ValueError("retained CI log exceeds size limit")
        verify_retained_evidence(
            args.log.read_bytes(), args.receipt.read_bytes(),
            checkout_sha=args.checkout_sha, run_id=args.run_id,
            run_attempt=args.run_attempt, event=args.event,
            dependency_bytes={
                name: (producer.ROOT / name).read_bytes()
                for name in ("requirements.txt", "requirements-ci.lock")
            },
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"VERA RETAINED CI EVIDENCE: FAIL: {exc}\n")
    print("VERA RETAINED CI EVIDENCE: LOCALLY CONSISTENT (not independently attested)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
