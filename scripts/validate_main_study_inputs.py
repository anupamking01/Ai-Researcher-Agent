"""Fail-closed preflight validation for canonical main-study CSV inputs.

Run this before inferential analysis to detect malformed scientific measurements,
mismatched treatment/evaluator identities, or drift from the preregistered study
matrix without modifying or repairing preserved experiment artifacts.
"""
from __future__ import annotations

import csv
from pathlib import Path

from scripts.validate_numeric_inputs import require_nonnegative, require_nonnegative_integer

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_CSV = REPO_ROOT / "outputs" / "main_study_runs.csv"
SUPPORT_CSV = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"

COUNT_FIELDS = ("claims_checked", "supported", "partially_supported", "unsupported", "contradicted")
INTEGER_MEASUREMENT_FIELDS = ("successful_sources", "total_tokens", "model_calls", "report_words")
CONTINUOUS_MEASUREMENT_FIELDS = ("treatment_cost_usd", "latency_seconds")
IDENTITY_FIELDS = ("variant_id", "task_id")
EXPECTED_VARIANTS = frozenset({"D3", "D6", "P6", "P6V"})
EXPECTED_TASKS = frozenset(f"main-{index:02d}" for index in range(1, 11))
EXPECTED_CELLS = frozenset((variant, task) for variant in EXPECTED_VARIANTS for task in EXPECTED_TASKS)


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"missing required CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _identity_keys(rows: list[dict[str, str]], *, label: str) -> set[tuple[str, str]] | None:
    """Return unique (variant, task) identities when the CSV exposes them.

    Small unit-level fixtures may intentionally omit identity columns. Canonical
    study CSVs contain both columns; if either is present, both become mandatory
    and every row must identify exactly one treatment cell.
    """
    if not rows:
        raise ValueError(f"{label} input contains no rows")
    has_identity = any(any(field in row for field in IDENTITY_FIELDS) for row in rows)
    if not has_identity:
        return None

    keys: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=2):
        variant = str(row.get("variant_id") or "").strip()
        task = str(row.get("task_id") or "").strip()
        if not variant or not task:
            raise ValueError(f"{label} row {index} has incomplete variant/task identity")
        key = (variant, task)
        if key in keys:
            raise ValueError(f"duplicate {label} treatment cell: {variant}/{task}")
        keys.add(key)
    return keys


def _validate_canonical_matrix(keys: set[tuple[str, str]], *, label: str) -> None:
    """Require exactly the preregistered 4 x 10 confirmatory study matrix."""
    if keys != EXPECTED_CELLS:
        missing = sorted(EXPECTED_CELLS - keys)
        unexpected = sorted(keys - EXPECTED_CELLS)
        raise ValueError(
            f"{label} does not match frozen 4x10 main-study matrix: "
            f"missing={missing}, unexpected={unexpected}"
        )


def validate_rows(
    main_rows: list[dict[str, str]],
    support_rows: list[dict[str, str]],
    *,
    require_canonical_matrix: bool = False,
) -> None:
    """Validate scientific domains, identities, and evaluator conservation.

    ``require_canonical_matrix`` is enabled by the command-line preflight used for
    the real study. Tests and small reusable fixtures can leave it disabled while
    still exercising row-level invariants.
    """
    main_keys = _identity_keys(main_rows, label="treatment")
    support_keys = _identity_keys(support_rows, label="evaluator")
    if (main_keys is None) != (support_keys is None):
        raise ValueError("treatment/evaluator identity columns must be present in both inputs")
    if main_keys is not None and support_keys is not None:
        if main_keys != support_keys:
            missing_eval = sorted(main_keys - support_keys)
            orphan_eval = sorted(support_keys - main_keys)
            raise ValueError(
                "treatment/evaluator cell mismatch: "
                f"missing_evaluator={missing_eval}, orphan_evaluator={orphan_eval}"
            )
        if require_canonical_matrix:
            _validate_canonical_matrix(main_keys, label="treatment/evaluator inputs")
    elif require_canonical_matrix:
        raise ValueError("canonical main-study inputs must expose variant_id and task_id")

    for index, row in enumerate(main_rows, start=2):
        completed = row.get("completed")
        if completed is not None and str(completed).strip().lower() not in {"true", "1", "yes"}:
            raise ValueError(f"main row {index} is not a completed treatment")
        for field in INTEGER_MEASUREMENT_FIELDS:
            require_nonnegative_integer(row.get(field), f"main row {index} {field}")
        for field in CONTINUOUS_MEASUREMENT_FIELDS:
            require_nonnegative(row.get(field), f"main row {index} {field}")

    for index, row in enumerate(support_rows, start=2):
        counts = {
            field: require_nonnegative_integer(row.get(field), f"support row {index} {field}")
            for field in COUNT_FIELDS
        }
        if counts["claims_checked"] <= 0:
            raise ValueError(f"support row {index} claims_checked must be positive")
        classified = sum(counts[field] for field in COUNT_FIELDS if field != "claims_checked")
        if classified != counts["claims_checked"]:
            raise ValueError(
                f"support row {index} count mismatch: classified={classified}, "
                f"claims_checked={counts['claims_checked']}"
            )


def main() -> int:
    validate_rows(_rows(MAIN_CSV), _rows(SUPPORT_CSV), require_canonical_matrix=True)
    print("main-study identity/numeric/matrix preflight: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
