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
from contextlib import ExitStack
import hashlib
import json
import os
import stat
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
    ARTIFACT_FINGERPRINTER,
    ARTIFACT_MANIFEST_VERIFIER,
)
from scripts.fingerprint_research_artifacts import fingerprint_regular_file
from scripts.verify_main_study_outputs import (
    DEFAULT_JSON,
    DEFAULT_MARKDOWN,
    verify_outputs,
)
from scripts.verify_research_artifact_manifest import REPO_ROOT, verify_manifest

DEFAULT_RECEIPT = Path("outputs/main_study_analysis_provenance.json")
CANONICAL_INPUTS = {"outputs/main_study_runs.csv", "outputs/posthoc_support_runs.csv"}
RECEIPT_FIELDS = {
    "schema_version",
    "input_manifest_aggregate_sha256",
    "verified_inputs",
    "analysis_implementation",
    "analysis_plan",
    "analysis_environment",
    "provenance_builder",
    "verification_implementations",
    "frozen_configuration",
    "verified_outputs",
}
OPTIONAL_RECEIPT_FIELDS = {"verified_execution"}
BOUND_FILE_FIELDS = {"path", "sha256"}
EXECUTION_FIELDS = {"runner", "execution_verifier", "input_validator"}
EXECUTION_PATHS = {
    "runner": Path("scripts/run_verified_main_study_analysis.py"),
    "execution_verifier": Path("scripts/verify_main_study_execution.py"),
    "input_validator": Path("scripts/validate_main_study_inputs.py"),
}
SNAPSHOT_FILES = {
    "outputs/main_study_runs.csv": "analysis input",
    "outputs/posthoc_support_runs.csv": "analysis input",
    "outputs/main_study_inference.json": "published canonical inference JSON",
    "paper/MAIN_STUDY_INFERENCE.md": "published manuscript inference Markdown",
    "scripts/analyze_main_study.py": "analysis implementation",
}
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


