"""Offline original-run task-list anchor regression tests (no treatment reruns)."""
from pathlib import Path

import pytest

from scripts import verify_frozen_main_study_tasks as tasks
from scripts import audit_human_eval_archive_readiness as audit


def _original_bytes() -> bytes:
    return (tasks.ROOT / tasks.TASK_MANIFEST_REL).read_bytes()


def test_original_study_run_task_snapshot_is_unchanged():
    receipt = tasks.verify_frozen_task_manifest()
    assert receipt["status"] == "original_treatment_run_task_manifest_matches"
    assert receipt["original_treatment_commit"] == tasks.ORIGINAL_TREATMENT_COMMIT
    assert receipt["original_task_manifest_sha256"] == tasks.ORIGINAL_TASK_MANIFEST_SHA256
    assert receipt["n_tasks"] == 10
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("alter", [
    lambda raw: raw.replace(b"main-01", b"main-XX", 1),
    lambda raw: raw + b"\n",
])
def test_coherent_task_rewrite_or_reformat_is_not_original_source(
    tmp_path: Path, alter
):
    path = tmp_path / "main_budget_tasks.json"
    original = _original_bytes()
    changed = alter(original)
    assert changed != original
    path.write_bytes(changed)
    with pytest.raises(ValueError, match="differs from the original"):
        tasks.verify_frozen_task_manifest(task_manifest_path=path)


def test_missing_and_symlinked_task_sources_fail_closed(tmp_path: Path):
    path = tmp_path / "main_budget_tasks.json"
    with pytest.raises((OSError, ValueError)):
        tasks.verify_frozen_task_manifest(task_manifest_path=path)
    target = tmp_path / "unrelated.json"
    target.write_bytes(_original_bytes())
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink support unavailable")
    with pytest.raises((OSError, ValueError)):
        tasks.verify_frozen_task_manifest(task_manifest_path=path)


def test_archive_readiness_never_conflates_original_task_drift_with_alignment(
    tmp_path: Path, monkeypatch
):
    # Synthetic, internally consistent source is still NOT the frozen study.
    task_path = tmp_path / tasks.TASK_MANIFEST_REL
    task_path.parent.mkdir(parents=True)
    task_path.write_text('{"task_set_id":"synthetic","tasks":[]}', encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["frozen_task_manifest_anchor"] == "verification_failed_or_missing"
    assert "original_experiment_task_manifest_anchor" in result["blockers"]
    assert result["status"] == "blocked"
    assert result["handoff_verified"] is False
