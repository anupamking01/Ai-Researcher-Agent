"""Fail-closed preflight validation for canonical main-study CSV inputs.

Run this before inferential analysis to detect malformed scientific measurements
or mismatched treatment/evaluator identities without modifying or repairing the
preserved experiment artifacts.
"""
from __future__ import annotations

import csv
from pathlib import Path

from scripts.validate_numeric_inputs import require_nonnegative, require_nonnegative_integer

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_CSV = REPO_ROOT / "outputs" / "main_study_runs.csv"
SUPPORT_CSV = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"

COUNT_FIELDS = ("claims_checked", "supported", "partially_supported", "unsupported", "contradicted")
MEASUREMENT_FIELDS = (
    "successful_sources",
    "total_tokens",
    "treatment_cost_usd",
    "latency_seconds",
    "model_calls",
    "report_words",
)
IDENTITY_FIELDS = ("variant_id", "task_id")


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


def validate_rows(main_rows: list[dict[str, str]], support_rows: list[dict[str, str]]) -> None:
    """Validate scientific domains, identities, and evaluator conservation."""
    main_keys = _identity_keys(main_rows, label="treatment")
    support_keys = _identity_keys(support_rows, label="evaluator")
    if (main_keys is None) != (support_keys is None):
        raise ValueError("treatment/evaluator identity columns must be present in both inputs")
    if main_keys is not None and support_keys is not None and main_keys != support_keys:
        missing_eval = sorted(main_keys - support_keys)
        orphan_eval = sorted(support_keys - main_keys)
        raise ValueError(
            "treatment/evaluator cell mismatch: "
            f"missing_evaluator={missing_eval}, orphan_evaluator={orphan_eval}"
        )

    for index, row in enumerate(main_rows, start=2):
        completed = row.get("completed")
        if completed is not None and str(completed).strip().lower() not in {"true", "1", "yes"}:
            raise ValueError(f"main row {index} is not a completed treatment")
        for field in MEASUREMENT_FIELDS:
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
    validate_rows(_rows(MAIN_CSV), _rows(SUPPORT_CSV))
    print("main-study identity/numeric preflight: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
