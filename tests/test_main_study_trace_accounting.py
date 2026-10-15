import asyncio
import builtins
import json
import os
import stat

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
        "completed": True,
        "source_budget": 3,
        "source_count": 2,
        "successful_source_count": 1,
        "failed_source_count": 1,
        "query_count": 1,
        "search_call_count": 1,
        "scheduled_urls": ["https://example.test/a", "https://example.test/b"],
        "successful_urls": ["https://example.test/a"],
        "failed_urls": ["https://example.test/b"],
        "latency_seconds": 1.25,
        "report_words": 100,
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
        "experiment": {
            "variant_id": "D3",
            "task_id": "main-01",
            "source_budget": 3,
        },
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


def test_trace_cost_accepts_failed_run_with_unclassified_scheduled_urls(tmp_path):
    payload = _trace_payload(
        completed=False,
        source_count=2,
        successful_source_count=0,
        failed_source_count=0,
        scheduled_urls=["https://example.test/a", "https://example.test/b"],
        successful_urls=[],
        failed_urls=[],
        report_words=0,
    )
    path = _write_trace(tmp_path, payload)

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


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["trace"].update(completed=1),
            "completed must be a boolean",
        ),
        (
            lambda payload: payload["trace"].update(source_budget=4),
            "source_budget must match experiment",
        ),
        (
            lambda payload: (
                payload["experiment"].update(source_budget=6),
                payload["trace"].update(source_budget=6),
            ),
            "source_budget must match frozen variant",
        ),
        (
            lambda payload: payload["trace"].update(source_count=4),
            "source_count must not exceed source_budget",
        ),
        (
            lambda payload: payload["trace"].update(successful_source_count=2),
            "source count ledger mismatch",
        ),
        (
            lambda payload: payload["trace"].update(scheduled_urls=[]),
            "source URL ledger mismatch",
        ),
        (
            lambda payload: payload["trace"].update(search_call_count=2),
            "search_call_count must not exceed query_count",
        ),
        (
            lambda payload: payload["trace"].update(latency_seconds=float("nan")),
            "latency_seconds must be a finite non-negative number",
        ),
        (
            lambda payload: payload["trace"].update(report_words=0),
            "completed trace must have positive report_words",
        ),
    ],
)
def test_trace_cost_rejects_invalid_operational_measurements(
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


def _configure_main(tmp_path, monkeypatch):
    task_file, pricing_file = _write_main_inputs(tmp_path)
    trace_root = tmp_path / "outputs" / "experiment_traces"
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
    return trace_root


@pytest.mark.parametrize(
    "state_name",
    ["main_study_manifest.json", "main_study_progress.json"],
)
def test_existing_main_study_state_blocks_before_model_imports_or_overwrite(
    tmp_path, monkeypatch, state_name
):
    _configure_main(tmp_path, monkeypatch)
    state_path = tmp_path / "outputs" / state_name
    state_path.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"preserved":true}\n'
    state_path.write_bytes(original)

    imported = []
    real_import = builtins.__import__

    def fail_if_model_module_imported(name, *args, **kwargs):
        if name in {"logic.experiment", "logic.run"}:
            imported.append(name)
            raise AssertionError(f"model module imported with existing state: {name}")
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as import_patch:
        import_patch.setattr(builtins, "__import__", fail_if_model_module_imported)
        with pytest.raises(SystemExit, match="Refusing to overwrite existing main-study state"):
            asyncio.run(run_budget_main_study.main())

    assert imported == []
    assert state_path.read_bytes() == original


def test_existing_treatment_trace_blocks_rerun_before_model_imports(
    tmp_path, monkeypatch
):
    trace_root = _configure_main(tmp_path, monkeypatch)
    _write_trace(trace_root)

    imported = []
    real_import = builtins.__import__

    def fail_if_model_module_imported(name, *args, **kwargs):
        if name in {"logic.experiment", "logic.run"}:
            imported.append(name)
            raise AssertionError(f"model module imported before rerun gate: {name}")
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as import_patch:
        import_patch.setattr(builtins, "__import__", fail_if_model_module_imported)
        with pytest.raises(SystemExit, match="Refusing to rerun treatments: 1 existing trace"):
            asyncio.run(run_budget_main_study.main())

    assert imported == []
    assert not (tmp_path / "outputs" / "main_study_manifest.json").exists()
    assert not (tmp_path / "outputs" / "main_study_progress.json").exists()


def test_symlinked_outputs_root_blocks_before_model_imports(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "outputs").symlink_to(outside, target_is_directory=True)
    _configure_main(tmp_path, monkeypatch)

    imported = []
    real_import = builtins.__import__

    def fail_if_model_module_imported(name, *args, **kwargs):
        if name in {"logic.experiment", "logic.run"}:
            imported.append(name)
            raise AssertionError(f"model module imported before output-root gate: {name}")
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as import_patch:
        import_patch.setattr(builtins, "__import__", fail_if_model_module_imported)
        with pytest.raises(SystemExit, match="Invalid main-study outputs root"):
            asyncio.run(run_budget_main_study.main())

    assert imported == []
    assert list(outside.iterdir()) == []


