"""Independently verify a recorded main-study analysis provenance receipt.

This reviewer-facing verifier checks that a success receipt still describes the
exact current analysis inputs, implementation, frozen plan, pinned dependency
environment, interpreter contract, provenance builder, verification implementations,
configuration, and final result artifacts. It then re-executes the frozen offline
analysis from private snapshots and requires exact result-byte equality. It makes
no network calls and never replaces published results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import analyze_main_study
from scripts.build_analysis_provenance import (
    ANALYSIS_OUTPUT_VERIFIER,
    ANALYSIS_PLAN,
    ANALYSIS_PROVENANCE_BUILDER,
    ANALYSIS_PYTHON_VERSION,
    ANALYSIS_REQUIREMENTS,
    ANALYSIS_SCRIPT,
    ANALYSIS_VERIFIER,
)
from scripts.verify_main_study_outputs import (
    DEFAULT_JSON,
    DEFAULT_MARKDOWN,
    verify_outputs,
)
from scripts.verify_research_artifact_manifest import REPO_ROOT, verify_manifest

DEFAULT_RECEIPT = Path("outputs/main_study_analysis_provenance.json")
CANONICAL_INPUTS = {"outputs/main_study_runs.csv", "outputs/posthoc_support_runs.csv"}
RECOMPUTE_DRIVER = """\
import importlib.util
from pathlib import Path
import sys

implementation = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("vera_frozen_analysis", implementation)
if spec is None or spec.loader is None:
    raise SystemExit("unable to load frozen analysis implementation")
