"""Validated local diagnostic main-study inference without modifying the frozen analyzer.

This optional CLI gates the *exact parsed rows* used by the historical
analyzer behind the repository's canonical CSV contract. It is not a
replacement for the externally pinned, manifest-verified analysis runner.
"""
from __future__ import annotations

import sys
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


def main() -> int:
    """Run the unchanged frozen estimator on already validated rows."""
    with _bound_validated_inputs():
        return frozen.main()


if __name__ == "__main__":
    raise SystemExit(main())
