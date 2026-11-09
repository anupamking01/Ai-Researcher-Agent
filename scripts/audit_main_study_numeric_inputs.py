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
import math
import os
import stat
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = "outputs/main_study_runs.csv"
SUPPORT_PATH = "outputs/posthoc_support_runs.csv"
VARIANTS = ("D3", "D6", "P6", "P6V")
TASKS = tuple(f"main-{index:02d}" for index in range(1, 11))
BUDGETS = {"D3": 3, "D6": 6, "P6": 6, "P6V": 6}
CLAIM_CAP = 12
# Historical study costs are model-token estimates, not provider invoices.
# The exact provenance label was emitted by the preserved September summarizer.
FROZEN_TREATMENT_COST_STATUS = "estimated_from_frozen_uncached_rates"
TOL = Decimal("0.000000000001")
MAX_CSV_BYTES = 2 * 1024 * 1024
# Guard the independent Decimal parser against tiny exponent-bomb tokens and
# count values too large for exact downstream float-based analysis. The existing
# frozen-input audit independently applies the same exact-integer ceiling.
MAX_NUMERIC_TOKEN_CHARS = 128
MAX_FLOAT_DECIMAL_EXPONENT = 308
MIN_FLOAT_DECIMAL_EXPONENT = -324
MAX_EXACT_INTEGER = (1 << 53) - 1


class NumericInputError(ValueError):
    """Frozen analysis CSVs are structurally or numerically inconsistent."""


def _number(row: dict, key: str, label: str) -> Decimal:
    raw = row.get(key)
    if raw is None or str(raw).strip() == "":
        raise NumericInputError(f"{label}: missing numeric {key}")
    token = str(raw).strip()
    if len(token) > MAX_NUMERIC_TOKEN_CHARS:
        raise NumericInputError(f"{label}: oversized numeric token {key}")
    try:
        number = Decimal(token)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise NumericInputError(f"{label}: invalid numeric {key}") from exc
    if not number.is_finite() or number < 0:
        raise NumericInputError(f"{label}: nonfinite or negative {key}")
    # Bound the exponent before conversion; an exponent bomb is only a few
    # bytes in CSV. A nonzero input must not overflow to infinity or silently
    # underflow to zero in the historical binary64-based analysis pipeline.
    # Permit finite subnormal values down to approximately 5e-324.
    if number != 0:
        exponent = number.adjusted()
        if not MIN_FLOAT_DECIMAL_EXPONENT <= exponent <= MAX_FLOAT_DECIMAL_EXPONENT:
            raise NumericInputError(f"{label}: extreme numeric exponent {key}")
        converted = float(number)
        if not math.isfinite(converted) or converted == 0:
            raise NumericInputError(f"{label}: nonrepresentable numeric {key}")
    return number


