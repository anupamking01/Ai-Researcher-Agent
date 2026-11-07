"""Guard the exact main-study task manifest used by the original treatment run.

The GitHub Actions treatment run 34620917346 executed source revision
c3c15e46a8eec3a8bbc24c968eedc0548172a897. At that revision,
experiments/main_budget_tasks.json has Git blob ID
68316fdb00631856006119370f9f549b23d1bee3, and the SHA-256 below
was calculated from its exact UTF-8 bytes.

This is a versioned original-run SOURCE anchor, not an independently signed
archive or an authentication of recovered reports/human ratings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts import build_human_eval_packet as packet_builder

ROOT = Path(__file__).resolve().parents[1]
TASK_MANIFEST_REL = "experiments/main_budget_tasks.json"
ORIGINAL_TREATMENT_RUN_ID = 34620917346
ORIGINAL_TREATMENT_COMMIT = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
ORIGINAL_TASK_MANIFEST_GIT_BLOB = "68316fdb00631856006119370f9f549b23d1bee3"
ORIGINAL_TASK_MANIFEST_SHA256 = "5701df80036edb354f4f7d1efc409ea8f554a215f8c37da9d1a0b8ed01fdfd5f"


def verify_frozen_task_manifest(
    *, repo_root: Path = ROOT, task_manifest_path: Path | None = None
) -> dict:
    """Fail closed on task-set drift, including coherent question rewrites.

    Capture the source once with the packet builder's bounded, regular-file
    reader. Check exact bytes before parsing, so changing both the task
    manifest and recovered traces cannot silently redefine the study tasks.
    """
    path = (Path(task_manifest_path) if task_manifest_path is not None
            else Path(repo_root) / TASK_MANIFEST_REL)
    raw = packet_builder._read_regular_file_captured(
        path, label="original treatment-run task manifest"
    )
    observed = hashlib.sha256(raw).hexdigest()
    if observed != ORIGINAL_TASK_MANIFEST_SHA256:
        raise ValueError(
            "task manifest differs from the original treatment-run source; "
            "do not regenerate or re-pin study tasks from a changed copy"
        )
    parsed = packet_builder._load_json_object(
        raw, label="original treatment-run task manifest"
    )
    tasks = parsed.get("tasks")
    if (
        parsed.get("task_set_id") != "main-budget-v1-2026-09-11"
        or parsed.get("frozen_before_execution") is not True
        or not isinstance(tasks, list)
        or len(tasks) != 10
        or [t.get("id") for t in tasks if isinstance(t, dict)]
        != [f"main-{n:02d}" for n in range(1, 11)]
    ):
        raise ValueError("original task manifest schema or frozen task matrix invalid")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "original_treatment_run_task_manifest_matches",
        "task_set_id": parsed["task_set_id"],
        "n_tasks": 10,
        "original_treatment_run_id": ORIGINAL_TREATMENT_RUN_ID,
        "original_treatment_commit": ORIGINAL_TREATMENT_COMMIT,
        "original_task_manifest_sha256": ORIGINAL_TASK_MANIFEST_SHA256,
        "independent_historical_archive_authentication": False,
        "human_ratings_used": False,
        "treatments_rerun": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--task-manifest", type=Path)
    args = parser.parse_args()
    try:
        receipt = verify_frozen_task_manifest(
            repo_root=args.repo_root, task_manifest_path=args.task_manifest
        )
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        parser.exit(1, f"ORIGINAL MAIN-STUDY TASKS: FAIL: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
