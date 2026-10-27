"""Validated local diagnostic main-study inference without modifying the frozen analyzer.

This optional CLI gates the *exact parsed rows* used by the historical
analyzer behind the repository's canonical CSV contract. It is not a
replacement for the externally pinned, manifest-verified analysis runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

# Preserve both direct-file and package-module invocation.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import analyze_main_study as frozen
from scripts.validate_main_study_inputs import read_csv_rows, validate_rows


MAX_DIAGNOSTIC_INPUT_BYTES = 8 * 1024 * 1024
DIAGNOSTIC_MAIN_INPUT = "main_study_diagnostic_treatment_input.csv"
DIAGNOSTIC_SUPPORT_INPUT = "main_study_diagnostic_evaluator_input.csv"
DIAGNOSTIC_MANIFEST = "main_study_diagnostic_provenance.json"


def _capture_csv_input(path: Path) -> bytes:
    """Capture one bounded regular-file generation before scientific validation."""
    path = Path(path)
    try:
        original = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(original.st_mode):
            raise ValueError(f"diagnostic input must be a regular file: {path}")
        if not 0 < original.st_size <= MAX_DIAGNOSTIC_INPUT_BYTES:
            raise ValueError(f"diagnostic input exceeds size limit or is empty: {path}")
        fd = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError as exc:
        raise ValueError(f"diagnostic input cannot be opened safely: {path}") from exc

    def identity(entry):
        return (
            entry.st_dev, entry.st_ino, entry.st_mode, entry.st_size,
            entry.st_mtime_ns, entry.st_ctime_ns,
        )

    try:
        before = os.fstat(fd)
        if identity(original) != identity(before):
            raise ValueError(f"diagnostic input changed before capture: {path}")
        parts = []
        total = 0
        while True:
            block = os.read(fd, min(1024 * 1024, MAX_DIAGNOSTIC_INPUT_BYTES + 1 - total))
            if not block:
                break
            total += len(block)
            if total > MAX_DIAGNOSTIC_INPUT_BYTES:
                raise ValueError(f"diagnostic input exceeds size limit: {path}")
            parts.append(block)
        after = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        if (
            total != before.st_size
            or identity(original) != identity(after)
            or identity(after) != identity(named)
        ):
            raise ValueError(f"diagnostic input changed during capture: {path}")
        return b"".join(parts)
    finally:
        os.close(fd)


@contextmanager
def _bound_validated_inputs():
    """Serve validated in-memory rows to the unchanged historical analyzer.

    Validate before running any inference or output publication. This prevents
    a separate, unchecked second read from becoming the actual measurement
    input. The temporary module hook is private to this synchronous CLI and
    must not be used concurrently in a shared Python process.
    """
    main_path = Path(frozen.MAIN_CSV)
    support_path = Path(frozen.SUPPORT_CSV)
    if main_path == support_path:
        raise ValueError("treatment and evaluator inputs must be separate CSV paths")

    # Parse copies of the precise bytes consumed by inference. The original
    # source paths are never reread by the byte-pinned historical analyzer.
    retained = {
        DIAGNOSTIC_MAIN_INPUT: _capture_csv_input(main_path),
        DIAGNOSTIC_SUPPORT_INPUT: _capture_csv_input(support_path),
    }
    with tempfile.TemporaryDirectory(prefix=".vera-diagnostic-input-snapshot-") as root:
        treatment_copy = Path(root) / DIAGNOSTIC_MAIN_INPUT
        evaluator_copy = Path(root) / DIAGNOSTIC_SUPPORT_INPUT
        treatment_copy.write_bytes(retained[DIAGNOSTIC_MAIN_INPUT])
        evaluator_copy.write_bytes(retained[DIAGNOSTIC_SUPPORT_INPUT])
        treatment_rows = read_csv_rows(treatment_copy)
        evaluator_rows = read_csv_rows(evaluator_copy)
        validate_rows(treatment_rows, evaluator_rows, require_canonical_matrix=True)

    original_reader = frozen._read_csv

    def validated_reader(path: Path):
        path = Path(path)
        if path == main_path:
            return [dict(row) for row in treatment_rows]
        if path == support_path:
            return [dict(row) for row in evaluator_rows]
        raise ValueError(f"unexpected analysis input path: {path}")

    frozen._read_csv = validated_reader
    try:
        yield retained
    finally:
        frozen._read_csv = original_reader


def build_dataset():
    """Diagnostic helper; does not emit artifacts or prove input provenance."""
    with _bound_validated_inputs():
        return frozen._build_dataset()


DIAGNOSTIC_JSON = "main_study_diagnostic_inference.json"
DIAGNOSTIC_MD = "main_study_diagnostic_inference.md"


def _same_directory(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(first.st_mode)
        and stat.S_ISDIR(second.st_mode)
        and (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)
    )



DIAGNOSTIC_MAX_FILE_BYTES = 16 * 1024 * 1024


def _diagnostic_file_fingerprint(directory_fd: int, name: str) -> tuple[int, int, int, int, str]:
    """Read a bounded regular file relative to its retained directory descriptor.

    The within-read stat comparison detects observable concurrent modification
    and replacement. The returned digest deliberately excludes ctime and link
    count: publishing an additional hard link legitimately changes both.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        file_fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ValueError(f"diagnostic output cannot be opened safely: {name}") from exc
    try:
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"diagnostic output is not a regular file: {name}")
        if before.st_size > DIAGNOSTIC_MAX_FILE_BYTES:
            raise ValueError(f"diagnostic output exceeds size limit: {name}")

        digest = hashlib.sha256()
        size = 0
        while True:
            block = os.read(file_fd, 1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > DIAGNOSTIC_MAX_FILE_BYTES:
                raise ValueError(f"diagnostic output exceeds size limit: {name}")
            digest.update(block)

        after = os.fstat(file_fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)

        def observed(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
            return (
                st.st_dev, st.st_ino, st.st_mode, st.st_size,
                st.st_mtime_ns, st.st_ctime_ns,
            )

        if size != after.st_size or observed(before) != observed(after) or observed(after) != observed(named):
            raise ValueError(f"diagnostic output changed while fingerprinting: {name}")
        return (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, digest.hexdigest())
    finally:
        os.close(file_fd)


def _byte_fingerprint(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _stage_diagnostic_evidence(staging: Path, retained: dict[str, bytes]) -> None:
    """Retain exact input bytes and output/source hashes for local diagnostics."""
    required = {DIAGNOSTIC_MAIN_INPUT, DIAGNOSTIC_SUPPORT_INPUT}
    if set(retained) != required:
        raise ValueError("diagnostic captured input set mismatch")
    artifacts = {}
    for name in (DIAGNOSTIC_MAIN_INPUT, DIAGNOSTIC_SUPPORT_INPUT):
        raw = retained[name]
        if not 0 < len(raw) <= MAX_DIAGNOSTIC_INPUT_BYTES:
            raise ValueError("diagnostic input snapshot exceeds size limit")
        (staging / name).write_bytes(raw)
        artifacts[name] = _byte_fingerprint(raw)
    for name in (DIAGNOSTIC_JSON, DIAGNOSTIC_MD):
        artifacts[name] = _byte_fingerprint((staging / name).read_bytes())

    from scripts import validate_main_study_inputs as preflight

    receipt = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "scope": "local_diagnostic_not_canonical",
        "sources": {
            "scripts/analyze_main_study.py":
                _byte_fingerprint(Path(frozen.__file__).read_bytes()),
            "scripts/analyze_main_study_with_preflight.py":
                _byte_fingerprint(Path(__file__).read_bytes()),
            "scripts/validate_main_study_inputs.py":
                _byte_fingerprint(Path(preflight.__file__).read_bytes()),
            "scripts/validate_numeric_inputs.py":
                _byte_fingerprint(Path(preflight.require_nonnegative.__code__.co_filename).read_bytes()),
        },
        "analysis_config": {
            "bootstrap_draws": frozen.BOOTSTRAP_DRAWS,
            "bootstrap_seed": frozen.BOOTSTRAP_SEED,
            "expected_tasks": frozen.EXPECTED_TASKS,
        },
        "artifacts": artifacts,
    }
    (staging / DIAGNOSTIC_MANIFEST).write_text(
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _publish_diagnostic_pair(
    staging: Path, destination: Path, *, extra_files: tuple[str, ...] = ()
) -> None:
    """Bind both diagnostic links to opened directories; fail on namespace drift.

    POSIX-only, not an atomic two-file transaction or immutable snapshot.
    """
    names = (DIAGNOSTIC_JSON, DIAGNOSTIC_MD, *extra_files)
    if len(set(names)) != len(names):
        raise ValueError("duplicate diagnostic publication filename")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        parent_fd = os.open(destination.parent, flags)
    except OSError as exc:
        raise ValueError("diagnostic parent must be a non-symlink directory") from exc
    try:
        parent_identity = os.fstat(parent_fd)
        source_fd = os.open(staging, flags)
        try:
            source_identity = os.fstat(source_fd)
            # Pin exact stage-file content and inode before creating any destination.
            fingerprints = {
                name: _diagnostic_file_fingerprint(source_fd, name)
                for name in names
            }
            os.mkdir(destination.name, mode=0o700, dir_fd=parent_fd)
            output_fd = os.open(destination.name, flags, dir_fd=parent_fd)
            try:
                output_identity = os.fstat(output_fd)
                linked = []
                try:
                    for name in names:
                        source = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
                        if not stat.S_ISREG(source.st_mode):
                            raise ValueError("diagnostic staged output must be a regular file")
                        if (source.st_dev, source.st_ino) != fingerprints[name][:2]:
                            raise ValueError("diagnostic staged-file identity changed during publication")
                        os.link(
                            name, name, src_dir_fd=source_fd,
                            dst_dir_fd=output_fd, follow_symlinks=False,
                        )
                        linked.append(name)
                        published = os.stat(
                            name, dir_fd=output_fd, follow_symlinks=False
                        )
                        if (source.st_dev, source.st_ino) != (
                            published.st_dev, published.st_ino
                        ):
                            raise ValueError("diagnostic staged-file identity changed")
                    os.fsync(output_fd)
                    os.fsync(parent_fd)
                    # A hard-link points to the same mutable inode: descriptor
                    # identity alone cannot detect altered diagnostic numbers.
                    for name, expected in fingerprints.items():
                        if (
                            _diagnostic_file_fingerprint(source_fd, name) != expected
                            or _diagnostic_file_fingerprint(output_fd, name) != expected
                        ):
                            raise ValueError(
                                "diagnostic output content or identity changed during publication"
                            )
                    try:
                        parent_now = os.stat(destination.parent, follow_symlinks=False)
                        source_now = os.stat(staging, follow_symlinks=False)
                        output_now = os.stat(
                            destination.name, dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                        absolute_now = os.stat(destination, follow_symlinks=False)
                    except OSError as exc:
                        raise ValueError(
                            "diagnostic directory namespace changed during publication"
                        ) from exc
                    if not (
                        _same_directory(parent_identity, parent_now)
                        and _same_directory(source_identity, source_now)
                        and _same_directory(output_identity, output_now)
                        and _same_directory(output_identity, absolute_now)
                    ):
                        raise ValueError(
                            "diagnostic directory namespace changed during publication"
                        )
                except BaseException:
                    # Clean only the descriptor-bound original, never an
                    # unrelated replacement appearing at the output path.
                    for name in linked:
                        try:
                            os.unlink(name, dir_fd=output_fd)
                        except FileNotFoundError:
                            pass
                    try:
                        named = os.stat(
                            destination.name, dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                        if _same_directory(output_identity, named):
                            os.rmdir(destination.name, dir_fd=parent_fd)
                    except OSError:
                        pass
                    raise
            finally:
                os.close(output_fd)
        finally:
            os.close(source_fd)
    finally:
        os.close(parent_fd)


def main(*, output_dir: Path) -> int:
    """Run validated inference into a new, explicitly selected diagnostic folder.

    The frozen analyzer's default canonical paths are never written by this
    entrypoint. Results are first generated in scratch space; validation or
    rendering failures leave no published diagnostic directory. Publication
    requires an absent destination and creates files without overwriting them.
    This is not a manifest-verified canonical analysis or an atomic two-file
    filesystem transaction, even with descriptor-bound publication.
    """
    destination = Path(output_dir)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"diagnostic output directory already exists: {destination}")
    if not destination.parent.is_dir():
        raise ValueError(f"create the diagnostic parent directory first: {destination.parent}")

    with _bound_validated_inputs() as retained_inputs:
        with tempfile.TemporaryDirectory(
            prefix=".vera-main-diagnostic-stage-", dir=destination.parent
        ) as scratch:
            staging = Path(scratch)
            original_json, original_md = frozen.OUT_JSON, frozen.OUT_MD
            frozen.OUT_JSON = staging / DIAGNOSTIC_JSON
            frozen.OUT_MD = staging / DIAGNOSTIC_MD
            try:
                status = frozen.main()
            finally:
                frozen.OUT_JSON, frozen.OUT_MD = original_json, original_md
            if status != 0:
                return status

            _stage_diagnostic_evidence(staging, retained_inputs)
            _publish_diagnostic_pair(
                staging, destination,
                extra_files=(
                    DIAGNOSTIC_MAIN_INPUT, DIAGNOSTIC_SUPPORT_INPUT,
                    DIAGNOSTIC_MANIFEST,
                ),
            )
            return status


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Validate local 40-cell inputs and publish isolated diagnostic inference"
    )
    parser.add_argument(
        "--output-dir", required=True, type=Path,
        help="new, previously nonexistent diagnostic directory (parent must exist)",
    )
    arguments = parser.parse_args()
    return main(output_dir=arguments.output_dir)


if __name__ == "__main__":
    raise SystemExit(_cli())