def _count(row: dict, key: str, label: str) -> int:
    value = _number(row, key, label)
    if value != value.to_integral_value():
        raise NumericInputError(f"{label}: fractional count {key}")
    if value > MAX_EXACT_INTEGER:
        raise NumericInputError(f"{label}: count {key} exceeds exact-integer ceiling")
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
    seen_evaluator_runs: set[str] = set()
    for variant in variants:
        for task in tasks:
            label = f"{variant}/{task}"
            m, e = main[(variant, task)], support[(variant, task)]
            run_id = e.get("run_id")
            if (not isinstance(run_id, str) or not run_id.strip()
                    or run_id in seen_evaluator_runs):
                raise NumericInputError(f"{label}: missing or duplicate evaluator run_id")
            seen_evaluator_runs.add(run_id)
            if str(m.get("completed", "")).strip().lower() not in ("true", "1", "yes"):
                raise NumericInputError(f"{label}: incomplete treatment")
            budget = _count(m, "source_budget", label)
            if budget != budgets[variant]:
                raise NumericInputError(f"{label}: source budget differs from treatment design")
            for key in ("successful_sources", "failed_sources", "search_calls",
                        "model_calls", "total_tokens", "report_words"):
                _count(m, key, label)
            successful = _count(m, "successful_sources", label)
            failed = _count(m, "failed_sources", label)
            if successful + failed > budget:
                raise NumericInputError(
                    f"{label}: successful plus failed sources exceed budget"
                )
            for key in ("treatment_cost_usd", "latency_seconds"):
                _number(m, key, label)
            if m.get("cost_status") != FROZEN_TREATMENT_COST_STATUS:
                raise NumericInputError(
                    f"{label}: cost_status differs from frozen estimated-cost provenance"
                )

            claims = _count(e, "claims_checked", label)
            if not 1 <= claims <= CLAIM_CAP:
                raise NumericInputError(f"{label}: claims_checked outside frozen 1-12 cap")
            parts = [_count(e, key, label) for key in (
                "supported", "partially_supported", "unsupported", "contradicted"
            )]
            if sum(parts) != claims:
                raise NumericInputError(f"{label}: evaluator claim-count partition mismatch")
            evidence_status = e.get("evidence_status", "")
            if successful == 0:
                if evidence_status != "zero_successful_sources":
                    raise NumericInputError(
                        f"{label}: zero-source cell lacks evaluator evidence sentinel"
                    )
                if parts != [0, 0, claims, 0]:
                    raise NumericInputError(
                        f"{label}: zero-source cell contains evidence-dependent labels"
                    )
            elif evidence_status == "zero_successful_sources":
                raise NumericInputError(
                    f"{label}: zero-evidence sentinel contradicts retrieved sources"
                )
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
    """Read a bounded, path-bound regular CSV through a held file descriptor.

    The pathname, opened file, and captured bytes must describe the same
    generation. This checks local read integrity, not original-source custody.
    """
    path = root / relative
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        parent_fd = os.open(path.parent, directory_flags)
        try:
            parent = os.fstat(parent_fd)
            if not stat.S_ISDIR(parent.st_mode):
                raise NumericInputError(f"{relative}: CSV parent is not a directory")
            file_fd = os.open(path.name, file_flags, dir_fd=parent_fd)
            try:
                before = os.fstat(file_fd)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise NumericInputError(
                        f"{relative}: CSV must be a single-linked regular file"
                    )
                if before.st_size > MAX_CSV_BYTES:
                    raise NumericInputError(f"{relative}: CSV exceeds 2 MiB audit bound")

                chunks = []
                offset = 0
                while offset < before.st_size:
                    chunk = os.pread(
                        file_fd, min(1024 * 1024, before.st_size - offset), offset
                    )
                    if not chunk:
                        raise NumericInputError(f"{relative}: CSV truncated during capture")
                    chunks.append(chunk)
                    offset += len(chunk)
                if os.pread(file_fd, 1, before.st_size):
                    raise NumericInputError(f"{relative}: CSV grew during capture")

                after = os.fstat(file_fd)
                visible = os.stat(
                    path.name, dir_fd=parent_fd, follow_symlinks=False
                )
                visible_parent = os.stat(path.parent, follow_symlinks=False)
                def fingerprint(info):
                    return (
                        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                        info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                    )
                if (
                    fingerprint(before) != fingerprint(after)
                    or fingerprint(after) != fingerprint(visible)
                    or not stat.S_ISDIR(visible_parent.st_mode)
                    or (parent.st_dev, parent.st_ino)
                    != (visible_parent.st_dev, visible_parent.st_ino)
                ):
                    raise NumericInputError(f"{relative}: CSV changed during capture")
                return b"".join(chunks)
            finally:
                os.close(file_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise NumericInputError(
            f"{relative}: CSV missing, redirected, or changed during capture"
        ) from exc


def _unsafe_spreadsheet_text(value: str) -> bool:
    """Reject executable-looking CSV prefixes before numeric normalization."""
    for char in value:
        if char.isspace() or unicodedata.category(char)[0] in ("C", "Z"):
            continue
        return char in "=+-@"
    return False


def _parse_csv(content: bytes, label: str) -> list[dict]:
    try:
        data = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers or len(headers) != len(set(headers)):
            raise NumericInputError(f"{label}: absent or duplicate CSV headers")
        if not {"variant_id", "task_id"}.issubset(headers):
            raise NumericInputError(f"{label}: missing cell identity headers")
        if any(_unsafe_spreadsheet_text(header) for header in headers):
            raise NumericInputError(f"{label}: formula-like CSV header")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values())
               for row in rows):
            raise NumericInputError(f"{label}: missing or surplus CSV fields")
        for line, row in enumerate(rows, start=2):
            # Inspect all raw exported cells, including unused metadata, before
            # Decimal parsing can normalize formula-looking numeric tokens.
            for column, value in row.items():
                if _unsafe_spreadsheet_text(value):
                    raise NumericInputError(
                        f"{label}: formula-like CSV cell {column} in row {line}"
                    )
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
    # Recheck both original paths before issuing the fingerprint receipt.
    # This is not an atomic filesystem snapshot and cannot authenticate
    # historical experimental source artifacts.
    if _csv_bytes(root, MAIN_PATH) != main_bytes:
        raise NumericInputError(f"{MAIN_PATH}: CSV changed before audit receipt")
    if _csv_bytes(root, SUPPORT_PATH) != support_bytes:
        raise NumericInputError(f"{SUPPORT_PATH}: CSV changed before audit receipt")
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
