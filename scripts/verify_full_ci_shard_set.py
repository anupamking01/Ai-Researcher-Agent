"""Independently replay all eight retained offline CI shard evidence bundles.

This verifies complete *local* coverage of the source-tree module inventory at
one externally specified GitHub run identity. It does not attest GitHub's
runner, actual test execution, network isolation, or research artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from scripts import select_full_ci_shard as selector
from scripts import verify_ci_source_checkout as source_checker
from scripts import verify_ci_test_evidence as producer
from scripts import verify_retained_ci_test_evidence as replay

EVIDENCE_FILES = frozenset({
    "vera-offline-tests.log",
    "vera-offline-test-receipt.json",
    "vera-offline-test-modules.txt",
})



def _require_exact_entries(directory: Path, expected: set[str] | frozenset[str], *, message: str) -> None:
    """Fail on the first surplus downloaded entry, without unbounded listing.

    Retained artifact directories are untrusted local input. Materializing a
    set from every name before comparing it to the expected fixed inventory
    permits a huge directory to consume unbounded memory. The ninth shard or
    fourth file is already proof of invalid evidence.
    """
    observed: set[str] = set()
    with os.scandir(directory) as entries:
        for entry in entries:
            if len(observed) >= len(expected):
                raise ValueError(message)
            observed.add(entry.name)
    if observed != expected:
        raise ValueError(message)


def verify_shard_set(
    evidence_root: Path, *, checkout_sha: str, run_id: str,
    run_attempt: str, event: str, dependency_bytes: dict[str, bytes],
) -> dict:
    """Verify every shard with independent identity, then its global coverage."""
    evidence_root = Path(evidence_root)
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise ValueError("evidence root must be a real directory")
    expected_dirs = {f"shard-{index}" for index in range(selector.SHARDS)}
    _require_exact_entries(
        evidence_root, expected_dirs,
        message="missing or unexpected CI shard evidence directory",
    )

    all_modules: list[str] = []
    per_shard = []
    counts: dict[str, int] = {}
    for index in range(selector.SHARDS):
        folder = evidence_root / f"shard-{index}"
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f"shard {index} evidence directory is not real")
        _require_exact_entries(
            folder, EVIDENCE_FILES,
            message=f"shard {index} evidence files are incomplete or unexpected",
        )
        log = producer.read_bounded_evidence(
            folder / "vera-offline-tests.log",
            maximum=producer.MAX_LOG_BYTES, label=f"shard {index} log",
        )
        receipt_bytes = producer.read_bounded_evidence(
            folder / "vera-offline-test-receipt.json",
            maximum=replay.MAX_RECEIPT_BYTES, label=f"shard {index} receipt",
        )
        selected_bytes = producer.read_bounded_evidence(
            folder / "vera-offline-test-modules.txt",
            maximum=producer.MAX_SELECTED_MODULES_BYTES,
            label=f"shard {index} module inventory",
        )
        receipt = replay.verify_retained_evidence(
            log, receipt_bytes, checkout_sha=checkout_sha, run_id=run_id,
            run_attempt=run_attempt, event=event,
            dependency_bytes=dependency_bytes, selected_modules=selected_bytes,
            shard=index,
        )
        modules = selected_bytes.decode("utf-8").splitlines()
        if len(modules) != receipt["full_ci_selected_module_count"]:
            raise ValueError(f"shard {index} module count disagrees with receipt")
        all_modules.extend(modules)
        for name, value in receipt["test_counts"].items():
            counts[name] = counts.get(name, 0) + value
        per_shard.append({
            "shard": index,
            "n_modules": len(modules),
            "n_passed": receipt["test_counts"]["passed"],
            "log_sha256": hashlib.sha256(log).hexdigest(),
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "selected_modules_sha256": hashlib.sha256(selected_bytes).hexdigest(),
        })

    discovered = selector.discover_modules(producer.ROOT)
    selector.verify_partition(discovered)
    if len(all_modules) != len(set(all_modules)) or sorted(all_modules) != list(discovered):
        raise ValueError("eight retained shards do not cover each source test module exactly once")
    return {
        "status": "complete_eight_shard_local_replay_consistent_not_independently_attested",
        "checkout_sha": checkout_sha,
        "workflow_event": event,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "shards_verified": len(per_shard),
        "source_test_modules_covered": len(discovered),
        "aggregate_test_counts": dict(sorted(counts.items())),
        "per_shard": per_shard,
        "experimental_treatments_or_evaluators_run": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument(
        "--event", required=True,
        choices=("push", "pull_request", "workflow_dispatch"),
    )
    args = parser.parse_args()
    try:
        # Require exact checkout bytes, not just a matching branch name/HEAD.
        source_checker.verify_source_checkout(
            producer.ROOT, expected_sha=args.checkout_sha
        )
        result = verify_shard_set(
            args.evidence_root, checkout_sha=args.checkout_sha,
            run_id=args.run_id, run_attempt=args.run_attempt, event=args.event,
            dependency_bytes={
                name: (producer.ROOT / name).read_bytes()
                for name in ("requirements.txt", "requirements-ci.lock")
            },
        )
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, f"VERA FULL CI SHARD SET: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
