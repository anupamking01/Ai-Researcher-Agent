"""Offline regression tests for cross-invocation diagnostic-pilot custody.

Tests use only temporary synthetic files and never call the provider/agent.
"""

import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from scripts import run_pilot


def test_missing_or_empty_output_workspace_is_accepted(tmp_path):
    root = tmp_path / "outputs"
    run_pilot._require_fresh_pilot_workspace(root)
    assert not root.exists()  # Read-only preflight, not a workspace creator.
    root.mkdir()
    run_pilot._require_fresh_pilot_workspace(root)


@pytest.mark.parametrize(
    "artifact",
    [
        "pilot_manifest.json",
        "pilot_progress.json",
        "pilot_summary.json",
        "pilot_runs.csv",
        "experiment_traces/D6/prior-run.json",
        "prior-report/research_report.md",
        "prior-report/verification.json",
        "unrecognized-artifact.txt",
    ],
)
def test_existing_workspace_artifact_is_preserved_and_rejected(tmp_path, artifact):
    root = tmp_path / "outputs"
    file = root / artifact
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"prior research evidence - do not replace")
    with pytest.raises(ValueError, match="not empty"):
        run_pilot._require_fresh_pilot_workspace(root)
    assert file.read_bytes() == b"prior research evidence - do not replace"


def test_preexisting_empty_trace_directory_is_not_treated_as_fresh(tmp_path):
    root = tmp_path / "outputs"
    (root / "experiment_traces").mkdir(parents=True)
    with pytest.raises(ValueError, match="not empty"):
        run_pilot._require_fresh_pilot_workspace(root)


def test_non_directory_output_root_is_rejected(tmp_path):
    root = tmp_path / "outputs"
    root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a directory"):
        run_pilot._require_fresh_pilot_workspace(root)
    assert root.read_text(encoding="utf-8") == "not a directory"


def test_symlinked_output_root_is_rejected_even_when_target_is_empty(tmp_path):
    target = tmp_path / "old-outputs"
    target.mkdir()
    root = tmp_path / "outputs"
    root.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="must not be a symlink"):
        run_pilot._require_fresh_pilot_workspace(root)


def test_main_rejects_occupied_workspace_before_credentials_or_model_import(
    tmp_path, monkeypatch
):
    task_file = tmp_path / "pilot.json"
    task_file.write_text(json.dumps({
        "task_set_id": "synthetic-pilot",
        "tasks": [{"id": "task-01", "question": "Synthetic question?"}],
    }), encoding="utf-8")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    sentinel = output_root / "pilot_manifest.json"
    sentinel.write_bytes(b"unchanged prior manifest")

    monkeypatch.setattr(run_pilot, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "run_pilot.py", "--task-file", str(task_file), "--variants", "D6"
    ])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="workspace is not empty"):
        asyncio.run(run_pilot.main())
    assert sentinel.read_bytes() == b"unchanged prior manifest"
    assert not (output_root / "pilot_progress.json").exists()


def test_manifest_publication_is_create_only_even_after_preflight_race(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_pilot, "REPO_ROOT", tmp_path)
    for name, value in (
        ("SMART_LLM_MODEL", "synthetic-smart"),
        ("FAST_LLM_MODEL", "synthetic-fast"),
        ("TEMPERATURE", "1"),
    ):
        monkeypatch.setenv(name, value)
    config = SimpleNamespace(
        browse_timeout_seconds=60.0,
        run_timeout_seconds=480.0,
        max_concurrent_browses=2,
    )
    manifest_path = run_pilot._write_manifest(
        "synthetic-pilot", [{"id": "task-01"}], ["D6"], config
    )
    before = manifest_path.read_bytes()
    assert json.loads(before)["task_ids"] == ["task-01"]
    with pytest.raises(SystemExit, match="manifest already exists"):
        run_pilot._write_manifest(
            "synthetic-pilot", [{"id": "task-02"}], ["P6"], config
        )
    assert manifest_path.read_bytes() == before
