"""Offline internal-numeric-consistency audit for the frozen VERA main-study CSVs.

An independent preflight, not an alternative estimator or a source-custody
attestation. Never imports, invokes, or modifies the SHA-pinned analyzer.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = "outputs/main_study_runs.csv"
SUPPORT_PATH = "outputs/posthoc_support_runs.csv"
VARIANTS = ("D3", "D6", "P6", "P6V")
TASKS = tuple(f"main-{index:02d}" for index in range(1, 11))
BUDGETS = {"D3": 3, "D6": 6, "P6": 6, "P6V": 6}
CLAIM_CAP = 12
TOL = Decimal("0.000000000001")
MAX_CSV_BYTES = 2 * 1024 * 1024


class NumericInputError(ValueError):
    """Frozen analysis CSVs are structurally or numerically inconsistent."""


def _number(row: dict, key: str, label: str) -> Decimal:
    raw = row.get(key)
    if raw is None or str(raw).strip() == "":
        raise NumericInputError(f"{label}: missing numeric {key}")
    try:
        number = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise NumericInputError(f"{label}: invalid numeric {key}") from exc
    if not number.is_finite() or number < 0:
        raise NumericInputError(f"{label}: nonfinite or negative {key}")
    return number


def _count(row: dict, key: str, label: str) -> int:
    value = _number(row, key, label)
    if value != value.to_integral_value():
        raise NumericInputError(f"{label}: fractional count {key}")
    return int(value)


def _rate(row: dict, key: str, reference: Decimal, label: str) -> None:
    recorded = _number(row, key, label)
    if recorded > 1 or abs(recorded - reference) > TOL:
        raise NumericInputError(f"{label}: inconsistent {key}")


def _matrix(rows: list[dict], label: str, variants: tuple[str, ...], tasks: tuple[str, ...]) -> dict:
    required = {(variant, task) for variant in variants for task in tasks}
    seen: dict[tuple[str, str], dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise NumericInputError(f"{label}: row must be an object")
        key = (row.get("variant_id"), row.get("task_id"))
        if key in seen:
            raise NumericInputError(f"{label}: duplicate treatment/task cell {key}")
        seen[key] = row
    if set(seen) != required:
        raise NumericInputError(
            f"{label}: exact treatment/task matrix required; "
            f"missing={len(required - set(seen))} extra={len(set(seen) - required)}"
        )
    return seen


def audit_rows(
    main_rows: list[dict], support_rows: list[dict], *,
    variants: tuple[str, ...] = VARIANTS,
    tasks: tuple[str, ...] = TASKS,
    budgets: dict[str, int] | None = None,
) -> dict:
    """Verify numeric semantics and mirrored rates, without inferring treatment effects."""
    if budgets is None:
        budgets = BUDGETS
    main = _matrix(main_rows, "treatment", variants, tasks)
    support = _matrix(support_rows, "common evaluator", variants, tasks)
    for variant in variants:
        for task in tasks:
            label = f"{variant}/{task}"
            m, e = main[(variant, task)], support[(variant, task)]
            if str(m.get("completed", "")).strip().lower() not in ("true", "1", "yes"):
                raise NumericInputError(f"{label}: incomplete treatment")
            budget = _count(m, "source_budget", label)
            if budget != budgets[variant]:
                raise NumericInputError(f"{label}: source budget differs from treatment design")
            for key in ("successful_sources", "failed_sources", "search_calls",
                        "model_calls", "total_tokens", "report_words"):
                _count(m, key, label)
            if _count(m, "successful_sources", label) > budget:
                raise NumericInputError(f"{label}: successful sources exceed budget")
            for key in ("treatment_cost_usd", "latency_seconds"):
                _number(m, key, label)

            claims = _count(e, "claims_checked", label)
            if not 1 <= claims <= CLAIM_CAP:
                raise NumericInputError(f"{label}: claims_checked outside frozen 1-12 cap")
            parts = [_count(e, key, label) for key in (
                "supported", "partially_supported", "unsupported", "contradicted"
            )]
            if sum(parts) != claims:
                raise NumericInputError(f"{label}: evaluator claim-count partition mismatch")
            ratio = Decimal(parts[0]) / Decimal(claims)
            _rate(e, "strict_support_rate", ratio, label)
            _rate(m, "posthoc_strict_support_rate", ratio, label)
            if _count(m, "posthoc_claims_checked", label) != claims:
                raise NumericInputError(f"{label}: mirrored claims_checked mismatch")

            _count(e, "total_tokens", label)
            evaluator_cost = _number(e, "estimated_cost_usd", label)
            mirrored_cost = _number(m, "posthoc_evaluator_cost_usd", label)
            if abs(evaluator_cost - mirrored_cost) > TOL:
                raise NumericInputError(f"{label}: mirrored evaluator-cost mismatch")
    return {
        "status": "verified_internal_numeric_consistency_not_original_source_authenticity",
        "n_cells": len(main),
        "n_tasks": len(tasks),
        "n_variants": len(variants),
        "frozen_evaluator_claim_cap": CLAIM_CAP,
    }


def _csv_bytes(root: Path, relative: str) -> bytes:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise NumericInputError(f"{relative}: missing or redirected CSV")
    if path.stat().st_size > MAX_CSV_BYTES:
        raise NumericInputError(f"{relative}: CSV exceeds 2 MiB audit bound")
    content = path.read_bytes()
    if len(content) > MAX_CSV_BYTES:
        raise NumericInputError(f"{relative}: CSV grew beyond 2 MiB")
    return content


def _parse_csv(content: bytes, label: str) -> list[dict]:
    try:
        data = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers or len(headers) != len(set(headers)):
            raise NumericInputError(f"{label}: absent or duplicate CSV headers")
        if not {"variant_id", "task_id"}.issubset(headers):
            raise NumericInputError(f"{label}: missing cell identity headers")
        rows = list(reader)
        if any(None in row for row in rows):
            raise NumericInputError(f"{label}: surplus CSV fields")
    except (UnicodeDecodeError, csv.Error) as exc:
        raise NumericInputError(f"{label}: invalid UTF-8 or CSV structure") from exc
    return rows


def audit_files(root: Path = ROOT) -> dict:
    main_bytes = _csv_bytes(root, MAIN_PATH)
    support_bytes = _csv_bytes(root, SUPPORT_PATH)
    findings = audit_rows(
        _parse_csv(main_bytes, MAIN_PATH),
        _parse_csv(support_bytes, SUPPORT_PATH),
    )
    return {
        "schema_version": 1,
        **findings,
        "input_sha256": {
            MAIN_PATH: hashlib.sha256(main_bytes).hexdigest(),
            SUPPORT_PATH: hashlib.sha256(support_bytes).hexdigest(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        findings = audit_files(args.root)
    except NumericInputError as exc:
        parser.exit(1, f"main-study numeric preflight failed: {exc}\n")
    print(json.dumps(findings, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
