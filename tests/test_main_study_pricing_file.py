import asyncio
import builtins
import hashlib
import json
import sys
import types
from dataclasses import dataclass

import pytest

from scripts import run_budget_main_study


def _valid_pricing() -> dict:
    return {
        "effective_date": "2026-09-08",
        "currency": "USD",
        "unit": "per_1m_text_tokens",
        "source": "Test pricing snapshot",
        "models": {
            "test-smart": {
                "input": 1.0,
                "cached_input": 0.1,
                "output": 2.0,
            },
            "test-fast": {
                "input": 0.5,
                "output": 1.0,
            },
        },
    }


def _write_json(path, payload) -> bytes:
    raw = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _write_tasks(path) -> None:
    _write_json(
        path,
        {
            "task_set_id": "main-budget-v1-test",
            "tasks": [
                {
                    "id": "main-01",
                    "category": "test",
                    "question": "What does the evidence show?",
                }
            ],
        },
    )


def test_pricing_loader_binds_validated_rates_to_exact_file_snapshot(tmp_path):
    pricing_file = tmp_path / "pricing.json"
    raw = _write_json(pricing_file, _valid_pricing())

    pricing, snapshot = run_budget_main_study._load_pricing(pricing_file)

    assert pricing == _valid_pricing()
    assert snapshot == {
        "path": str(pricing_file.resolve()),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "top level must be an object"),
        ({"unit": "per_token", "models": {"model": {"input": 1, "output": 2}}},
         "unit must equal per_1m_text_tokens"),
        ({"unit": "per_1m_text_tokens", "models": {}},
         "models must be a non-empty object"),
        ({"unit": "per_1m_text_tokens", "models": {" ": {"input": 1, "output": 2}}},
         "model name must be a non-empty string without surrounding whitespace"),
        ({"unit": "per_1m_text_tokens", "models": {"model": []}},
         "model model must be an object"),
        ({"unit": "per_1m_text_tokens", "models": {"model": {"output": 2}}},
         "model model input must be a finite non-negative number"),
        ({"unit": "per_1m_text_tokens", "models": {"model": {"input": 1, "output": True}}},
         "model model output must be a finite non-negative number"),
        ({"unit": "per_1m_text_tokens", "models": {"model": {"input": -1, "output": 2}}},
         "model model input must be a finite non-negative number"),
        ({"unit": "per_1m_text_tokens", "models": {"model": {"input": 1, "output": float("inf")}}},
         "model model output must be a finite non-negative number"),
        ({"unit": "per_1m_text_tokens", "models": {"model": {"input": 1, "output": 2, "cached_input": float("nan")}}},
         "model model cached_input must be a finite non-negative number"),
    ],
)
def test_pricing_loader_rejects_malformed_or_unusable_rates(
    tmp_path, payload, message
):
    pricing_file = tmp_path / "pricing.json"
    _write_json(pricing_file, payload)

    with pytest.raises(SystemExit, match=message):
        run_budget_main_study._load_pricing(pricing_file)


def test_pricing_loader_rejects_duplicate_json_keys(tmp_path):
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(
        '{"unit":"per_1m_text_tokens","models":{"model":'
        '{"input":1,"input":2,"output":3}}}',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="duplicate JSON key: input"):
        run_budget_main_study._load_pricing(pricing_file)


def test_main_study_manifest_records_pricing_snapshot_before_execution(
    tmp_path, monkeypatch
):
    task_file = tmp_path / "tasks.json"
    _write_tasks(task_file)
    pricing_file = tmp_path / "experiments" / "pricing.json"
    raw = _write_json(pricing_file, _valid_pricing())

    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_budget_main_study, "PRICING_FILE", pricing_file)
    monkeypatch.setattr(
        run_budget_main_study,
        "_execution_environment",
        lambda: {
            "python_implementation": "SyntheticPython",
            "python_version_pin": "3.11",
            "python_version": "3.11.99",
            "platform": "synthetic-runner",
            "installed_distributions": [],
        },
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_git_source_state",
        lambda: {"commit": "1" * 40, "tree": "2" * 40},
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
    assert manifest["pricing_file"] == "experiments/pricing.json"
    assert manifest["pricing_file_size_bytes"] == len(raw)
    assert manifest["pricing_file_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    ("pricing_payload", "message"),
    [
        (
            {"unit": "per_1m_text_tokens", "models": {}},
            "models must be a non-empty object",
        ),
        (
            {
                "unit": "per_1m_text_tokens",
                "models": {"other-model": {"input": 1.0, "output": 2.0}},
            },
            "has no rate for SMART_LLM_MODEL=test-smart",
        ),
    ],
)
def test_invalid_pricing_fails_before_outputs_and_model_imports(
    tmp_path, monkeypatch, pricing_payload, message
):
    task_file = tmp_path / "tasks.json"
    _write_tasks(task_file)
    pricing_file = tmp_path / "experiments" / "pricing.json"
    _write_json(pricing_file, pricing_payload)

    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_budget_main_study, "PRICING_FILE", pricing_file)
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

    imported = []
    real_import = builtins.__import__

    def fail_if_model_module_imported(name, *args, **kwargs):
        if name in {"logic.experiment", "logic.run"}:
            imported.append(name)
            raise AssertionError(f"model module imported before pricing preflight: {name}")
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as import_patch:
        import_patch.setattr(builtins, "__import__", fail_if_model_module_imported)
        with pytest.raises(SystemExit, match=message):
            asyncio.run(run_budget_main_study.main())

    assert imported == []
    assert not (tmp_path / "outputs").exists()

