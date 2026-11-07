"""Reconcile historical evaluator-source recovery with frozen measurement metadata.

This audit does not invoke the evaluator, recalculate scores, or authenticate the
missing original treatment reports/traces. Its per-cell status is self-reported
in the *published, byte-pinned* evaluator-summary CSV, not an execution log.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from scripts import audit_frozen_analysis_csv_inputs as frozen
from scripts import audit_historical_common_evaluator_policy as source

VARIANTS = ("D3", "D6", "P6", "P6V")
TASK_IDS = tuple(f"main-{i:02d}" for i in range(1, 11))
# The original recovery workflow explicitly requires exactly these three
# missing cells, before evaluator-only resume (source audit checks its blob).
RECOVERED = {
    ("P6V", "main-02"): "retrieved_evidence",
    ("P6V", "main-08"): "retrieved_evidence",
    ("P6V", "main-10"): "zero_successful_sources",
}
FIELDS = (
    "variant_id", "task_id", "run_id", "evidence_status", "claims_checked",
    "supported", "partially_supported", "unsupported", "contradicted",
    "strict_support_rate", "total_tokens", "estimated_cost_usd",
)


class EvaluatorPartitionError(ValueError):
    """Frozen evaluator summary cannot support the stated provenance partition."""


def inspect_partition(raw: bytes, *, expected_sha256: str) -> dict:
    """Validate a single captured CSV byte snapshot; test pins can be synthetic."""
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise EvaluatorPartitionError("evaluator CSV differs from independently pinned bytes")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
        if reader.fieldnames != list(FIELDS):
            raise EvaluatorPartitionError("frozen evaluator CSV column contract changed")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise EvaluatorPartitionError("invalid frozen evaluator CSV encoding or records") from exc
    if len(rows) != len(VARIANTS) * len(TASK_IDS):
        raise EvaluatorPartitionError("frozen evaluator CSV must contain exactly 40 records")
    observed: set[tuple[str, str]] = set()
    run_ids: set[str] = set()
    for row in rows:
        if set(row) != set(FIELDS) or any(not isinstance(v, str) for v in row.values()):
            raise EvaluatorPartitionError("frozen evaluator CSV has missing or extra fields")
        variant, task, run_id = (row[k] for k in ("variant_id", "task_id", "run_id"))
        cell = (variant, task)
        if (variant not in VARIANTS or task not in TASK_IDS or cell in observed
                or not run_id or run_id != run_id.strip() or run_id in run_ids):
            raise EvaluatorPartitionError("invalid, duplicate or reused evaluator cell identity")
        observed.add(cell)
        run_ids.add(run_id)
        if row["evidence_status"] != RECOVERED.get(cell, ""):
            raise EvaluatorPartitionError(
                f"frozen recovery status disagrees with historical workflow: {variant}/{task}"
            )
    if observed != {(v, t) for v in VARIANTS for t in TASK_IDS}:
        raise EvaluatorPartitionError("frozen evaluator CSV is missing a treatment/task cell")
    return {
        "status": "published_summary_recovery_partition_source_concordance_only",
        "frozen_evaluator_csv_sha256": expected_sha256,
        "cells": len(observed),
        "source_declared_original_cached_cells": 37,
        "source_declared_evaluator_only_recovered_cells": 3,
        "frozen_summary_nonempty_recovery_status_cells": 3,
        "frozen_summary_blank_legacy_status_cells": 37,
        "recovered_cell_statuses": {
            f"{variant}/{task}": status for (variant, task), status in sorted(RECOVERED.items())
        },
        "recovery_cells_by_arm": {v: sum(cell[0] == v for cell in RECOVERED) for v in VARIANTS},
        "recovered_share_of_p6v_cells": "3/10",
        "recovered_zero_evidence_status_cells": ["P6V/main-10"],
        "input_policy_drift_is_arm_concentrated": True,
        "per_cell_status_is_frozen_csv_self_report": True,
        "original_trace_report_custody_authenticated": False,
        "original_evaluator_execution_authenticated": False,
        "recovered_evaluator_execution_authenticated": False,
        "recovered_sentinel_provider_call_authenticated": False,
        "bias_direction_or_magnitude_established": False,
        "automated_inference_recomputed": False,
        "human_validation_performed": False,
    }


def audit_checkout(root: Path) -> dict:
    """Bind source chronology and 40-cell CSV preflight before interpreting status."""
    root = root.resolve()
    source_receipt = source.audit_checkout(root)
    if (source_receipt["entire_evaluator_input_policy_identical"] is not False
            or source_receipt["recovery_zero_successful_source_sentinel_added"] is not True):
        raise EvaluatorPartitionError("historical evaluator-policy difference unverified")
    frozen.audit_frozen_csv_inputs(
        root / "outputs/main_study_runs.csv",
        root / "outputs/posthoc_support_runs.csv",
    )
    raw = frozen._capture_csv_bytes(
        root / "outputs/posthoc_support_runs.csv", label="frozen evaluator partition"
    )
    receipt = inspect_partition(raw, expected_sha256=frozen.FROZEN_SUPPORT_CSV_SHA256)
    receipt["historical_source_policy_audited"] = True
    receipt["frozen_treatment_evaluator_summary_preflight_passed"] = True
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        receipt = audit_checkout(args.root)
    except (EvaluatorPartitionError, frozen.InputIntegrityError,
            source.HistoricalEvaluatorPolicyError,
            source.history.HistoricalDesignSourceError) as exc:
        parser.exit(1, f"historical evaluator partition audit failed: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
