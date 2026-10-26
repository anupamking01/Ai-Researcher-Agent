"""Validated local diagnostic main-study inference without modifying the frozen analyzer.

This optional CLI gates the *exact parsed rows* used by the historical
analyzer behind the repository's canonical CSV contract. It is not a
replacement for the externally pinned, manifest-verified analysis runner.
"""
from __future__ import annotations

import argparse
import os
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


def main(*, output_dir: Path) -> int:
    """Run validated inference into a new, explicitly selected diagnostic folder.

    The frozen analyzer's default canonical paths are never written by this
    entrypoint. Results are first generated in scratch space; validation or
    rendering failures leave no published diagnostic directory. Publication
    requires an absent destination and creates files without overwriting them.
    This is not a manifest-verified canonical analysis or an atomic two-file
    filesystem transaction.
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

            # mkdir is exclusive even if a second invocation races this one.
            # The output names are separate from the canonical result names.
            destination.mkdir(mode=0o700)
            published = []
            try:
                for name in (DIAGNOSTIC_JSON, DIAGNOSTIC_MD):
                    os.link(staging / name, destination / name)
                    published.append(name)
            except BaseException:
                for name in published:
                    (destination / name).unlink()
                try:
                    destination.rmdir()
                except OSError:
                    pass
                raise
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
