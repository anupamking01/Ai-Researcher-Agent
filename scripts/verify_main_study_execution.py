"""Verify the snapshot runner recorded by an execution-bound main-study receipt.

Historical receipts that predate this execution-layer binding remain verifiable
with ``verify_analysis_provenance.py``. Receipts produced by the verified runner
add ``verified_execution`` and can be checked here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.verify_analysis_provenance import DEFAULT_RECEIPT, verify_receipt
from scripts.verify_research_artifact_manifest import REPO_ROOT

RUNNER_PATH = "scripts/run_verified_main_study_analysis.py"
EXECUTION_VERIFIER_PATH = "scripts/verify_main_study_execution.py"


def _require_bound_file(entry: object, *, label: str, expected_path: str, root: Path) -> None:
    if (
        not isinstance(entry, dict)
        or set(entry) != {"path", "sha256"}
        or entry.get("path") != expected_path
    ):
        raise ValueError(f"{label} must bind canonical path {expected_path}")
    path = root / expected_path
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if entry.get("sha256") != actual:
        raise ValueError(f"{label} SHA-256 mismatch: {expected_path}")


def verify_execution_receipt(receipt: dict, *, root: Path = REPO_ROOT) -> None:
    """Verify legacy provenance plus the exact snapshot execution layer."""
    root = Path(root)
    verify_receipt(receipt, root=root)
    execution = receipt.get("verified_execution")
    if not isinstance(execution, dict) or set(execution) != {
        "runner",
        "execution_verifier",
    }:
        raise ValueError("receipt must bind the complete execution provenance")
    _require_bound_file(
        execution["runner"],
        label="runner",
        expected_path=RUNNER_PATH,
        root=root,
    )
    _require_bound_file(
        execution["execution_verifier"],
        label="execution verifier",
        expected_path=EXECUTION_VERIFIER_PATH,
        root=root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", nargs="?", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    path = args.receipt if args.receipt.is_absolute() else REPO_ROOT / args.receipt
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        verify_execution_receipt(receipt)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"MAIN-STUDY EXECUTION VERIFICATION: FAIL: {exc}") from exc
    print("MAIN-STUDY EXECUTION VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
