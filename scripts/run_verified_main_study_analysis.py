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
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

from scripts import analyze_main_study
from scripts.build_analysis_provenance import build_receipt
from scripts.fingerprint_research_artifacts import (
    fingerprint_regular_file,
    fingerprint_regular_file_with_identity,
)
from scripts.verify_main_study_outputs import DEFAULT_JSON, DEFAULT_MARKDOWN, verify_outputs
from scripts.verify_research_artifact_manifest import (
    REPO_ROOT,
    parse_manifest_json,
    verify_manifest,
)

CANONICAL_MAIN = "outputs/main_study_runs.csv"
CANONICAL_SUPPORT = "outputs/posthoc_support_runs.csv"
REQUIRED_INPUTS = {CANONICAL_MAIN, CANONICAL_SUPPORT}
DEFAULT_PROVENANCE_OUTPUT = "outputs/main_study_analysis_provenance.json"
VERIFIED_RUNNER = "scripts/run_verified_main_study_analysis.py"
EXECUTION_VERIFIER = "scripts/verify_main_study_execution.py"
INPUT_VALIDATOR = "scripts/validate_main_study_inputs.py"
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


@dataclass(frozen=True)
class InputValidatorBinding:
    path: Path
    sha256: str
    module: ModuleType


def _capture_manifest_pinned_regular_bytes(
    path: Path, *, expected_sha256: str, expected_size: int
) -> bytes:
    """Capture pinned research input bytes without a second unchecked path read.

    Recheck the source with the established no-symlink descriptor fingerprint,
    open the data descriptor nonblocking, and accept at most the manifest-declared
    number of bytes. Bind the opened inode, byte count, timestamps and digest,
    then repeat the safe path fingerprint. This is not an atomic filesystem
    snapshot; it blocks observable substitutions and unbounded middle reads.
    """
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError("invalid pinned research input size")
    before_sha, before_size, before_inode = fingerprint_regular_file_with_identity(path)
    if (before_sha, before_size) != (expected_sha256, expected_size):
        raise ValueError(f"pinned research input changed before capture: {path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"pinned research input changed during capture: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != before_inode
            or opened.st_size != expected_size
        ):
            raise ValueError(f"pinned research input changed during capture: {path}")

        chunks = []
        byte_count = 0
        digest = hashlib.sha256()
        while True:
            # The extra byte detects concurrent growth, including at size zero.
            chunk = os.read(
                descriptor, min(1024 * 1024, expected_size - byte_count + 1)
            )
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > expected_size:
                raise ValueError(f"pinned research input exceeded declared size: {path}")
            digest.update(chunk)
            chunks.append(chunk)

        closed = os.fstat(descriptor)
        def identity(metadata):
            return (
                metadata.st_dev, metadata.st_ino, metadata.st_size,
                metadata.st_mtime_ns, metadata.st_ctime_ns,
            )

        if (
            identity(opened) != identity(closed)
            or byte_count != expected_size
            or digest.hexdigest() != expected_sha256
        ):
            raise ValueError(f"pinned research input changed during capture: {path}")
    except OSError as exc:
        raise ValueError(f"pinned research input changed during capture: {path}") from exc
    finally:
        os.close(descriptor)

    after_sha, after_size, after_inode = fingerprint_regular_file_with_identity(path)
    if (after_sha, after_size, after_inode) != (
        expected_sha256, expected_size, before_inode
    ):
        raise ValueError(f"pinned research input changed after capture: {path}")
    return b"".join(chunks)


def _capture_verified_inputs(
    entries: list[dict], *, root: Path, snapshot_root: Path
) -> dict[str, Path]:
    """Capture exact manifest-bound bytes for isolated inferential analysis."""
    by_path = {entry["path"]: entry for entry in entries}
    captured = {}
    for relative in sorted(REQUIRED_INPUTS):
        expected = by_path[relative]
        try:
            content = _capture_manifest_pinned_regular_bytes(
                root / relative,
                expected_sha256=expected["sha256"],
                expected_size=expected["bytes"],
            )
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"research artifact changed while capturing verified analysis input: {relative}"
            ) from exc
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        captured[relative] = destination
    return captured


def _run_analysis_from_snapshots(
    snapshots: dict[str, Path],
    *,
    root: Path,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> int:
    """Run the frozen analyzer in a process isolated from live module globals."""
    output_json = Path(output_json) if output_json is not None else root / DEFAULT_JSON
    output_markdown = (
        Path(output_markdown)
        if output_markdown is not None
        else root / DEFAULT_MARKDOWN
    )
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                SNAPSHOT_ANALYSIS_DRIVER,
                str(snapshots[CANONICAL_MAIN]),
                str(snapshots[CANONICAL_SUPPORT]),
                str(output_json),
                str(output_markdown),
            ],
            cwd=root,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("unable to execute isolated frozen analysis") from exc
    return completed.returncode


