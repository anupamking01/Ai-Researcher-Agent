"""Offline launch-preflight regressions; no agent, provider, or treatment calls."""

import asyncio
import json
import sys

import pytest

from scripts import run_pilot


GOOD = {
    "task_set_id": "synthetic-pilot",
    "tasks": [{"id": "pilot-01", "question": "Synthetic diagnostic task?"}],
}


def _write(tmp_path, raw):
    path = tmp_path / "tasks.json"
    path.write_text(raw, encoding="utf-8")
    return path


def test_original_frozen_five_task_manifest_parses_without_rewriting():
    source = run_pilot.REPO_ROOT / "experiments" / "pilot_tasks.json"
    before = source.read_bytes()
    study_id, tasks = run_pilot._load_tasks(source)
    assert study_id == "pilot-v1-2026-09-08"
    assert len(tasks) == 5
    assert source.read_bytes() == before


def test_valid_synthetic_manifest_preserves_all_task_fields(tmp_path):
    path = _write(tmp_path, json.dumps(GOOD))
    assert run_pilot._load_tasks(path) == (GOOD["task_set_id"], GOOD["tasks"])


@pytest.mark.parametrize("raw", [
    '{"task_set_id":"earlier","task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?"}]}',
    '{"task_set_id":"synthetic-pilot","tasks":[],"tasks":[{"id":"pilot-01","question":"Q?"}]}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"other","id":"pilot-01","question":"Q?"}]}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Earlier?","question":"Later?"}]}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?","unused":{"x":1,"x":2}}]}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?"}],"unused":{"x":1,"x":2}}',
])
def test_duplicate_json_keys_anywhere_rejected_before_selection(tmp_path, raw):
    path = _write(tmp_path, raw)
    with pytest.raises(ValueError, match="invalid pilot task manifest.*duplicate JSON key"):
        run_pilot._load_tasks(path)


@pytest.mark.parametrize("raw", [
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?"}],"unused":NaN}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?"}],"unused":Infinity}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?"}],"unused":-Infinity}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?","weight":1e309}]}',
    '{"task_set_id":"synthetic-pilot","tasks":[{"id":"pilot-01","question":"Q?"}],"unused":-1e309}',
])
def test_nonfinite_manifest_numbers_are_rejected_even_if_unused(tmp_path, raw):
    path = _write(tmp_path, raw)
    with pytest.raises(ValueError, match="invalid pilot task manifest"):
        run_pilot._load_tasks(path)


@pytest.mark.parametrize("raw", ["[1,2]", '{"task_set_id":', "{}", ""])
def test_non_object_malformed_or_missing_task_plan_does_not_pass(tmp_path, raw):
    path = _write(tmp_path, raw)
    with pytest.raises(ValueError):
        run_pilot._load_tasks(path)


def test_invalid_utf8_task_source_is_diagnostic(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_bytes(bytes([0xff, 0xfe]))
    with pytest.raises(ValueError, match="invalid pilot task manifest"):
        run_pilot._load_tasks(path)


def test_invalid_source_aborts_main_before_credentials_or_artifacts(tmp_path, monkeypatch):
    task_file = _write(tmp_path, (
        '{"task_set_id":"wrong","task_set_id":"synthetic-pilot",'
        '"tasks":[{"id":"pilot-01","question":"Q?"}]}'
    ))
    monkeypatch.setattr(run_pilot, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "run_pilot.py", "--task-file", str(task_file), "--variants", "D6"
    ])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="Pilot aborted: invalid pilot task manifest"):
        asyncio.run(run_pilot.main())
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("bad", [
    "NaN", "nan", "Infinity", "-Infinity", "inf", "-inf", "1e309", "-1e309",
    "not-a-number",
])
def test_nonfinite_or_invalid_temperature_rejected_before_manifest(
    monkeypatch, bad
):
    for name, value in (
        ("OPENAI_API_KEY", "synthetic-key"),
        ("SMART_LLM_MODEL", "synthetic-smart"),
        ("FAST_LLM_MODEL", "synthetic-fast"),
        ("TEMPERATURE", bad),
    ):
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit, match="TEMPERATURE must be a finite numeric value"):
        run_pilot._check_environment()


@pytest.mark.parametrize("valid", ["0", "1", "1.0", "0.5", "1e-2"])
def test_finite_temperature_remains_supported(monkeypatch, valid):
    for name, value in (
        ("OPENAI_API_KEY", "synthetic-key"),
        ("SMART_LLM_MODEL", "synthetic-smart"),
        ("FAST_LLM_MODEL", "synthetic-fast"),
        ("TEMPERATURE", valid),
    ):
        monkeypatch.setenv(name, value)
    run_pilot._check_environment()
