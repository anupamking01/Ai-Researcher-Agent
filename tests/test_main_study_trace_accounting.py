import asyncio
import builtins
import json

import pytest

from scripts import run_budget_main_study


PRICING = {
    "models": {
        "test-smart": {"input": 1.0, "output": 2.0},
        "test-fast": {"input": 0.5, "output": 1.0},
    }
}


def _usage_bucket(**overrides) -> dict:
    bucket = {
        "model_calls": 1,
        "unavailable_calls": 0,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
    bucket.update(overrides)
    return bucket


def _trace_payload(**trace_overrides) -> dict:
    usage = {
        "test-smart": _usage_bucket(),
        "test-fast": _usage_bucket(
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
        ),
    }
    trace = {
        "run_id": "run-1",
        "variant_id": "D3",
        "task_id": "main-01",
        "model_call_count": 2,
        "unavailable_usage_call_count": 0,
        "prompt_tokens": 150,
        "completion_tokens": 30,
        "total_tokens": 180,
        "usage_accounting_status": "provider_usage_complete",
        "provider_usage_by_model": usage,
    }
    trace.update(trace_overrides)
    return {
        "schema_version": 2,
        "experiment": {"variant_id": "D3", "task_id": "main-01"},
        "trace": trace,
    }


def _write_trace(tmp_path, payload=None):
    path = tmp_path / "D3" / "run-1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or _trace_payload()), encoding="utf-8")
    return path


def test_trace_cost_accepts_conserved_complete_provider_ledger(tmp_path):
    path = _write_trace(tmp_path)

    cost = run_budget_main_study._trace_cost_usd(path, PRICING)

    assert cost == pytest.approx(0.000175)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.update(schema_version=True), "schema_version must equal 2"),
        (lambda payload: payload.update(trace=[]), "experiment and trace must be objects"),
        (
            lambda payload: payload["trace"].update(variant_id="D6"),
            "variant_id identity mismatch",
        ),
        (
            lambda payload: payload["trace"].update(run_id="other-run"),
            "run_id must match filename",
        ),
        (
            lambda payload: payload["trace"].update(
                usage_accounting_status="provider_usage_partial"
            ),
            "usage_accounting_status must equal provider_usage_complete",
        ),
        (
            lambda payload: payload["trace"].update(provider_usage_by_model=[]),
            "provider_usage_by_model must be a non-empty object",
        ),
        (
            lambda payload: payload["trace"]["provider_usage_by_model"].update(
                {"unknown-model": _usage_bucket()}
            ),
            "has no frozen price",
        ),
        (
            lambda payload: payload["trace"]["provider_usage_by_model"][
                "test-smart"
            ].update(prompt_tokens=True),
            "prompt_tokens must be a non-negative integer",
        ),
        (
            lambda payload: payload["trace"]["provider_usage_by_model"][
                "test-smart"
            ].update(completion_tokens=1.5),
            "completion_tokens must be a non-negative integer",
        ),
        (
            lambda payload: payload["trace"]["provider_usage_by_model"][
                "test-smart"
            ].update(unavailable_calls=1),
            "requires zero unavailable calls",
        ),
        (
            lambda payload: payload["trace"]["provider_usage_by_model"][
                "test-smart"
            ].update(total_tokens=999),
            r"total_tokens must equal prompt_tokens \+ completion_tokens",
        ),
        (
            lambda payload: payload["trace"].update(prompt_tokens=149),
            "aggregate token ledger mismatch",
        ),
        (
            lambda payload: payload["trace"].update(model_call_count=3),
            "aggregate call ledger mismatch",
        ),
    ],
)
def test_trace_cost_rejects_malformed_or_contradictory_ledgers(
    tmp_path, mutate, message
):
    payload = _trace_payload()
    mutate(payload)
    path = _write_trace(tmp_path, payload)

    with pytest.raises(SystemExit, match=message):
        run_budget_main_study._trace_cost_usd(path, PRICING)


def test_trace_cost_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "D3" / "run-1.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version":2,"experiment":{"variant_id":"D3",'
        '"task_id":"main-01"},"trace":{"run_id":"run-1",'
        '"variant_id":"D3","variant_id":"D6","task_id":"main-01"}}',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="duplicate JSON key: variant_id"):
        run_budget_main_study._trace_cost_usd(path, PRICING)


def test_current_treatment_cost_rejects_dangling_trace_root_symlink(
    tmp_path, monkeypatch
):
    trace_root = tmp_path / "traces"
    trace_root.symlink_to(tmp_path / "missing", target_is_directory=True)
    monkeypatch.setattr(run_budget_main_study, "TRACE_ROOT", trace_root)

    with pytest.raises(SystemExit, match="Invalid treatment trace root"):
        run_budget_main_study._current_treatment_cost(PRICING)


def test_current_treatment_cost_rejects_symlinked_variant_directory(
    tmp_path, monkeypatch
):
    outside_variant = tmp_path / "outside" / "D3"
    outside_variant.mkdir(parents=True)
    trace_root = tmp_path / "traces"
    trace_root.mkdir()
    (trace_root / "D3").symlink_to(
        outside_variant,
        target_is_directory=True,
    )
    monkeypatch.setattr(run_budget_main_study, "TRACE_ROOT", trace_root)

    with pytest.raises(SystemExit, match="Invalid treatment trace directory"):
        run_budget_main_study._current_treatment_cost(PRICING)


@pytest.mark.parametrize("aggregate_field", ["prompt_tokens", "model_call_count"])
def test_trace_cost_rejects_boolean_aggregate_ledger_values(
    tmp_path, aggregate_field
):
    payload = _trace_payload()
    payload["trace"]["provider_usage_by_model"] = {
        "test-smart": _usage_bucket(
            model_calls=1,
            prompt_tokens=1,
            completion_tokens=0,
            total_tokens=1,
        )
    }
    payload["trace"].update(
        model_call_count=1,
        prompt_tokens=1,
        completion_tokens=0,
        total_tokens=1,
    )
    payload["trace"][aggregate_field] = True
    path = _write_trace(tmp_path, payload)

    with pytest.raises(SystemExit, match="aggregate .* ledger mismatch"):
        run_budget_main_study._trace_cost_usd(path, PRICING)


def _write_main_inputs(tmp_path):
    task_file = tmp_path / "tasks.json"
    task_file.write_text(
        json.dumps(
            {
                "task_set_id": "main-budget-v1-test",
                "tasks": [
                    {
                        "id": "main-01",
                        "category": "test",
                        "question": "What does the evidence show?",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pricing_file = tmp_path / "experiments" / "pricing.json"
    pricing_file.parent.mkdir()
    pricing_file.write_text(
        json.dumps({"unit": "per_1m_text_tokens", **PRICING}),
        encoding="utf-8",
    )
    return task_file, pricing_file


def test_invalid_trace_ledger_fails_before_outputs_and_model_imports(
    tmp_path, monkeypatch
):
    task_file, pricing_file = _write_main_inputs(tmp_path)
    trace_root = tmp_path / "existing-traces"
    payload = _trace_payload(prompt_tokens=-1)
    _write_trace(trace_root, payload)

    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_budget_main_study, "PRICING_FILE", pricing_file)
    monkeypatch.setattr(run_budget_main_study, "TRACE_ROOT", trace_root)
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
            raise AssertionError(f"model module imported before trace preflight: {name}")
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as import_patch:
        import_patch.setattr(builtins, "__import__", fail_if_model_module_imported)
        with pytest.raises(SystemExit, match="aggregate token ledger mismatch"):
            asyncio.run(run_budget_main_study.main())

    assert imported == []
    assert not (tmp_path / "outputs").exists()