def _open_output_directory(path: Path) -> int:
    """Open a stable, non-symlink directory for descriptor-relative publication."""
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError(f"canonical analysis parent must be a regular directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        directory_fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(
            f"canonical analysis parent must be a regular directory: {path}"
        ) from exc
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        os.close(directory_fd)
        raise ValueError(f"canonical analysis parent must be a regular directory: {path}")
    return directory_fd


MAX_VERIFIED_OUTPUT_BYTES = 16 * 1024 * 1024


def _output_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_output_at(directory_fd: int, name: str, *, label: str) -> bytes | None:
    """Capture a bounded, identity-stable output through its parent descriptor."""
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"published {label} must be a regular file")
    if metadata.st_size > MAX_VERIFIED_OUTPUT_BYTES:
        raise ValueError(f"published {label} exceeds the 16 MiB output safety limit")
    try:
        file_fd = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise ValueError(f"unable to read published {label}") from exc
    try:
        opened = os.fstat(file_fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _output_identity(opened) != _output_identity(metadata)
        ):
            raise ValueError(f"published {label} changed during capture")
        chunks = []
        remaining = metadata.st_size
        while True:
            chunk = os.read(file_fd, min(1024 * 1024, remaining + 1))
            if not chunk:
                break
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError(f"published {label} exceeded its original byte count")
            chunks.append(chunk)
        closed = os.fstat(file_fd)
        if remaining != 0 or _output_identity(closed) != _output_identity(opened):
            raise ValueError(f"published {label} changed during capture")
    except OSError as exc:
        raise ValueError(f"unable to read published {label}") from exc
    finally:
        os.close(file_fd)
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"published {label} changed during capture") from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or _output_identity(current) != _output_identity(metadata)
    ):
        raise ValueError(f"published {label} changed during capture")
    return b"".join(chunks)


def _require_directory_binding(path: Path, directory_fd: int) -> None:
    """Require the canonical path to still name the opened directory inode."""
    path = Path(path)
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"canonical analysis parent changed during publication: {path}") from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(f"canonical analysis parent changed during publication: {path}")


def _canonical_output_bytes(root: Path, relative: Path, *, label: str) -> bytes:
    parent = root / relative.parent
    directory_fd = _open_output_directory(parent)
    try:
        content = _read_output_at(directory_fd, relative.name, label=label)
        if content is None:
            raise ValueError(f"verified analysis output is missing: {root / relative}")
        _require_directory_binding(parent, directory_fd)
        return content
    finally:
        os.close(directory_fd)


def _create_output_at(directory_fd: int, name: str, content: bytes) -> None:
    file_fd = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        0o666,
        dir_fd=directory_fd,
    )
    with os.fdopen(file_fd, "wb") as handle:
        handle.write(content)


def _open_receipt_directory(path: Path, *, create: bool) -> int | None:
    """Open and bind the provenance-receipt parent without following its leaf."""
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError(
            f"provenance receipt parent must be a regular directory: {path}"
        )
    if not path.exists():
        if not create:
            return None
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise ValueError(
                f"provenance receipt parent must be a regular directory: {path}"
            )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        directory_fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(
            f"provenance receipt parent must be a regular directory: {path}"
        ) from exc
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        os.close(directory_fd)
        raise ValueError(
            f"provenance receipt parent must be a regular directory: {path}"
        )
    return directory_fd


def _require_receipt_directory_binding(path: Path, directory_fd: int) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(
            f"provenance receipt parent changed during publication: {path}"
        ) from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(
            f"provenance receipt parent changed during publication: {path}"
        )


