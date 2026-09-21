"""Run main-study inference only after provenance and numeric-integrity checks.

This is the preferred entry point for manuscript-facing analysis. It binds the
analysis to a previously recorded SHA-256 manifest, verifies the exact input
bytes, validates scientific numeric domains, and only then executes the frozen
analysis. A deterministic provenance receipt is written only after successful
analysis, binding the run to its exact inputs, implementation, and frozen plan.
No input is repaired or rewritten.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Callable

from scripts import analyze_main_study
from scripts.build_analysis_provenance import build_receipt
from scripts.validate_main_study_inputs import validate_rows
from scripts.verify_research_artifact_manifest import REPO_ROOT, verify_manifest

CANONICAL_MAIN = "outputs/main_study_runs.csv"
CANONICAL_SUPPORT = "outputs/posthoc_support_runs.csv"
REQUIRED_INPUTS = {CANONICAL_MAIN, CANONICAL_SUPPORT}
DEFAULT_PROVENANCE_OUTPUT = "outputs/main_study_analysis_provenance.json"


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_and_run(
    manifest: dict,
    *,
    root: Path = REPO_ROOT,
    analyze: Callable[[], int] = analyze_main_study.main,
) -> int:
    """Verify provenance/integrity before invoking the frozen analysis.

    The manifest must describe exactly the two canonical CSV inputs. Requiring
    an exact set prevents a valid hash for unrelated files from being mistaken
    for provenance of the data actually consumed by the analysis.
    """
    entries = verify_manifest(manifest, root=root)
    manifested = {entry["path"] for entry in entries}
    if manifested != REQUIRED_INPUTS:
        missing = sorted(REQUIRED_INPUTS - manifested)
        extra = sorted(manifested - REQUIRED_INPUTS)
        raise ValueError(
            f"manifest must bind exactly the canonical analysis inputs; "
            f"missing={missing}, extra={extra}"
        )

    main_rows = _read_rows(root / CANONICAL_MAIN)
    support_rows = _read_rows(root / CANONICAL_SUPPORT)
    validate_rows(main_rows, support_rows)
    return analyze()


def verify_run_and_record(
    manifest: dict,
    *,
    root: Path = REPO_ROOT,
    analyze: Callable[[], int] = analyze_main_study.main,
    receipt_builder: Callable[..., dict] = build_receipt,
    output: Path | None = None,
) -> int:
    """Run verified inference and persist provenance only for a successful run.

    The receipt is built before inference so missing/drifted analysis code or
    plan fails closed. It is written only when the analysis returns zero, so a
    receipt can never be mistaken for evidence that a failed analysis finished.
    """
    receipt = receipt_builder(manifest, root=root)
    result = verify_and_run(manifest, root=root, analyze=analyze)
    if result != 0:
        return result

    destination = output or root / DEFAULT_PROVENANCE_OUTPUT
    if not destination.is_absolute():
        destination = root / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="previously recorded research-artifact manifest")
    parser.add_argument(
        "--provenance-output",
        type=Path,
        default=Path(DEFAULT_PROVENANCE_OUTPUT),
        help="receipt written only after successful verified analysis",
    )
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = verify_run_and_record(payload, output=args.provenance_output)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"VERIFIED MAIN-STUDY ANALYSIS: FAIL: {exc}") from exc
    if result == 0:
        print("VERIFIED MAIN-STUDY ANALYSIS: PASS (provenance receipt recorded)")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
