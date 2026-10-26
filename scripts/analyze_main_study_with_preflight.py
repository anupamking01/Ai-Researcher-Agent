"""Validated local diagnostic main-study inference without modifying the frozen analyzer.

This optional CLI gates the *exact parsed rows* used by the historical
analyzer behind the repository's canonical CSV contract. It is not a
replacement for the externally pinned, manifest-verified analysis runner.
"""
from __future__ import annotations

import argparse
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

    treatment_rows = read_csv_rows(main_path)
    evaluator_rows = read_csv_rows(support_path)
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
        yield
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


def _publish_diagnostic_pair(staging: Path, destination: Path) -> None:
    """Bind both diagnostic links to opened directories; fail on namespace drift.

    POSIX-only, not an atomic two-file transaction or immutable snapshot.
    """
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
            os.mkdir(destination.name, mode=0o700, dir_fd=parent_fd)
            output_fd = os.open(destination.name, flags, dir_fd=parent_fd)
            try:
                output_identity = os.fstat(output_fd)
                linked = []
                try:
                    for name in (DIAGNOSTIC_JSON, DIAGNOSTIC_MD):
                        source = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
                        if not stat.S_ISREG(source.st_mode):
                            raise ValueError("diagnostic staged output must be a regular file")
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

    with _bound_validated_inputs():
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

            _publish_diagnostic_pair(staging, destination)
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
