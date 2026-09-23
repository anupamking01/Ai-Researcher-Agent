"""Independently verify a recorded main-study analysis provenance receipt.

This reviewer-facing verifier checks that a success receipt still describes the
exact current analysis inputs, implementation, frozen plan, pinned dependency
environment, interpreter contract, configuration, and final result artifacts. It
makes no network calls and does not regenerate results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts import analyze_main_study
from scripts.build_analysis_provenance import (
    ANALYSIS_PLAN,
    ANALYSIS_PYTHON_VERSION,
    ANALYSIS_REQUIREMENTS,
    ANALYSIS_SCRIPT,
)
from scripts.verify_main_study_outputs import DEFAULT_JSON, DEFAULT_MARKDOWN
from scripts.verify_research_artifact_manifest import REPO_ROOT, verify_manifest

DEFAULT_RECEIPT = Path("outputs/main_study_analysis_provenance.json")
CANONICAL_INPUTS = {"outputs/main_study_runs.csv", "outputs/posthoc_support_runs.csv"}


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"provenance-bound artifact is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(entry: object, *, label: str, root: Path) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} provenance entry must be an object")
    path = entry.get("path")
    digest = entry.get("sha256")
    if not isinstance(path, str) or not path or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{label} provenance entry must contain path and SHA-256")
    actual = _sha256(root / path)
    if actual != digest:
        raise ValueError(f"{label} SHA-256 mismatch: {path}")


def _require_canonical_hash(entry: object, *, label: str, expected_path: Path, root: Path) -> None:
    """Verify a hash entry only after pinning it to its canonical repository path."""
    if not isinstance(entry, dict) or entry.get("path") != expected_path.as_posix():
        raise ValueError(f"{label} provenance must bind canonical path: {expected_path.as_posix()}")
    _require_hash(entry, label=label, root=root)


def _verify_inputs(receipt: dict, *, root: Path) -> None:
    """Reconstruct and verify the original canonical input manifest from the receipt."""
    aggregate = receipt.get("input_manifest_aggregate_sha256")
    if not isinstance(aggregate, str) or len(aggregate) != 64:
        raise ValueError("receipt is missing a valid input-manifest aggregate SHA-256")
    inputs = receipt.get("verified_inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("receipt must embed the verified analysis inputs")
    manifested = {
        entry.get("path") for entry in inputs if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    if len(manifested) != len(inputs) or manifested != CANONICAL_INPUTS:
        raise ValueError("receipt must bind exactly the canonical analysis input paths")
    verify_manifest(
        {
            "schema_version": 1,
            "algorithm": "sha256",
            "artifacts": inputs,
            "aggregate_sha256": aggregate,
        },
        root=root,
    )


def verify_receipt(receipt: dict, *, root: Path = REPO_ROOT) -> None:
    """Fail closed unless the receipt matches every current bound artifact/knob."""
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise ValueError("unsupported or malformed analysis provenance receipt")
    _verify_inputs(receipt, root=root)

    implementation = receipt.get("analysis_implementation")
    plan = receipt.get("analysis_plan")
    if not isinstance(implementation, dict) or implementation.get("path") != ANALYSIS_SCRIPT:
        raise ValueError("receipt does not bind the canonical analysis implementation")
    if not isinstance(plan, dict) or plan.get("path") != ANALYSIS_PLAN:
        raise ValueError("receipt does not bind the canonical frozen analysis plan")
    _require_hash(implementation, label="analysis implementation", root=root)
    _require_hash(plan, label="analysis plan", root=root)

    environment = receipt.get("analysis_environment")
    if not isinstance(environment, dict) or set(environment) != {"requirements", "python_version"}:
        raise ValueError("receipt must bind the pinned analysis dependency and Python environment")
    requirements = environment["requirements"]
    if not isinstance(requirements, dict) or requirements.get("path") != ANALYSIS_REQUIREMENTS:
        raise ValueError("receipt does not bind the canonical pinned requirements")
    _require_hash(requirements, label="analysis requirements", root=root)
    python_version = environment["python_version"]
    if not isinstance(python_version, dict) or python_version.get("path") != ANALYSIS_PYTHON_VERSION:
        raise ValueError("receipt does not bind the canonical Python version contract")
    _require_hash(python_version, label="analysis Python version", root=root)

    expected_configuration = {
        "variants": list(analyze_main_study.VARIANTS),
        "primary_contrasts": [list(item) for item in analyze_main_study.PRIMARY_CONTRASTS],
        "bootstrap_seed": analyze_main_study.BOOTSTRAP_SEED,
        "bootstrap_draws": analyze_main_study.BOOTSTRAP_DRAWS,
        "expected_tasks": analyze_main_study.EXPECTED_TASKS,
    }
    if receipt.get("frozen_configuration") != expected_configuration:
        raise ValueError("receipt frozen configuration does not match current analysis")

    outputs = receipt.get("verified_outputs")
    if not isinstance(outputs, dict) or set(outputs) != {"canonical_inference", "manuscript_rendering"}:
        raise ValueError("receipt must bind exactly both verified main-study outputs")
    _require_canonical_hash(
        outputs["canonical_inference"],
        label="canonical inference",
        expected_path=DEFAULT_JSON,
        root=root,
    )
    _require_canonical_hash(
        outputs["manuscript_rendering"],
        label="manuscript rendering",
        expected_path=DEFAULT_MARKDOWN,
        root=root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", nargs="?", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    path = args.receipt if args.receipt.is_absolute() else REPO_ROOT / args.receipt
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        verify_receipt(receipt)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"ANALYSIS PROVENANCE VERIFICATION: FAIL: {exc}") from exc
    print("ANALYSIS PROVENANCE VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
