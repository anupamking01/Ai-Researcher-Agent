"""Run main-study inference only after provenance and numeric-integrity checks.

This is the preferred entry point for manuscript-facing analysis. It binds the
analysis to a previously recorded SHA-256 manifest, captures and re-verifies an
immutable snapshot of those exact input bytes, validates scientific numeric
domains on that snapshot, executes the frozen analysis from the same snapshot,
and verifies that manuscript-facing outputs are an exact rendering of canonical
machine-readable results. A deterministic provenance receipt binding both inputs
and final outputs is written only after all checks succeed. No input is repaired
or rewritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from scripts import analyze_main_study
from scripts.build_analysis_provenance import build_receipt
from scripts.validate_main_study_inputs import validate_rows
from scripts.verify_main_study_outputs import DEFAULT_JSON, DEFAULT_MARKDOWN, verify_outputs
from scripts.verify_research_artifact_manifest import REPO_ROOT, verify_manifest

CANONICAL_MAIN = "outputs/main_study_runs.csv"
CANONICAL_SUPPORT = "outputs/posthoc_support_runs.csv"
REQUIRED_INPUTS = {CANONICAL_MAIN, CANONICAL_SUPPORT}
DEFAULT_PROVENANCE_OUTPUT = "outputs/main_study_analysis_provenance.json"
VERIFIED_RUNNER = "scripts/run_verified_main_study_analysis.py"
EXECUTION_VERIFIER = "scripts/verify_main_study_execution.py"
SNAPSHOT_ANALYSIS_DRIVER = """\
from pathlib import Path
import sys
from scripts import analyze_main_study

analyze_main_study.MAIN_CSV = Path(sys.argv[1])
analyze_main_study.SUPPORT_CSV = Path(sys.argv[2])
analyze_main_study.OUT_JSON = Path(sys.argv[3])
analyze_main_study.OUT_MD = Path(sys.argv[4])
raise SystemExit(analyze_main_study.main())
"""


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _capture_verified_inputs(
    entries: list[dict], *, root: Path, snapshot_root: Path
) -> dict[str, Path]:
    """Capture and re-bind the exact bytes that the analysis will consume."""
    by_path = {entry["path"]: entry for entry in entries}
    captured = {}
    for relative in sorted(REQUIRED_INPUTS):
        content = (root / relative).read_bytes()
        expected = by_path[relative]
        if (
            len(content) != expected["bytes"]
            or hashlib.sha256(content).hexdigest() != expected["sha256"]
        ):
            raise ValueError(
                f"research artifact changed while capturing verified analysis input: {relative}"
            )
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        captured[relative] = destination
    return captured


def _run_analysis_from_snapshots(snapshots: dict[str, Path], *, root: Path) -> int:
    """Run the frozen analyzer in a process isolated from live module globals."""
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                SNAPSHOT_ANALYSIS_DRIVER,
                str(snapshots[CANONICAL_MAIN]),
                str(snapshots[CANONICAL_SUPPORT]),
                str(root / DEFAULT_JSON),
                str(root / DEFAULT_MARKDOWN),
            ],
            cwd=root,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("unable to execute isolated frozen analysis") from exc
    return completed.returncode


def _bind_verified_execution(receipt: dict, *, root: Path) -> dict:
    """Bind the orchestration layer and its independent verifier for future runs."""
    bound = dict(receipt)
    bound["verified_execution"] = {
        "runner": {"path": VERIFIED_RUNNER, "sha256": _sha256(root / VERIFIED_RUNNER)},
        "execution_verifier": {
            "path": EXECUTION_VERIFIER,
            "sha256": _sha256(root / EXECUTION_VERIFIER),
        },
    }
    return bound


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"verified analysis output is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind_verified_outputs(receipt: dict, *, root: Path) -> dict:
    """Return a receipt that cryptographically binds the verified result files.

    Output verification establishes semantic consistency between canonical JSON
    and manuscript Markdown. Hashing both exact byte streams afterwards makes
    the success receipt an attestation of the specific result artifacts that
    passed that check, rather than only an attestation of inputs/code/plan.
    """
    bound = dict(receipt)
    bound["verified_outputs"] = {
        "canonical_inference": {
            "path": DEFAULT_JSON.as_posix(),
            "sha256": _sha256(root / DEFAULT_JSON),
        },
        "manuscript_rendering": {
            "path": DEFAULT_MARKDOWN.as_posix(),
            "sha256": _sha256(root / DEFAULT_MARKDOWN),
        },
    }
    return bound


def verify_and_run(
    manifest: dict,
    *,
    root: Path = REPO_ROOT,
    analyze: Callable[[], int] | None = None,
) -> int:
    """Verify provenance/integrity before invoking the frozen analysis.

    The manifest must describe exactly the two canonical CSV inputs. Requiring
    an exact set prevents a valid hash for unrelated files from being mistaken
    for provenance of the data actually consumed by the analysis. Re-hashing the
    captured bytes closes the gap between live-file verification and analysis.
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

    with tempfile.TemporaryDirectory(prefix="vera-main-analysis-") as tmp_name:
        snapshots = _capture_verified_inputs(
            entries,
            root=root,
            snapshot_root=Path(tmp_name),
        )
        main_rows = _read_rows(snapshots[CANONICAL_MAIN])
        support_rows = _read_rows(snapshots[CANONICAL_SUPPORT])
        validate_rows(main_rows, support_rows)
        if analyze is not None:
            return analyze()
        return _run_analysis_from_snapshots(snapshots, root=root)


def verify_run_and_record(
    manifest: dict,
    *,
    root: Path = REPO_ROOT,
    analyze: Callable[[], int] | None = None,
    receipt_builder: Callable[..., dict] = build_receipt,
    output_verifier: Callable[..., None] = verify_outputs,
    output: Path | None = None,
) -> int:
    """Run verified inference and persist provenance only for a successful run.

    Any receipt from an earlier run is invalidated before this attempt starts.
    The input/code/plan receipt is prepared before inference so drift blocks
    execution. After inference succeeds, canonical JSON and manuscript Markdown
    must pass deterministic consistency verification; in the production path
    their exact bytes are then SHA-256-bound into the final receipt. Thus the
    receipt attests to the precise outputs that passed verification.

    An injected verifier is supported for unit tests; because such a verifier
    does not establish the canonical-output contract, output hashes are not
    attached in that dependency-injected path.
    """
    destination = output or root / DEFAULT_PROVENANCE_OUTPUT
    if not destination.is_absolute():
        destination = root / destination

    destination.unlink(missing_ok=True)

    receipt = receipt_builder(manifest, root=root)
    result = verify_and_run(manifest, root=root, analyze=analyze)
    if result != 0:
        return result

    output_verifier(root=root)
    if output_verifier is verify_outputs:
        receipt = _bind_verified_outputs(receipt, root=root)
    if output_verifier is verify_outputs and receipt_builder is build_receipt:
        receipt = _bind_verified_execution(receipt, root=root)
        from scripts.verify_main_study_execution import verify_execution_receipt

        verify_execution_receipt(receipt, root=root)

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
        help="receipt written only after successful verified analysis and output verification",
    )
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = verify_run_and_record(payload, output=args.provenance_output)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"VERIFIED MAIN-STUDY ANALYSIS: FAIL: {exc}") from exc
    if result == 0:
        print("VERIFIED MAIN-STUDY ANALYSIS: PASS (outputs verified and hash-bound; provenance receipt recorded)")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