analyze_main_study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_main_study)
analyze_main_study.MAIN_CSV = Path(sys.argv[2])
analyze_main_study.SUPPORT_CSV = Path(sys.argv[3])
analyze_main_study.OUT_JSON = Path(sys.argv[4])
analyze_main_study.OUT_MD = Path(sys.argv[5])
raise SystemExit(analyze_main_study.main())
"""


def _regular_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


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

    builder = receipt.get("provenance_builder")
    if not isinstance(builder, dict) or builder.get("path") != ANALYSIS_PROVENANCE_BUILDER:
        raise ValueError("receipt does not bind the canonical provenance builder")
    _require_hash(builder, label="analysis provenance builder", root=root)

    verifiers = receipt.get("verification_implementations")
    if not isinstance(verifiers, dict) or set(verifiers) != {"provenance", "output_consistency"}:
        raise ValueError("receipt must bind the complete canonical verification chain")
    provenance_verifier = verifiers["provenance"]
    if not isinstance(provenance_verifier, dict) or provenance_verifier.get("path") != ANALYSIS_VERIFIER:
        raise ValueError("receipt does not bind the canonical provenance verifier")
    _require_hash(provenance_verifier, label="analysis provenance verifier", root=root)
    output_verifier = verifiers["output_consistency"]
    if not isinstance(output_verifier, dict) or output_verifier.get("path") != ANALYSIS_OUTPUT_VERIFIER:
        raise ValueError("receipt does not bind the canonical output-consistency verifier")
    _require_hash(output_verifier, label="analysis output-consistency verifier", root=root)

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
        outputs["canonical_inference"], label="canonical inference", expected_path=DEFAULT_JSON, root=root
    )
    _require_canonical_hash(
        outputs["manuscript_rendering"], label="manuscript rendering", expected_path=DEFAULT_MARKDOWN, root=root
    )


def _captured_input_snapshots(
    receipt: dict,
    *,
    root: Path,
    snapshot_root: Path,
) -> tuple[dict[str, Path], dict[str, bytes]]:
    """Capture the exact receipt-bound input bytes for isolated recomputation."""
    entries = receipt.get("verified_inputs")
    if not isinstance(entries, list):
        raise ValueError("receipt must embed the verified analysis inputs")
    by_path = {
        entry.get("path"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    if set(by_path) != CANONICAL_INPUTS or len(by_path) != len(entries):
        raise ValueError("receipt must bind exactly the canonical analysis input paths")

    snapshots = {}
    captured_bytes = {}
    for relative in sorted(CANONICAL_INPUTS):
        source = root / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"analysis input must be a regular file: {relative}")
        before = source.stat()
        content = source.read_bytes()
        after = source.stat()
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after:
            raise ValueError(
                f"analysis input changed while capturing recomputation snapshot: {relative}"
            )
        expected = by_path[relative]
        if (
            type(expected.get("bytes")) is not int
            or len(content) != expected["bytes"]
            or hashlib.sha256(content).hexdigest() != expected.get("sha256")
        ):
            raise ValueError(
                f"analysis input does not match recomputation receipt: {relative}"
            )
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        snapshots[relative] = destination
        captured_bytes[relative] = content
    return snapshots, captured_bytes


def _require_inputs_unchanged(
    captured_bytes: dict[str, bytes],
    *,
    root: Path,
) -> None:
    for relative, expected in captured_bytes.items():
        source = root / relative
        if (
            source.is_symlink()
            or not source.is_file()
            or source.read_bytes() != expected
        ):
            raise ValueError(
                f"analysis input changed during independent recomputation: {relative}"
            )


def _capture_analysis_implementation(
    receipt: dict,
    *,
    root: Path,
    runtime_root: Path,
) -> Path:
    """Copy the exact receipt-bound analyzer into the isolated runtime."""
    entry = receipt.get("analysis_implementation")
    if not isinstance(entry, dict) or entry.get("path") != ANALYSIS_SCRIPT:
        raise ValueError("receipt does not bind the canonical analysis implementation")
    content = _regular_bytes(
        root / ANALYSIS_SCRIPT,
        label="analysis implementation",
    )
    if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
        raise ValueError(
            "analysis implementation does not match recomputation receipt"
        )
    destination = runtime_root / ANALYSIS_SCRIPT
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def verify_recomputed_outputs(
    receipt: dict,
    *,
    root: Path = REPO_ROOT,
) -> None:
    """Re-execute frozen inference from snapshots and compare exact result bytes."""
    root = Path(root)
    published_json = _regular_bytes(
        root / DEFAULT_JSON,
        label="published canonical inference JSON",
    )
    published_markdown = _regular_bytes(
        root / DEFAULT_MARKDOWN,
        label="published manuscript inference Markdown",
    )
    with tempfile.TemporaryDirectory(prefix="vera-main-recompute-") as tmp_name:
        recompute_root = Path(tmp_name)
        runtime_root = recompute_root / "runtime"
        implementation_snapshot = _capture_analysis_implementation(
            receipt,
            root=root,
            runtime_root=runtime_root,
        )
        snapshots, captured_bytes = _captured_input_snapshots(
            receipt,
            root=root,
            snapshot_root=recompute_root / "inputs",
        )
        recomputed_json = recompute_root / DEFAULT_JSON
        recomputed_markdown = recompute_root / DEFAULT_MARKDOWN
        recomputed_json.parent.mkdir(parents=True, exist_ok=True)
        recomputed_markdown.parent.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                        "-I",
                    "-c",
                    RECOMPUTE_DRIVER,
                        str(implementation_snapshot),
                    str(snapshots["outputs/main_study_runs.csv"]),
                    str(snapshots["outputs/posthoc_support_runs.csv"]),
                    str(recomputed_json),
                    str(recomputed_markdown),
                ],
                cwd=runtime_root,
                check=False,
                timeout=300,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("unable to independently recompute main-study analysis") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip()
            suffix = f": {detail}" if detail else ""
            raise ValueError(
                f"independent main-study recomputation failed{suffix}"
            )

        verify_outputs(
            root=root,
            json_path=recomputed_json,
            markdown_path=recomputed_markdown,
        )
        if recomputed_json.read_bytes() != published_json:
            raise ValueError(
                "independently recomputed canonical JSON does not match published analysis"
            )
        if recomputed_markdown.read_bytes() != published_markdown:
            raise ValueError(
                "independently recomputed Markdown does not match published analysis"
            )
        if _regular_bytes(
            root / DEFAULT_JSON,
            label="published canonical inference JSON",
        ) != published_json:
            raise ValueError(
                "published canonical inference JSON changed during independent recomputation"
            )
        if _regular_bytes(
            root / DEFAULT_MARKDOWN,
            label="published manuscript inference Markdown",
        ) != published_markdown:
            raise ValueError(
                "published manuscript inference Markdown changed during independent recomputation"
            )
        _require_inputs_unchanged(captured_bytes, root=root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", nargs="?", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    path = args.receipt if args.receipt.is_absolute() else REPO_ROOT / args.receipt
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        verify_receipt(receipt)
        verify_recomputed_outputs(receipt)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"ANALYSIS PROVENANCE VERIFICATION: FAIL: {exc}") from exc
    print("ANALYSIS PROVENANCE VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
