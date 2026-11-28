"""Source-bound, outcome-free historical ten-task freeze chronology."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.audit_main_study_design_identifiability import TASK_IDS

FREEZE = "b1fe8e15ed4daa98b6539616dfb735cf40f49b6b"
LAUNCH = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
PATH = "experiments/main_budget_tasks.json"
BLOB = "68316fdb00631856006119370f9f549b23d1bee3"
TASK_SET = "main-budget-v1-2026-09-11"

class TaskFreezeError(ValueError):
    """Historical task-freeze custody cannot be established."""

def inspect_manifest(raw: bytes) -> list[str]:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise TaskFreezeError("duplicate JSON key")
            obj[key] = value
        return obj
    def no_constant(value):
        raise TaskFreezeError("non-finite JSON constant")
    if type(raw) is not bytes or not 0 < len(raw) <= 128 * 1024:
        raise TaskFreezeError("source byte bounds")
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                              parse_constant=no_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise TaskFreezeError("invalid manifest JSON") from exc
    if (type(manifest) is not dict or
        set(manifest) != {"task_set_id", "frozen_before_execution", "purpose", "tasks"}
        or manifest["task_set_id"] != TASK_SET
        or manifest["frozen_before_execution"] is not True
        or type(manifest["purpose"]) is not str or not manifest["purpose"].strip()):
        raise TaskFreezeError("historical task-set identity")
    rows = manifest["tasks"]
    if type(rows) is not list or len(rows) != len(TASK_IDS):
        raise TaskFreezeError("historical task count")
    ids = []
    for row in rows:
        if (type(row) is not dict or set(row) != {"id", "category", "question"}
            or any(type(row[key]) is not str or not row[key].strip()
                   for key in ("id", "category", "question"))):
            raise TaskFreezeError("invalid task row")
        ids.append(row["id"])
    if tuple(ids) != TASK_IDS:
        raise TaskFreezeError("historical task IDs or order changed")
    return ids

def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(root), *args],
                                capture_output=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TaskFreezeError("Git history unavailable") from exc
    if result.returncode:
        raise TaskFreezeError(f"git {args[0]} failed; full history required")
    return result.stdout

def audit(root: Path) -> dict:
    root = root.resolve()
    if _git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root):
        raise TaskFreezeError("expected repository root")
    if _git(root, "rev-parse", "--is-shallow-repository").decode().strip() != "false":
        raise TaskFreezeError("full non-shallow Git history required")
    for sha in (FREEZE, LAUNCH):
        if _git(root, "rev-parse", f"{sha}^{{commit}}").decode().strip() != sha:
            raise TaskFreezeError("pinned historical commit missing")
    _git(root, "merge-base", "--is-ancestor", FREEZE, LAUNCH)
    _git(root, "merge-base", "--is-ancestor", LAUNCH, "HEAD")
    old_blob = _git(root, "rev-parse", f"{FREEZE}:{PATH}").decode().strip()
    run_blob = _git(root, "rev-parse", f"{LAUNCH}:{PATH}").decode().strip()
    if old_blob != BLOB or run_blob != BLOB:
        raise TaskFreezeError("prelaunch and launch manifest blob mismatch")
    source = _git(root, "show", f"{FREEZE}:{PATH}")
    ids = inspect_manifest(source)
    return {
        "schema_version": 1, "status": "historical_git_task_prelaunch_freeze_only",
        "historical_task_freeze_commit": FREEZE, "historical_launch_commit": LAUNCH,
        "manifest_path": PATH, "manifest_git_blob": BLOB,
        "manifest_sha256": hashlib.sha256(source).hexdigest(),
        "task_ids": ids,
        "prelaunch_git_ancestry_verified": True, "unchanged_manifest_blob_at_launch": True,
        "independent_external_task_preregistration_established": False,
        "task_selection_outcome_blinding_established": False,
        "task_independence_established": False,
        "original_treatment_execution_authenticated": False,
        "original_report_trace_custody_authenticated": False,
        "human_validation_performed": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    try:
        print(json.dumps(audit(parser.parse_args().root), indent=2, sort_keys=True))
    except TaskFreezeError as exc:
        parser.exit(1, f"historical task freeze audit failed: {exc}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