def _invalidate_receipt(destination: Path) -> None:
    """Remove a stale receipt through a bound parent, never through a redirect."""
    destination = Path(destination)
    directory_fd = _open_receipt_directory(destination.parent, create=False)
    if directory_fd is None:
        return
    try:
        _require_receipt_directory_binding(destination.parent, directory_fd)
        try:
            metadata = os.stat(
                destination.name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(
                f"existing provenance receipt must be a regular file: {destination}"
            )
        os.unlink(destination.name, dir_fd=directory_fd)
        os.fsync(directory_fd)
        _require_receipt_directory_binding(destination.parent, directory_fd)
    finally:
        os.close(directory_fd)


def _publish_receipt(destination: Path, content: bytes) -> None:
    """Durably publish complete receipt bytes without replacing a concurrent writer."""
    destination = Path(destination)
    directory_fd = _open_receipt_directory(destination.parent, create=True)
    assert directory_fd is not None
    staging_name = None
    try:
        _require_receipt_directory_binding(destination.parent, directory_fd)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        for _ in range(100):
            candidate = f".{destination.name}.{secrets.token_hex(8)}.tmp"
            try:
                file_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
                    0o644,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            staging_name = candidate
            break
        else:
            raise ValueError(
                f"unable to allocate provenance receipt staging file: {destination}"
            )

        with os.fdopen(file_fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _require_receipt_directory_binding(destination.parent, directory_fd)
        try:
            os.link(
                staging_name,
                destination.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise ValueError(
                f"concurrent provenance receipt publication detected: {destination}"
            ) from exc
        except OSError as exc:
            raise ValueError(
                f"unable to publish provenance receipt atomically: {destination}"
            ) from exc
        os.fsync(directory_fd)
        os.unlink(staging_name, dir_fd=directory_fd)
        staging_name = None
        os.fsync(directory_fd)
        if (
            _read_output_at(
                directory_fd,
                destination.name,
                label="provenance receipt",
            )
            != content
        ):
            raise ValueError(
                f"published provenance receipt changed during publication: {destination}"
            )
        _require_receipt_directory_binding(destination.parent, directory_fd)
    finally:
        if staging_name is not None:
            try:
                os.unlink(staging_name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


def _read_candidate_output(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"verified candidate {label} is missing: {path}")
    directory_fd = _open_output_directory(path.parent)
    try:
        content = _read_output_at(directory_fd, path.name, label=label)
        if content is None:
            raise ValueError(f"verified candidate {label} is missing: {path}")
        _require_directory_binding(path.parent, directory_fd)
        return content
    finally:
        os.close(directory_fd)


def _candidate_output_digests(json_path: Path, markdown_path: Path) -> dict[str, str]:
    return {
        "canonical_inference": hashlib.sha256(
            _read_candidate_output(json_path, label="JSON")
        ).hexdigest(),
        "manuscript_rendering": hashlib.sha256(
            _read_candidate_output(markdown_path, label="Markdown")
        ).hexdigest(),
    }


def _publish_verified_outputs(
    candidate_json: Path,
    candidate_markdown: Path,
    *,
    root: Path,
    expected_sha256: dict[str, str] | None = None,
) -> None:
    """Publish only the exact candidate bytes that passed output verification."""
    candidate_json = Path(candidate_json)
    candidate_markdown = Path(candidate_markdown)
    expected_json = _read_candidate_output(candidate_json, label="JSON")
    expected_markdown = _read_candidate_output(candidate_markdown, label="Markdown")
    if expected_sha256 is not None and {
        "canonical_inference": hashlib.sha256(expected_json).hexdigest(),
        "manuscript_rendering": hashlib.sha256(expected_markdown).hexdigest(),
    } != expected_sha256:
        raise ValueError("verified analysis candidate changed after output verification")

    json_parent = root / DEFAULT_JSON.parent
    markdown_parent = root / DEFAULT_MARKDOWN.parent
    json_fd = _open_output_directory(json_parent)
    try:
        markdown_fd = _open_output_directory(markdown_parent)
    except BaseException:
        os.close(json_fd)
        raise
    try:
        published_json = _read_output_at(
            json_fd, DEFAULT_JSON.name, label="canonical inference JSON"
        )
        published_markdown = _read_output_at(
            markdown_fd,
            DEFAULT_MARKDOWN.name,
            label="manuscript inference Markdown",
        )
        if (published_json is None) != (published_markdown is None):
            raise ValueError(
                "published canonical analysis output set is incomplete; "
                "refusing to repair or replace it automatically"
            )
        if published_json is not None:
            if (
                published_json != expected_json
                or published_markdown != expected_markdown
            ):
                raise ValueError(
                    "verified analysis differs from published canonical outputs; "
                    "preserving the published result files"
                )
            _require_directory_binding(json_parent, json_fd)
            _require_directory_binding(markdown_parent, markdown_fd)
            return

        try:
            _create_output_at(json_fd, DEFAULT_JSON.name, expected_json)
            _create_output_at(
                markdown_fd, DEFAULT_MARKDOWN.name, expected_markdown
            )
        except OSError as exc:
            raise ValueError(
                "concurrent canonical analysis publication detected; "
                "partial state is preserved for explicit inspection"
            ) from exc

        if (
            _read_output_at(
                json_fd, DEFAULT_JSON.name, label="canonical inference JSON"
            )
            != expected_json
            or _read_output_at(
                markdown_fd,
                DEFAULT_MARKDOWN.name,
                label="manuscript inference Markdown",
            )
            != expected_markdown
        ):
            raise ValueError("published canonical analysis bytes changed during publication")
        _require_directory_binding(json_parent, json_fd)
        _require_directory_binding(markdown_parent, markdown_fd)
    finally:
        os.close(markdown_fd)
        os.close(json_fd)


def _capture_input_validator_binding(*, root: Path) -> InputValidatorBinding:
    """Load the validator from the exact stable source bytes being recorded."""
    path = Path(os.path.abspath(Path(root) / INPUT_VALIDATOR))
    try:
        before_sha256, before_size = fingerprint_regular_file(path)
        source = _capture_manifest_pinned_regular_bytes(
            path, expected_sha256=before_sha256, expected_size=before_size
        )
        after_sha256, after_size = fingerprint_regular_file(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"input validator must be a stable regular file: {path}") from exc
    captured_sha256 = hashlib.sha256(source).hexdigest()
    if (
        before_sha256 != captured_sha256
        or after_sha256 != captured_sha256
        or before_size != len(source)
        or after_size != len(source)
    ):
        raise ValueError(f"input validator changed while it was captured: {path}")

    module = ModuleType("_vera_captured_main_study_input_validator")
    module.__file__ = str(path)
    module.__package__ = "scripts"
    try:
        code = compile(source, str(path), "exec")
        exec(code, module.__dict__)
    except Exception as exc:
        raise ValueError(f"unable to load captured input validator: {path}") from exc
    return InputValidatorBinding(path=path, sha256=captured_sha256, module=module)


def _require_input_validator_unchanged(binding: InputValidatorBinding) -> None:
    """Fail if the captured validator source changed during this run."""
    try:
        observed_sha256, _ = fingerprint_regular_file(binding.path)
    except ValueError as exc:
        raise ValueError(
            f"input validator changed during verified analysis: {binding.path}"
        ) from exc
    if observed_sha256 != binding.sha256:
        raise ValueError(
            f"input validator changed during verified analysis: {binding.path}"
        )


def _bind_verified_execution(
    receipt: dict,
    *,
    root: Path,
    input_validator_sha256: str,
) -> dict:
    """Bind the orchestration layer and its independent verifier for future runs."""
    bound = dict(receipt)
    bound["verified_execution"] = {
        "runner": {"path": VERIFIED_RUNNER, "sha256": _sha256(root / VERIFIED_RUNNER)},
        "execution_verifier": {
            "path": EXECUTION_VERIFIER,
            "sha256": _sha256(root / EXECUTION_VERIFIER),
        },
        "input_validator": {
            "path": INPUT_VALIDATOR,
            "sha256": input_validator_sha256,
        },
    }
    return bound


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"verified analysis output is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind_verified_outputs(
    receipt: dict,
    *,
    root: Path,
    expected_sha256: dict[str, str] | None = None,
) -> dict:
    """Return a receipt that cryptographically binds the verified result files.

    Output verification establishes semantic consistency between canonical JSON
    and manuscript Markdown. Hashing both exact byte streams afterwards makes
    the success receipt an attestation of the specific result artifacts that
    passed that check, rather than only an attestation of inputs/code/plan.
    """
    canonical_bytes = _canonical_output_bytes(
        root,
        DEFAULT_JSON,
        label="canonical inference JSON",
    )
    manuscript_bytes = _canonical_output_bytes(
        root,
        DEFAULT_MARKDOWN,
        label="manuscript inference Markdown",
    )
    observed = {
        "canonical_inference": hashlib.sha256(canonical_bytes).hexdigest(),
        "manuscript_rendering": hashlib.sha256(manuscript_bytes).hexdigest(),
    }
    if expected_sha256 is not None and observed != expected_sha256:
        raise ValueError(
            "published canonical outputs changed after candidate verification; "
            "refusing to issue a success receipt"
        )

    bound = dict(receipt)
    bound["verified_outputs"] = {
        "canonical_inference": {
            "path": DEFAULT_JSON.as_posix(),
            "sha256": observed["canonical_inference"],
        },
        "manuscript_rendering": {
            "path": DEFAULT_MARKDOWN.as_posix(),
            "sha256": observed["manuscript_rendering"],
        },
    }
    return bound


def verify_and_run(
    manifest: dict,
    *,
    root: Path = REPO_ROOT,
    analyze: Callable[[], int] | None = None,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
    input_validator: ModuleType | None = None,
    require_canonical_matrix: bool = False,
) -> int:
    """Verify provenance/integrity before invoking the frozen analysis.

    The manifest must describe exactly the two canonical CSV inputs. Requiring
    an exact set prevents a valid hash for unrelated files from being mistaken
    for provenance of the data actually consumed by the analysis. Re-hashing the
    captured bytes closes the gap between live-file verification and analysis.
    The production receipt path sets ``require_canonical_matrix`` to enforce
    the frozen 4x10 cells, assigned retrieval budgets, and cross-file evaluator
    mirrors. False is retained for small dependency-injected test fixtures.
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
        if input_validator is None:
            from scripts import validate_main_study_inputs as input_validator

        main_rows = input_validator.read_csv_rows(snapshots[CANONICAL_MAIN])
        support_rows = input_validator.read_csv_rows(snapshots[CANONICAL_SUPPORT])
        input_validator.validate_rows(
            main_rows,
            support_rows,
            require_canonical_matrix=require_canonical_matrix,
        )
        if analyze is not None:
            return analyze()
        return _run_analysis_from_snapshots(
            snapshots,
            root=root,
            output_json=output_json,
            output_markdown=output_markdown,
        )


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

    _invalidate_receipt(destination)

    production_receipt = output_verifier is verify_outputs and receipt_builder is build_receipt
    validator_binding = (
        _capture_input_validator_binding(root=root) if production_receipt else None
    )
    receipt = receipt_builder(manifest, root=root)
    expected_output_sha256 = None
    validator_options = (
        {
            "input_validator": validator_binding.module,
            "require_canonical_matrix": True,
        }
        if validator_binding is not None
        else {}
    )
    if analyze is None:
        with tempfile.TemporaryDirectory(
            prefix="vera-main-analysis-candidate-"
        ) as candidate_name:
            candidate_root = Path(candidate_name)
            candidate_json = candidate_root / DEFAULT_JSON
            candidate_markdown = candidate_root / DEFAULT_MARKDOWN
            result = verify_and_run(
                manifest,
                root=root,
                output_json=candidate_json,
                output_markdown=candidate_markdown,
                **validator_options,
            )
            if result != 0:
                return result
            if validator_binding is not None:
                _require_input_validator_unchanged(validator_binding)
            # Bind candidate bytes before semantic verification, and refuse
            # publication if those bytes change while/after it runs.
            candidate_digests = _candidate_output_digests(
                candidate_json, candidate_markdown
            )
            output_verifier(
                root=root,
                json_path=candidate_json,
                markdown_path=candidate_markdown,
            )
            if _candidate_output_digests(
                candidate_json, candidate_markdown
            ) != candidate_digests:
                raise ValueError(
                    "verified analysis candidate changed during output verification"
                )
            _publish_verified_outputs(
                candidate_json,
                candidate_markdown,
                root=root,
                expected_sha256=candidate_digests,
            )
            expected_output_sha256 = candidate_digests
    else:
        result = verify_and_run(
            manifest,
            root=root,
            analyze=analyze,
            **validator_options,
        )
        if result != 0:
            return result
        if validator_binding is not None:
            _require_input_validator_unchanged(validator_binding)
        output_verifier(root=root)

    # Re-read the published pair after the candidate-to-canonical boundary.
    # This is the exact revision that the success receipt will bind.
    if output_verifier is verify_outputs:
        output_verifier(root=root)
    if output_verifier is verify_outputs:
        receipt = _bind_verified_outputs(
            receipt,
            root=root,
            expected_sha256=expected_output_sha256,
        )
    if production_receipt:
        assert validator_binding is not None
        _require_input_validator_unchanged(validator_binding)
        receipt = _bind_verified_execution(
            receipt,
            root=root,
            input_validator_sha256=validator_binding.sha256,
        )
        from scripts.verify_main_study_execution import verify_execution_receipt

        verify_execution_receipt(receipt, root=root)

    receipt_bytes = (
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _publish_receipt(destination, receipt_bytes)
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
        payload = parse_manifest_json(manifest_path.read_text(encoding="utf-8"))
        result = verify_run_and_record(payload, output=args.provenance_output)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"VERIFIED MAIN-STUDY ANALYSIS: FAIL: {exc}") from exc
    if result == 0:
        print("VERIFIED MAIN-STUDY ANALYSIS: PASS (outputs verified and hash-bound; provenance receipt recorded)")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
