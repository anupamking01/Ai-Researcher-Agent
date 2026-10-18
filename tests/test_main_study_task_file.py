import asyncio
import hashlib
import json
import subprocess
import sys
import types
from dataclasses import dataclass

import pytest

from scripts import run_budget_main_study


def _git(*args, cwd):
    return subprocess.check_output(
        ["git", *args],
        cwd=cwd,
        text=True,
    ).strip()


def _initialize_git_repository(path):
    _git("init", "-q", cwd=path)
    _git("config", "user.email", "research-test@example.invalid", cwd=path)
    _git("config", "user.name", "Research Test", cwd=path)
    source = path / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _git("add", "source.py", cwd=path)
    _git("commit", "-q", "-m", "test fixture", cwd=path)
    return source


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


def test_git_source_state_records_exact_clean_commit_and_tree(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    assert run_budget_main_study._git_source_state() == {
        "commit": _git("rev-parse", "HEAD", cwd=tmp_path),
        "tree": _git("rev-parse", "HEAD^{tree}", cwd=tmp_path),
    }


def test_git_source_state_rejects_dirty_worktree(tmp_path, monkeypatch):
    source = _initialize_git_repository(tmp_path)
    source.write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Git working tree is not clean"):
        run_budget_main_study._git_source_state()


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_git_source_state_rejects_hidden_tracked_changes(
    tmp_path, monkeypatch, index_flag
):
    source = _initialize_git_repository(tmp_path)
    _git("update-index", index_flag, "source.py", cwd=tmp_path)
    source.write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Git index hides tracked source state"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_nonignored_untracked_files(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    (tmp_path / "untracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Git working tree is not clean"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_unversioned_source_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Cannot record Git source state"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_ancestor_repository(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    nested_root = tmp_path / "copied-project"
    nested_root.mkdir()
    (nested_root / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git("add", "copied-project/runner.py", cwd=tmp_path)
    _git("commit", "-q", "-m", "add copied project", cwd=tmp_path)
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", nested_root)

    with pytest.raises(SystemExit, match="Git repository root does not match"):
        run_budget_main_study._git_source_state()


def test_execution_environment_records_normalized_sorted_distributions(monkeypatch):
    distributions = [
        types.SimpleNamespace(metadata={"Name": "Zeta_Package"}, version="2.0"),
        types.SimpleNamespace(metadata={"Name": "alpha.package"}, version="1.0"),
        types.SimpleNamespace(metadata={"Name": "Alpha-Package"}, version="1.0"),
    ]
    monkeypatch.setattr(
        run_budget_main_study,
        "importlib",
        types.SimpleNamespace(
            metadata=types.SimpleNamespace(distributions=lambda: distributions)
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "SyntheticPython",
            python_version=lambda: "3.11.99",
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )

    assert run_budget_main_study._execution_environment() == {
        "python_implementation": "SyntheticPython",
        "python_version": "3.11.99",
        "platform": "synthetic-runner",
        "installed_distributions": [
            {"name": "alpha-package", "version": "1.0"},
            {"name": "alpha-package", "version": "1.0"},
            {"name": "zeta-package", "version": "2.0"},
        ],
    }


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
    expected_environment = {
        "python_implementation": "SyntheticPython",
        "python_version": "3.11.99",
        "platform": "synthetic-runner",
        "installed_distributions": [
            {"name": "example-package", "version": "1.2.3"},
        ],
    }
    monkeypatch.setattr(
        run_budget_main_study,
        "_execution_environment",
        lambda: expected_environment,
        raising=False,
    )
    expected_source_state = {
        "commit": "1" * 40,
        "tree": "2" * 40,
    }
    monkeypatch.setattr(
        run_budget_main_study,
        "_git_source_state",
        lambda: expected_source_state,
    )
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

    @dataclass(frozen=True)
    class FakeConfig:
        browse_timeout_seconds: int = 1
        run_timeout_seconds: int = 2
        max_concurrent_browses: int = 3
        task_set_id: str = ""
        task_id: str = ""

    class FakeExperimentConfig:
        @classmethod
        def from_variant(cls, _variant):
            return FakeConfig()

    async def fake_run_agent(**_kwargs):
        return None

    experiment_module = types.ModuleType("logic.experiment")
    experiment_module.ExperimentConfig = FakeExperimentConfig
    run_module = types.ModuleType("logic.run")
    run_module.run_agent = fake_run_agent
    monkeypatch.setitem(sys.modules, "logic.experiment", experiment_module)
    monkeypatch.setitem(sys.modules, "logic.run", run_module)

    asyncio.run(run_budget_main_study.main())

    manifest = json.loads(
        (tmp_path / "outputs" / "main_study_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["task_file"] == "tasks.json"
    assert manifest["task_file_size_bytes"] == len(raw)
    assert manifest["task_file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["execution_environment"] == expected_environment
    assert manifest["git_commit"] == expected_source_state["commit"]
    assert manifest["git_tree"] == expected_source_state["tree"]


def test_main_study_rejects_source_drift_while_loading_treatment_code(
    tmp_path, monkeypatch
):
    task_file = tmp_path / "tasks.json"
    _write_payload(task_file, _valid_payload())
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
        run_budget_main_study,
        "_execution_environment",
        lambda: {
            "python_implementation": "SyntheticPython",
            "python_version": "3.11.99",
            "platform": "synthetic-runner",
            "installed_distributions": [],
        },
    )
    source_states = iter(
        [
            {"commit": "1" * 40, "tree": "2" * 40},
            {"commit": "1" * 40, "tree": "3" * 40},
        ]
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_git_source_state",
        lambda: next(source_states),
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

    @dataclass(frozen=True)
    class FakeConfig:
        browse_timeout_seconds: int = 1
        run_timeout_seconds: int = 2
        max_concurrent_browses: int = 3
        task_set_id: str = ""
        task_id: str = ""

    class FakeExperimentConfig:
        @classmethod
        def from_variant(cls, _variant):
            return FakeConfig()

    model_calls = []

    async def fake_run_agent(**kwargs):
        model_calls.append(kwargs)

    experiment_module = types.ModuleType("logic.experiment")
    experiment_module.ExperimentConfig = FakeExperimentConfig
    run_module = types.ModuleType("logic.run")
    run_module.run_agent = fake_run_agent
    monkeypatch.setitem(sys.modules, "logic.experiment", experiment_module)
    monkeypatch.setitem(sys.modules, "logic.run", run_module)

    with pytest.raises(SystemExit, match="source state changed"):
        asyncio.run(run_budget_main_study.main())

    assert model_calls == []
    assert not (tmp_path / "outputs" / "main_study_manifest.json").exists()
