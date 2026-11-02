"""Read-only internal-integrity audit of frozen VERA analysis CSV inputs.

The canonical inference implementation and its independently pinned source
digest must remain byte-for-byte unchanged. This standalone preflight checks
recorded CSV structure and arithmetic without recomputing inference, invoking
agents/evaluators, or authenticating missing original experimental traces.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import os
import stat
from pathlib import Path

from scripts.validate_main_study_inputs import _validate_csv_record

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAIN = REPO_ROOT / "outputs" / "main_study_runs.csv"
DEFAULT_SUPPORT = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"
VARIANTS = ("D3", "D6", "P6", "P6V")
EXPECTED_TASKS = 10
MAX_INPUT_BYTES = 256 * 1024
MAX_EXACT_COUNT = (1 << 53) - 1


class InputIntegrityError(ValueError):
    """A retained summary is not an unambiguous numerical input."""


def _file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    """Metadata used to detect a path or open-file replacement during capture."""
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_size,
        metadata.st_mtime_ns, metadata.st_ctime_ns,
    )


def _capture_csv_bytes(path: Path, *, label: str) -> bytes:
    """Bounded descriptor capture, not historical experimental authentication."""
    if any(parent.is_symlink() for parent in path.parents):
        raise InputIntegrityError(f"{label} has a symlinked parent directory")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = None
    try:
        fd = os.open(path, flags)
        before = os.fstat(fd)
        path_before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or _file_identity(before) != _file_identity(path_before):
            raise InputIntegrityError(f"{label} must be a non-symlink regular CSV file")
        if not 0 < before.st_size <= MAX_INPUT_BYTES:
            raise InputIntegrityError(f"{label} is empty or exceeds input limit")
        captured = bytearray()
        while len(captured) <= MAX_INPUT_BYTES:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - len(captured)))
            if not chunk:
                break
            captured.extend(chunk)
        after = os.fstat(fd)
        path_after = os.stat(path, follow_symlinks=False)
        if not 0 < len(captured) <= MAX_INPUT_BYTES:
            raise InputIntegrityError(f"{label} is empty or exceeds input limit")
        if (
            len(captured) != before.st_size
            or _file_identity(before) != _file_identity(after)
            or _file_identity(before) != _file_identity(path_after)
        ):
            raise InputIntegrityError(f"{label} changed during bounded CSV capture")
        return bytes(captured)
    except OSError as exc:
        raise InputIntegrityError(f"{label} cannot be opened as a stable CSV file") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _read_csv(path: Path, *, label: str) -> tuple[bytes, list[dict[str, str]]]:
    raw = _capture_csv_bytes(Path(path), label=label)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputIntegrityError(f"{label} cannot be decoded as UTF-8 CSV") from exc
    # Apply the canonical one-record-per-physical-line lexical contract to
    # the exact captured text. DictReader otherwise skips blank lines and
    # accepts ambiguous quoted fields; a checksum alone cannot detect that
    # its interpretation has discarded or normalized input records.
    try:
        with io.StringIO(text, newline="") as lines:
            for line_number, record in enumerate(lines, start=1):
                _validate_csv_record(record, path=Path(path), line_number=line_number)
    except ValueError as exc:
        raise InputIntegrityError(f"{label} has noncanonical CSV record: {exc}") from exc
    with io.StringIO(text, newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        try:
            names = reader.fieldnames
            if not names or any(not name for name in names):
                raise InputIntegrityError(f"{label} has missing or empty headers")
            if len(names) != len(set(names)):
                raise InputIntegrityError(f"{label} has duplicate CSV headers")
            rows = list(reader)
        except csv.Error as exc:
            raise InputIntegrityError(f"{label} contains malformed CSV") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise InputIntegrityError(f"{label} has missing or extra CSV cells")
    return raw, rows


def _int(row: dict[str, str], field: str, *, label: str) -> int:
    text = row.get(field)
    if not isinstance(text, str) or not text.strip():
        raise InputIntegrityError(f"{label} missing count {field}")
    try:
        number = Decimal(text.strip())
        if not number.is_finite():
            raise InputIntegrityError(f"{label} nonfinite count {field}")
        if abs(number) > MAX_EXACT_COUNT:
            raise InputIntegrityError(f"{label} count {field} exceeds safe integer range")
        if number != number.to_integral_value():
            raise InputIntegrityError(f"{label} fractional count {field}")
        return int(number)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        if isinstance(exc, InputIntegrityError):
            raise
        raise InputIntegrityError(f"{label} invalid count {field}") from exc


def _finite_nonnegative(row: dict[str, str], field: str, *, label: str) -> float:
    text = row.get(field)
    if not isinstance(text, str) or not text.strip():
        raise InputIntegrityError(f"{label} missing measure {field}")
    try:
        value = float(text)
    except (ValueError, OverflowError) as exc:
        raise InputIntegrityError(f"{label} invalid measure {field}") from exc
    if not math.isfinite(value) or value < 0:
        raise InputIntegrityError(f"{label} nonfinite or negative measure {field}")
    return value


def _paired_rows(rows: list[dict[str, str]], *, label: str) -> dict[tuple[str, str], dict[str, str]]:
    if len(rows) != EXPECTED_TASKS * len(VARIANTS):
        raise InputIntegrityError(f"{label} does not contain exactly 40 cells")
    indexed = {}
    task_sets = {variant: set() for variant in VARIANTS}
    for row in rows:
        variant, task = row.get("variant_id"), row.get("task_id")
        if variant not in VARIANTS or not isinstance(task, str) or not task.strip():
            raise InputIntegrityError(f"{label} has unknown arm or missing task ID")
        key = (variant, task)
        if key in indexed:
            raise InputIntegrityError(f"{label} contains a duplicate cell")
        indexed[key] = row
        task_sets[variant].add(task)
    if any(len(tasks) != EXPECTED_TASKS for tasks in task_sets.values()):
        raise InputIntegrityError(f"{label} has unbalanced task counts")
    if any(task_sets[v] != task_sets[VARIANTS[0]] for v in VARIANTS[1:]):
        raise InputIntegrityError(f"{label} treatment arms lack identical task sets")
    return indexed


def _check_original_task_ids(task_ids: set[str]) -> str:
    """Bind summary cell IDs to the original-run source manifest, not only each other.

    The anchor is a Git-preserved treatment-source identity, never independent
    authentication of missing historical traces, reports or retrievals.
    """
    from scripts.verify_frozen_main_study_tasks import verify_frozen_task_manifest

    try:
        source_receipt = verify_frozen_task_manifest(repo_root=REPO_ROOT)
    except (OSError, ValueError, UnicodeError) as exc:
        raise InputIntegrityError(
            "original treatment task-manifest source failed verification"
        ) from exc
    expected = {f"main-{ordinal:02d}" for ordinal in range(1, EXPECTED_TASKS + 1)}
    if task_ids != expected:
        raise InputIntegrityError(
            "summary task IDs differ from the pinned original treatment task set"
        )
    return source_receipt["original_task_manifest_sha256"]


def audit_frozen_csv_inputs(
    main_csv: Path = DEFAULT_MAIN,
    support_csv: Path = DEFAULT_SUPPORT,
    *,
    require_original_task_set: bool = True,
) -> dict:
    """Audit retained summaries; the source-anchor opt-out is synthetic-only."""
    main_raw, main_rows = _read_csv(main_csv, label="treatment summary")
    support_raw, support_rows = _read_csv(support_csv, label="evaluator summary")
    main = _paired_rows(main_rows, label="treatment summary")
    support = _paired_rows(support_rows, label="evaluator summary")
    if set(main) != set(support):
        raise InputIntegrityError("treatment and evaluator cell identities differ")
    # Balanced CSVs can both be relabelled to a different 10-task study.
    # Production/default auditing requires the exact original task-source pin
    # and its fixed IDs; only deliberately synthetic API fixtures may opt out.
    original_manifest_sha = (
        _check_original_task_ids({task for _, task in main})
        if require_original_task_set else None
    )
    seen_run_ids = set()
    for (variant, task), row in main.items():
        label = f"{variant}/{task}"
        if row.get("completed", "").strip().lower() not in {"true", "1", "yes"}:
            raise InputIntegrityError(f"{label} is an incomplete treatment cell")
        budget = 3 if variant == "D3" else 6
        if _int(row, "source_budget", label=label) != budget:
            raise InputIntegrityError(f"{label} assigned source budget drift")
        source_counts = {}
        for field in (
            "successful_sources", "failed_sources", "search_calls",
            "model_calls", "total_tokens", "report_words",
        ):
            count = _int(row, field, label=label)
            if count < 0:
                raise InputIntegrityError(f"{label} has negative treatment count {field}")
            source_counts[field] = count
        if source_counts["successful_sources"] + source_counts["failed_sources"] > budget:
            raise InputIntegrityError(f"{label} recorded source usage exceeds budget")
        _finite_nonnegative(row, "treatment_cost_usd", label=label)
        _finite_nonnegative(row, "latency_seconds", label=label)
        _finite_nonnegative(row, "posthoc_evaluator_cost_usd", label=label)
        if not 0 <= _finite_nonnegative(
            row, "posthoc_strict_support_rate", label=label
        ) <= 1:
            raise InputIntegrityError(f"{label} invalid mirrored strict support")
        mirrored_claims = _int(row, "posthoc_claims_checked", label=label)
        if not 1 <= mirrored_claims <= 12:
            raise InputIntegrityError(f"{label} mirrored claims exceed evaluator cap")

        evaluation = support[(variant, task)]
        run_id = evaluation.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip() or run_id in seen_run_ids:
            raise InputIntegrityError(f"{label} missing or reused evaluator run ID")
        seen_run_ids.add(run_id)
        claims = _int(evaluation, "claims_checked", label=label)
        if not 1 <= claims <= 12:
            raise InputIntegrityError(f"{label} evaluator claims exceed frozen 12-claim cap")
        counts = [
            _int(evaluation, name, label=label) for name in
            ("supported", "partially_supported", "unsupported", "contradicted")
        ]
        if any(count < 0 or count > claims for count in counts):
            raise InputIntegrityError(f"{label} invalid evaluator category count")
        if sum(counts) != claims:
            raise InputIntegrityError(f"{label} evaluator categories do not partition claims")
        _int(evaluation, "total_tokens", label=label)
        if _int(evaluation, "total_tokens", label=label) < 0:
            raise InputIntegrityError(f"{label} negative evaluator token count")
        cost = _finite_nonnegative(evaluation, "estimated_cost_usd", label=label)
        rate = _finite_nonnegative(evaluation, "strict_support_rate", label=label)
        if rate > 1 or not math.isclose(rate, counts[0] / claims, rel_tol=0, abs_tol=1e-12):
            raise InputIntegrityError(f"{label} evaluator strict support disagrees with counts")
        if (
            mirrored_claims != claims
            or not math.isclose(
                float(row["posthoc_strict_support_rate"]), rate,
                rel_tol=0, abs_tol=1e-12
            )
            or not math.isclose(
                float(row["posthoc_evaluator_cost_usd"]), cost,
                rel_tol=0, abs_tol=1e-12
            )
        ):
            raise InputIntegrityError(f"{label} treatment/evaluator mirror disagreement")
        # Frozen evidence-only scoring: without successfully retrieved evidence,
        # no checked claim can receive support, partial support or contradiction.
        # Validate the self-reported sentinel and the complete label partition;
        # internally consistent but fabricated nonzero rates must not pass.
        evidence_status = evaluation.get("evidence_status", "")
        if source_counts["successful_sources"] == 0:
            if evidence_status != "zero_successful_sources":
                raise InputIntegrityError(f"{label} zero-source cell lacks evidence sentinel")
            if counts != [0, 0, claims, 0]:
                raise InputIntegrityError(f"{label} zero-source cell has non-unsupported labels")
        elif evidence_status == "zero_successful_sources":
            raise InputIntegrityError(f"{label} zero-evidence sentinel contradicts sources")
    return {
        "status": "pass_summary_csv_internal_consistency_only",
        "main_sha256": hashlib.sha256(main_raw).hexdigest(),
        "evaluator_sha256": hashlib.sha256(support_raw).hexdigest(),
        "paired_cells": len(main),
        "arms": list(VARIANTS),
        "frozen_task_ids_match_original_source": require_original_task_set,
        "original_task_manifest_sha256": original_manifest_sha,
        "frozen_analysis_recomputed": False,
        "original_executions_independently_authenticated": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-csv", type=Path, default=DEFAULT_MAIN)
    parser.add_argument("--support-csv", type=Path, default=DEFAULT_SUPPORT)
    args = parser.parse_args()
    try:
        result = audit_frozen_csv_inputs(args.main_csv, args.support_csv)
    except InputIntegrityError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
