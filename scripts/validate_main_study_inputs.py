"""Fail-closed preflight validation for canonical main-study CSV inputs.

Run this before inferential analysis to detect malformed scientific measurements
without modifying or repairing the preserved experiment artifacts.
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


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"missing required CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_rows(main_rows: list[dict[str, str]], support_rows: list[dict[str, str]]) -> None:
    """Validate numeric domains and evaluator count conservation."""
    for index, row in enumerate(main_rows, start=2):
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
    print("main-study numeric preflight: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