def test_create_only_json_write_preserves_state_published_after_preflight(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    path = tmp_path / "outputs" / "main_study_manifest.json"
    path.parent.mkdir(parents=True)
    original = b'{"winner":"other-process"}\n'
    path.write_bytes(original)

    with pytest.raises(SystemExit, match="Refusing to overwrite existing main-study state"):
        run_budget_main_study._write_json(
            "main_study_manifest.json",
            {"winner": "this-process"},
            create_only=True,
        )

    assert path.read_bytes() == original


def test_create_only_json_write_is_staged_and_durably_published(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    path = tmp_path / "outputs" / "main_study_manifest.json"
    fsync_targets = []
    real_fsync = os.fsync

    def observe_fsync(file_fd):
        mode = os.fstat(file_fd).st_mode
        fsync_targets.append("directory" if stat.S_ISDIR(mode) else "file")
        if stat.S_ISREG(mode):
            assert not path.exists()
        return real_fsync(file_fd)

    monkeypatch.setattr(run_budget_main_study.os, "fsync", observe_fsync)

    run_budget_main_study._write_json(
        "main_study_manifest.json",
        {"study": "main"},
        create_only=True,
    )

    assert fsync_targets == ["file", "directory", "directory"]
    assert json.loads(path.read_text(encoding="utf-8")) == {"study": "main"}
    assert list(path.parent.iterdir()) == [path]


def test_progress_json_write_uses_unique_staging_name(tmp_path, monkeypatch):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    path = tmp_path / "outputs" / "main_study_progress.json"
    replaced_sources = []
    real_replace = os.replace

    def observe_replace(src, dst, **kwargs):
        replaced_sources.append(src)
        assert src != "main_study_progress.json.tmp"
        return real_replace(src, dst, **kwargs)

    monkeypatch.setattr(run_budget_main_study.os, "replace", observe_replace)

    run_budget_main_study._write_json(
        "main_study_progress.json",
        {"completed_runs": 1},
    )

    assert len(replaced_sources) == 1
    assert replaced_sources[0].startswith(".main_study_progress.json.")
    assert json.loads(path.read_text(encoding="utf-8")) == {"completed_runs": 1}


def test_create_only_json_write_cleans_staging_after_sync_failure(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    path = tmp_path / "outputs" / "main_study_manifest.json"

    def fail_file_fsync(file_fd):
        if stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise OSError("simulated file sync failure")

    monkeypatch.setattr(run_budget_main_study.os, "fsync", fail_file_fsync)

    with pytest.raises(SystemExit, match="Cannot write main-study state"):
        run_budget_main_study._write_json(
            "main_study_manifest.json",
            {"study": "main"},
            create_only=True,
        )

    assert not path.exists()
    assert list(path.parent.iterdir()) == []


def test_create_only_json_write_syncs_publication_before_staging_cleanup(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    path = tmp_path / "outputs" / "main_study_manifest.json"
    directory_synced = False
    unlink_attempts = 0
    real_fsync = os.fsync
    real_unlink = os.unlink

    def observe_fsync(file_fd):
        nonlocal directory_synced
        if stat.S_ISDIR(os.fstat(file_fd).st_mode):
            directory_synced = True
        return real_fsync(file_fd)

    def fail_first_unlink(*args, **kwargs):
        nonlocal unlink_attempts
        unlink_attempts += 1
        if unlink_attempts == 1:
            assert directory_synced
            raise OSError("simulated staging cleanup failure")
        return real_unlink(*args, **kwargs)

    monkeypatch.setattr(run_budget_main_study.os, "fsync", observe_fsync)
    monkeypatch.setattr(run_budget_main_study.os, "unlink", fail_first_unlink)

    with pytest.raises(SystemExit, match="Cannot write main-study state"):
        run_budget_main_study._write_json(
            "main_study_manifest.json",
            {"study": "main"},
            create_only=True,
        )

    assert path.exists()
    assert unlink_attempts == 2
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize(
    ("name", "create_only"),
    [
        ("main_study_manifest.json", True),
        ("main_study_progress.json", False),
    ],
)
def test_json_write_rejects_outputs_root_swapped_to_symlink_after_preflight(
    tmp_path, monkeypatch, name, create_only
):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_budget_main_study,
        "TRACE_ROOT",
        tmp_path / "outputs" / "experiment_traces",
    )
    assert run_budget_main_study._preflight_new_study_state(PRICING) == 0.0

    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / name
    original = b'{"preserved":"outside"}\n'
    if not create_only:
        target.write_bytes(original)
    (tmp_path / "outputs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SystemExit, match="Invalid main-study outputs root"):
        run_budget_main_study._write_json(
            name,
            {"winner": "this-process"},
            create_only=create_only,
        )

    if create_only:
        assert not target.exists()
    else:
        assert target.read_bytes() == original


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

