import asyncio
import hashlib
import json

import pytest

from scripts import run_budget_main_study


def _valid_payload() -> dict:
    return {
        "task_set_id": "main-budget-v1-test",
        "tasks": [
            {
                "id": "main-01",
                "category": "technical_comparison",
                "question": "What does the synthetic evidence show?",
            }
        ],
    }


def _write_payload(path, payload) -> bytes:
    raw = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def test_task_loader_binds_validated_tasks_to_exact_file_snapshot(tmp_path):
    task_file = tmp_path / "tasks.json"
    raw = _write_payload(task_file, _valid_payload())

    task_set_id, tasks, snapshot = run_budget_main_study._load_task_file(task_file)

    assert task_set_id == "main-budget-v1-test"
    assert tasks == _valid_payload()["tasks"]
    assert snapshot == {
        "path": str(task_file.resolve()),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([{"tasks": []}], "top level must be an object"),
        ({"task_set_id": " ", "tasks": [{}]}, "task_set_id must be a non-empty string"),
        ({"task_set_id": "test", "tasks": "main-01"}, "tasks must be a non-empty list"),
        ({"task_set_id": "test", "tasks": ["main-01"]}, "task 1 must be an object"),
        (
            {
                "task_set_id": "test",
                "tasks": [
                    {"id": "../main-01", "category": "test", "question": "Question?"}
                ],
            },
            "task 1 id must be a safe non-empty identifier",
        ),
        (
            {
                "task_set_id": "test",
                "tasks": [
                    {"id": "main-01", "category": "test", "question": "Question?"},
                    {"id": "main-01", "category": "test", "question": "Other?"},
                ],
            },
            "duplicate task id: main-01",
        ),
        (
            {
                "task_set_id": "test",
                "tasks": [{"id": "main-01", "category": " ", "question": "Question?"}],
            },
            "task 1 category must be a non-empty string",
        ),
        (
            {
                "task_set_id": "test",
                "tasks": [{"id": "main-01", "category": "test", "question": " "}],
            },
            "task 1 question must be a non-empty string",
        ),
    ],
)
def test_task_loader_rejects_malformed_or_ambiguous_tasks(tmp_path, payload, message):
    task_file = tmp_path / "tasks.json"
    _write_payload(task_file, payload)

    with pytest.raises(SystemExit, match=message):
        run_budget_main_study._load_task_file(task_file)


def test_task_loader_rejects_duplicate_json_keys(tmp_path):
    task_file = tmp_path / "tasks.json"
    task_file.write_text(
        '{"task_set_id":"test","tasks":[{"id":"main-01",'
        '"category":"test","question":"first","question":"second"}]}',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="duplicate JSON key: question"):
        run_budget_main_study._load_task_file(task_file)


def test_main_study_manifest_records_task_snapshot_before_execution(tmp_path, monkeypatch):
    task_file = tmp_path / "tasks.json"
    raw = _write_payload(task_file, _valid_payload())
    pricing_file = tmp_path / "experiments" / "pricing.json"
    pricing_file.parent.mkdir()
    pricing_file.write_text(
        json.dumps(
            {
                "unit": "per_1m_text_tokens",
                "models": {
                    "test-smart": {"input": 1.0, "output": 2.0},
                    "test-fast": {"input": 0.5, "output": 1.0},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_budget_main_study, "PRICING_FILE", pricing_file)
    monkeypatch.setattr(
        run_budget_main_study,
        "TRACE_ROOT",
        tmp_path / "outputs" / "experiment_traces",
    )
    monkeypatch.setattr(
        run_budget_main_study.sys,
        "argv",
        ["run_budget_main_study.py", f"--task-file={task_file}"],
    )
    for name, value in {
        "OPENAI_API_KEY": "test-key",
        "SMART_LLM_MODEL": "test-smart",
        "FAST_LLM_MODEL": "test-fast",
        "TEMPERATURE": "1",
    }.items():
        monkeypatch.setenv(name, value)

    async def fake_run_agent(**_kwargs):
        return None

    monkeypatch.setattr("logic.run.run_agent", fake_run_agent)

    asyncio.run(run_budget_main_study.main())

    manifest = json.loads(
        (tmp_path / "outputs" / "main_study_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["task_file"] == "tasks.json"
    assert manifest["task_file_size_bytes"] == len(raw)
    assert manifest["task_file_sha256"] == hashlib.sha256(raw).hexdigest()
