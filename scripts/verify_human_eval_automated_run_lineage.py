"""Audit lineage between VERA's frozen automated-evaluator runs and blinded reports.

Coordinator-only, read-only pre-unblinding gate. It compares actual run IDs
per frozen treatment/task cell; task-level coverage alone is not sufficient to
show that people will rate the reports measured by the automated evaluator.

No blinding key is disclosed in output, no scores are read, and no treatments,
evaluation calls, inference, or human judgments are generated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from scripts import build_human_eval_packet as packet_builder
from scripts import validate_main_study_inputs as inputs
from scripts import verify_human_eval_packet as packet_verifier
from scripts import verify_research_artifact_manifest as manifest_verifier

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("D3", "D6", "P6", "P6V")
TASKS = tuple(f"main-{n:02d}" for n in range(1, 11))
MAIN_REL = "outputs/main_study_runs.csv"
SUPPORT_REL = "outputs/posthoc_support_runs.csv"


def _matrix(rows, *, label, expected_cells, run_identity):
    """Reject missing, duplicated, or aliased frozen cell/run identities."""
    if not isinstance(rows, list) or len(rows) != len(expected_cells):
        raise ValueError(f"{label} must contain exactly {len(expected_cells)} cells")
    by_cell = {}
    used_runs = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label} contains a non-object row")
        variant, task = row.get("variant_id"), row.get("task_id")
        if type(variant) is not str or type(task) is not str:
            raise ValueError(f"{label} contains non-string cell identity")
        cell = (variant, task)
        if cell not in expected_cells:
            raise ValueError(f"{label} contains an unexpected cell: {cell}")
        if cell in by_cell:
            raise ValueError(f"{label} contains a duplicate cell: {cell}")
        if run_identity:
            run_id = row.get("run_id")
            if (
                type(run_id) is not str or not run_id
                or run_id != run_id.strip()
                or any(character in run_id for character in ("/", "\\", "\n", "\r", "\x00"))
                or run_id in (".", "..")
            ):
                raise ValueError(f"{label} has an invalid run ID for {cell}")
            if run_id in used_runs:
                raise ValueError(f"{label} aliases one run ID to multiple cells")
            used_runs.add(run_id)
        by_cell[cell] = row
    if set(by_cell) != expected_cells:
        raise ValueError(f"{label} frozen cell coverage differs")
    return by_cell


def compare_run_lineage(
    key_rows: list[dict],
    main_rows: list[dict],
    evaluator_rows: list[dict],
    *,
    expected_tasks: tuple[str, ...] = TASKS,
) -> dict:
    """Compare the coordinator key with both preserved automated input tables.

    The primary treatment CSV has no run_id column, whereas the common evaluator
    CSV does. The latter is the sole exported per-run link to the traced report.
    Callers must separately verify packet source files and archived CSV hashes.
    """
    if (
        type(expected_tasks) is not tuple or not expected_tasks
        or any(type(task) is not str or not task for task in expected_tasks)
        or len(set(expected_tasks)) != len(expected_tasks)
    ):
        raise ValueError("expected task IDs must be a nonempty unique tuple")
    expected_cells = {(variant, task) for variant in VARIANTS for task in expected_tasks}
    key = _matrix(
        key_rows, label="coordinator blinding key",
        expected_cells=expected_cells, run_identity=True,
    )
    main = _matrix(
        main_rows, label="automated treatment export",
        expected_cells=expected_cells, run_identity=False,
    )
    evaluated = _matrix(
        evaluator_rows, label="automated evaluator export",
        expected_cells=expected_cells, run_identity=True,
    )
    for cell in sorted(expected_cells):
        if key[cell]["run_id"] != evaluated[cell]["run_id"]:
            raise ValueError(
                "human packet/automated evaluator run lineage mismatch for "
                f"{cell[0]}/{cell[1]}"
            )
        # The legacy treatment CSV has no run_id. Ensure its same-cell support
        # count refers to the evaluator record whenever that mirror is present.
        checked = main[cell].get("posthoc_claims_checked")
        if checked is not None and (
            type(checked) is not str or checked != evaluated[cell].get("claims_checked")
        ):
            try:
                consistent = int(checked) == int(evaluated[cell]["claims_checked"])
            except (ValueError, TypeError, KeyError):
                consistent = False
            if not consistent:
                raise ValueError(
                    f"automated treatment/evaluator count mirror mismatch for {cell}"
                )
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_packet_automated_run_lineage_consistent",
        "n_tasks": len(expected_tasks),
        "n_reports": len(expected_cells),
        "run_ids_matched": len(expected_cells),
        "human_ratings_read": False,
        "treatment_outputs_rerun": False,
        "evaluator_outputs_rerun": False,
    }


def _read_study_csv(raw: bytes, *, path: Path) -> list[dict[str, str]]:
    """Parse exactly the bytes captured for the cross-source verification window."""
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"study CSV must be UTF-8: {path}") from exc
    for line_number, record in enumerate(io.StringIO(decoded, newline=""), 1):
        inputs._validate_csv_record(record, path=path, line_number=line_number)
    reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
    names = reader.fieldnames or []
    if not names or any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError(f"invalid or duplicated study CSV headers: {path}")
    rows = []
    try:
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"ragged study CSV row in {path}")
            rows.append(row)
    except csv.Error as exc:
        raise ValueError(f"malformed study CSV: {path}") from exc
    return rows


def audit_files(
    *,
    repo_root: Path = ROOT,
    packet_root: Path | None = None,
    task_manifest_path: Path | None = None,
    research_manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
    expected_tasks: tuple[str, ...] = TASKS,
) -> dict:
    """Verify the packet's actual reports and the frozen evaluator run lineage.

    An independently stored manifest SHA-256 is required to claim *external*
    archival anchoring. Unpinned mode is useful for diagnostics but cannot
    authenticate which historical CSV version was supplied.
    """
    repo_root = Path(repo_root)
    packet_root = Path(packet_root) if packet_root is not None else repo_root / "outputs/human_eval"
    task_manifest_path = (
        Path(task_manifest_path) if task_manifest_path is not None
        else repo_root / "experiments/main_budget_tasks.json"
    )
    if (research_manifest_path is None) != (expected_manifest_sha256 is None):
        raise ValueError(
            "archival anchoring requires both a research manifest and its "
            "independently retained SHA-256"
        )
    main_path = repo_root / MAIN_REL
    support_path = repo_root / SUPPORT_REL
    key_path = packet_root / "blinding_key.csv"
    paths = {
        "treatment": main_path,
        "evaluator": support_path,
        "coordinator_key": key_path,
    }
    # Bound all four files by content across the sequential verifier calls.
    initial = {
        name: packet_builder._read_regular_file_captured(path, label=name)
        for name, path in paths.items()
    }
    if research_manifest_path is not None:
        entries = manifest_verifier.verify_manifest_file(
            Path(research_manifest_path), root=repo_root,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        if {entry["path"] for entry in entries} != {MAIN_REL, SUPPORT_REL}:
            raise ValueError("archival manifest must bind exactly both canonical CSV inputs")

    packet = packet_verifier.verify_packet(
        output_root=packet_root,
        task_manifest_path=task_manifest_path,
        repo_root=repo_root,
    )
    key_rows = packet_verifier._read_csv(
        initial["coordinator_key"],
        fields=packet_verifier.KEY_FIELDS,
        label="coordinator blinding key",
    )
    main_rows = _read_study_csv(initial["treatment"], path=main_path)
    support_rows = _read_study_csv(initial["evaluator"], path=support_path)
    # Historical canonical analysis CSVs predate stricter prospective pricing
    # metadata. Enforce scientific row domains here, not modern pricing schema.
    inputs.validate_rows(main_rows, support_rows, require_canonical_matrix=False)
    checked = compare_run_lineage(
        key_rows, main_rows, support_rows, expected_tasks=expected_tasks
    )
    if (
        packet.get("n_reports") != checked["n_reports"]
        or packet.get("n_tasks") != checked["n_tasks"]
    ):
        raise ValueError("verified human packet cardinality differs from automated matrix")
    for name, path in paths.items():
        if packet_builder._read_regular_file_captured(path, label=name) != initial[name]:
            raise ValueError(f"{name} changed during cross-study run lineage verification")

    return {
        **checked,
        "archival_manifest_externally_pinned": research_manifest_path is not None,
        "interpretation": (
            "Coordinator-only report/run alignment preflight; not evidence of "
            "human scoring, original data authenticity, or atomic archival snapshot"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--packet-root", type=Path)
    parser.add_argument("--task-manifest", type=Path)
    parser.add_argument("--research-manifest", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    try:
        result = audit_files(
            repo_root=args.repo_root,
            packet_root=args.packet_root,
            task_manifest_path=args.task_manifest,
            research_manifest_path=args.research_manifest,
            expected_manifest_sha256=args.expected_manifest_sha256,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"HUMAN/AUTOMATED RUN LINEAGE: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