def parse_receipt_json(content: str) -> object:
    """Parse a receipt without silently resolving duplicate object fields."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    return json.loads(content, object_pairs_hook=unique_object)


def _regular_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _directory_identity(descriptor: int) -> tuple[int, int, int, int]:
    metadata = os.fstat(descriptor)
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _open_bound_directory(
    path: Path | str,
    *,
    label: str,
    parent_descriptor: int | None = None,
) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular directory: {path}") from exc
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} must be a regular directory: {path}")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _require_directory_path_binding(
    path: Path,
    descriptor: int,
    *,
    label: str,
) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
        bound = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError(f"{label} changed during independent recomputation") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (bound.st_dev, bound.st_ino)
    ):
        raise ValueError(f"{label} changed during independent recomputation")


def _require_directory_entry_binding(
    parent_descriptor: int,
    name: str,
    descriptor: int,
    *,
    label: str,
) -> None:
    try:
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        bound = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError(f"{label} changed during independent recomputation") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (bound.st_dev, bound.st_ino)
    ):
        raise ValueError(f"{label} changed during independent recomputation")


def _regular_snapshot_from_descriptor(
    descriptor: int,
    *,
    label: str,
) -> tuple[bytes, tuple[int, int, int, int, int]]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a regular file")
    chunks = []
    offset = 0
    while True:
        chunk = os.pread(descriptor, 1024 * 1024, offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity:
        raise ValueError(f"{label} changed while it was being read")
    return b"".join(chunks), after_identity


def _open_regular_snapshot_at(
    directory_descriptor: int,
    name: str,
    *,
    label: str,
) -> tuple[int, tuple[bytes, tuple[int, int, int, int, int]]]:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular file") from exc
    try:
        snapshot = _regular_snapshot_from_descriptor(descriptor, label=label)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, snapshot


def _require_regular_entry_binding(
    directory_descriptor: int,
    name: str,
    file_descriptor: int,
    *,
    label: str,
) -> None:
    try:
        current = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        bound = os.fstat(file_descriptor)
    except OSError as exc:
        raise ValueError(f"{label} changed during independent recomputation") from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != (bound.st_dev, bound.st_ino)
    ):
        raise ValueError(f"{label} changed during independent recomputation")


def _open_repository_snapshot(descriptors: ExitStack, root: Path):
    root_descriptor = _open_bound_directory(root, label="repository root")
    descriptors.callback(os.close, root_descriptor)
    root_identity = _directory_identity(root_descriptor)
    _require_directory_path_binding(
        root,
        root_descriptor,
        label="repository root",
    )

    directories = {}
    files = {}
    for parent in sorted({Path(relative).parent.as_posix() for relative in SNAPSHOT_FILES}):
        directory_descriptor = _open_bound_directory(
            parent,
            label=f"repository {parent} directory",
            parent_descriptor=root_descriptor,
        )
        descriptors.callback(os.close, directory_descriptor)
        _require_directory_entry_binding(
            root_descriptor,
            parent,
            directory_descriptor,
            label=f"repository {parent} directory",
        )
        directory_identity = _directory_identity(directory_descriptor)
        for relative, label in SNAPSHOT_FILES.items():
            path = Path(relative)
            if path.parent.as_posix() != parent:
                continue
            file_descriptor, snapshot = _open_regular_snapshot_at(
                directory_descriptor,
                path.name,
                label=label,
            )
            descriptors.callback(os.close, file_descriptor)
            files[relative] = (
                directory_descriptor,
                file_descriptor,
                snapshot,
                label,
            )
        directories[parent] = (
            directory_descriptor,
            directory_identity,
        )
    return root_descriptor, root_identity, directories, files


def _require_repository_snapshot_stable(
    root: Path,
    root_descriptor: int,
    root_identity,
    directories,
    files,
) -> None:
    """Observe that every captured artifact stayed bound through recomputation."""
    for relative, (
        directory_descriptor,
        file_descriptor,
        original,
        label,
    ) in files.items():
        current = _regular_snapshot_from_descriptor(file_descriptor, label=label)
        if current != original:
            raise ValueError(f"{label} changed during independent recomputation")
        _require_regular_entry_binding(
            directory_descriptor,
            Path(relative).name,
            file_descriptor,
            label=label,
        )
    for parent, (directory_descriptor, identity) in directories.items():
        label = f"repository {parent} directory"
        if _directory_identity(directory_descriptor) != identity:
            raise ValueError(f"{label} changed during independent recomputation")
        _require_directory_entry_binding(
            root_descriptor,
            parent,
            directory_descriptor,
            label=label,
        )
    if _directory_identity(root_descriptor) != root_identity:
        raise ValueError("repository root changed during independent recomputation")
    _require_directory_path_binding(
        root,
        root_descriptor,
        label="repository root",
    )


def _sha256(path: Path) -> str:
    digest, _ = fingerprint_regular_file(path)
    return digest


def _require_hash(entry: object, *, label: str, root: Path) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} provenance entry must be an object")
    if set(entry) != BOUND_FILE_FIELDS:
        raise ValueError(
            f"{label} provenance entry must contain exactly path and SHA-256"
        )
    path = entry.get("path")
    digest = entry.get("sha256")
    if not isinstance(path, str) or not path or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{label} provenance entry must contain path and SHA-256")
    try:
        actual = _sha256(root / path)
    except ValueError as exc:
        raise ValueError(
            f"{label} must bind a stable regular file: {root / path}"
        ) from exc
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
    if not isinstance(receipt, dict):
        raise ValueError("unsupported or malformed analysis provenance receipt")
    unexpected = set(receipt) - RECEIPT_FIELDS - OPTIONAL_RECEIPT_FIELDS
    if unexpected:
        raise ValueError(f"receipt contains unexpected root fields: {sorted(unexpected)}")
    schema_version = receipt.get("schema_version")
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise ValueError("unsupported or malformed analysis provenance receipt")
    if "verified_execution" in receipt:
        execution = receipt["verified_execution"]
        if not isinstance(execution, dict) or set(execution) != EXECUTION_FIELDS:
            raise ValueError(
                "verified execution must contain exact execution provenance fields"
            )
        _require_canonical_hash(
            execution["runner"],
            label="execution runner",
            expected_path=EXECUTION_PATHS["runner"],
            root=root,
        )
        _require_canonical_hash(
            execution["execution_verifier"],
            label="execution verifier",
            expected_path=EXECUTION_PATHS["execution_verifier"],
            root=root,
        )
        _require_canonical_hash(
            execution["input_validator"],
            label="input validator",
            expected_path=EXECUTION_PATHS["input_validator"],
            root=root,
        )
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
    expected_verifiers = {"provenance", "output_consistency"}
    if schema_version == 2:
        expected_verifiers |= {"artifact_manifest", "artifact_fingerprinter"}
    if not isinstance(verifiers, dict) or set(verifiers) != expected_verifiers:
        raise ValueError("receipt must bind the complete canonical verification chain")
    provenance_verifier = verifiers["provenance"]
    if not isinstance(provenance_verifier, dict) or provenance_verifier.get("path") != ANALYSIS_VERIFIER:
        raise ValueError("receipt does not bind the canonical provenance verifier")
    _require_hash(provenance_verifier, label="analysis provenance verifier", root=root)
    output_verifier = verifiers["output_consistency"]
    if not isinstance(output_verifier, dict) or output_verifier.get("path") != ANALYSIS_OUTPUT_VERIFIER:
        raise ValueError("receipt does not bind the canonical output-consistency verifier")
    _require_hash(output_verifier, label="analysis output-consistency verifier", root=root)
    if schema_version == 2:
        artifact_manifest = verifiers["artifact_manifest"]
        if (
            not isinstance(artifact_manifest, dict)
            or artifact_manifest.get("path") != ARTIFACT_MANIFEST_VERIFIER
        ):
            raise ValueError(
                "receipt does not bind the canonical artifact manifest verifier"
            )
        _require_hash(
            artifact_manifest,
            label="artifact manifest verifier",
            root=root,
        )
        artifact_fingerprinter = verifiers["artifact_fingerprinter"]
        if (
            not isinstance(artifact_fingerprinter, dict)
            or artifact_fingerprinter.get("path") != ARTIFACT_FINGERPRINTER
        ):
            raise ValueError(
                "receipt does not bind the canonical artifact fingerprinter"
            )
        _require_hash(
            artifact_fingerprinter,
            label="artifact fingerprinter",
            root=root,
        )

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
    captured_files,
    snapshot_root: Path,
) -> dict[str, Path]:
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
    for relative in sorted(CANONICAL_INPUTS):
        content = captured_files[relative][2][0]
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
    return snapshots


def _capture_analysis_implementation(
    receipt: dict,
    *,
    content: bytes,
    runtime_root: Path,
) -> Path:
    """Copy the exact receipt-bound analyzer into the isolated runtime."""
    entry = receipt.get("analysis_implementation")
    if not isinstance(entry, dict) or entry.get("path") != ANALYSIS_SCRIPT:
        raise ValueError("receipt does not bind the canonical analysis implementation")
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
    with ExitStack() as descriptors:
        (
            root_descriptor,
            root_identity,
            directories,
            captured_files,
        ) = _open_repository_snapshot(descriptors, root)
        published_json = captured_files[DEFAULT_JSON.as_posix()][2][0]
        published_markdown = captured_files[DEFAULT_MARKDOWN.as_posix()][2][0]
        implementation = captured_files[ANALYSIS_SCRIPT][2][0]

        with tempfile.TemporaryDirectory(prefix="vera-main-recompute-") as tmp_name:
            recompute_root = Path(tmp_name)
            runtime_root = recompute_root / "runtime"
            implementation_snapshot = _capture_analysis_implementation(
                receipt,
                content=implementation,
                runtime_root=runtime_root,
            )
            snapshots = _captured_input_snapshots(
                receipt,
                captured_files=captured_files,
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
                raise ValueError(
                    "unable to independently recompute main-study analysis"
                ) from exc
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
            _require_repository_snapshot_stable(
                root,
                root_descriptor,
                root_identity,
                directories,
                captured_files,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", nargs="?", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    path = args.receipt if args.receipt.is_absolute() else REPO_ROOT / args.receipt
    try:
        receipt = parse_receipt_json(path.read_text(encoding="utf-8"))
        verify_receipt(receipt)
        verify_recomputed_outputs(receipt)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"ANALYSIS PROVENANCE VERIFICATION: FAIL: {exc}") from exc
    print("ANALYSIS PROVENANCE VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
