"""Offline, synthetic postrun token-ledger integrity checks for diagnostic pilots.

No treatments, providers, common evaluators, or human raters are executed.
"""
import json

import pytest

from scripts.validate_pilot_artifacts import validate_pilot


def _write_cell(root, *, versioned=True):
    arm, task, run_id = "D6", "pilot-01", "run-001"
    urls = [f"https://example.invalid/{n}" for n in range(6)]
    for name, data in (
        ("pilot_manifest.json", {
            "task_set_id": "synthetic-token-ledger", "variants": [arm],
            "task_ids": [task], "smart_model": "smart",
            "fast_model": "fast", "temperature": 1.0,
        }),
        ("pilot_progress.json", {
            "task_set_id": "synthetic-token-ledger", "variants": [arm],
            "task_ids": [task], "total_expected_runs": 1,
            "attempted_runs": 1, "completed_runs": 1,
            "failed_runs": 0, "timeout_runs": 0,
        }),
        ("pilot_summary.json", {
            "n_trace_files": 1,
            "variant_summary": {arm: {"n_runs": 1, "n_completed": 1}},
        }),
    ):
        (root / name).write_text(json.dumps(data), encoding="utf-8")

    trace_path = root / "experiment_traces" / arm / f"{run_id}.json"
    trace_path.parent.mkdir(parents=True)
    trace = {
        "variant_id": arm, "task_set_id": "synthetic-token-ledger",
        "task_id": task, "run_id": run_id, "completed": True,
        "planning_mode": "direct", "verification_mode": "none",
        "source_budget": 6, "source_count": 6,
        "successful_source_count": 6, "failed_source_count": 0,
        "scheduled_urls": urls, "successful_urls": urls, "failed_urls": [],
        "query_count": 1, "search_call_count": 1,
        "research_context_words": 10, "report_words": 30,
        "model_call_count": 2, "total_tokens": 100,
        "prompt_tokens": 60, "completion_tokens": 40,
        "provider_usage_by_model": {
            "smart": {"prompt_tokens": 40, "completion_tokens": 30},
            "fast": {"prompt_tokens": 20, "completion_tokens": 10},
        },
        "usage_accounting_status": "provider_usage_complete",
        "smart_model": "smart", "fast_model": "fast", "temperature": 1.0,
        "verification_status": "not_requested",
    }
    payload = {
        "experiment": {"variant_id": arm, "task_set_id": "synthetic-token-ledger",
                       "task_id": task, "source_budget": 6},
        "trace": trace,
    }
    if versioned:
        payload["schema_version"] = 2
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    return trace_path


def _mutate(path, modify):
    payload = json.loads(path.read_text(encoding="utf-8"))
    modify(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _errors(root):
    return " | ".join(validate_pilot(root))


def test_complete_versioned_two_model_usage_accepted(tmp_path):
    _write_cell(tmp_path)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize("field,value", [
    ("prompt_tokens", 59), ("completion_tokens", 39),
    ("total_tokens", 101), ("prompt_tokens", "60"),
    ("completion_tokens", True), ("prompt_tokens", -1),
    ("prompt_tokens", None), ("completion_tokens", 40.5),
])
def test_aggregate_token_corruption_rejected(tmp_path, field, value):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"].__setitem__(field, value))
    assert ("provider token totals disagree" in _errors(tmp_path)
            or f"trace.{field} must be a nonnegative integer" in _errors(tmp_path))


@pytest.mark.parametrize("model,field,value", [
    ("smart", "prompt_tokens", 39),
    ("fast", "completion_tokens", 11),
    ("smart", "prompt_tokens", -1),
    ("fast", "completion_tokens", True),
    ("fast", "prompt_tokens", "20"),
    ("smart", "completion_tokens", 30.5),
    ("fast", "prompt_tokens", None),
])
def test_model_bucket_corruption_rejected(tmp_path, model, field, value):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"]["provider_usage_by_model"][model].__setitem__(field, value))
    errors = _errors(tmp_path)
    assert "provider usage ledger mismatch" in errors or "must be an explicit nonnegative integer" in errors


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
def test_missing_model_bucket_token_category_rejected(tmp_path, field):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"]["provider_usage_by_model"]["smart"].pop(field))
    assert "must be an explicit nonnegative integer" in _errors(tmp_path)


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
def test_missing_aggregate_token_category_rejected(tmp_path, field):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"].pop(field))
    assert f"trace.{field} must be a nonnegative integer" in _errors(tmp_path)


@pytest.mark.parametrize("bad", [None, [], "not-a-ledger", 7])
def test_present_nonmapping_model_ledger_rejected(tmp_path, bad):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"].__setitem__("provider_usage_by_model", bad))
    assert "provider_usage_by_model must be a mapping" in _errors(tmp_path)


def test_versioned_trace_cannot_omit_model_ledger(tmp_path):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"].pop("provider_usage_by_model"))
    assert "schema-v2 trace missing provider_usage_by_model" in _errors(tmp_path)


def test_empty_complete_usage_ledger_is_invalid(tmp_path):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"].__setitem__("provider_usage_by_model", {}))
    assert "complete provider usage has an empty per-model ledger" in _errors(tmp_path)


@pytest.mark.parametrize("bad_bucket", [None, [], 0, "bad"])
def test_malformed_present_model_bucket_rejected(tmp_path, bad_bucket):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data["trace"]["provider_usage_by_model"].__setitem__("fast", bad_bucket))
    assert "invalid provider model usage bucket" in _errors(tmp_path)


@pytest.mark.parametrize("bad_version", [None, True, "2", 0, -1, 2.0])
def test_invalid_trace_schema_marker_cannot_bypass_audit(tmp_path, bad_version):
    path = _write_cell(tmp_path)
    _mutate(path, lambda data: data.__setitem__("schema_version", bad_version))
    assert "invalid trace schema_version" in _errors(tmp_path)


def test_unversioned_legacy_without_bucket_remains_compatible(tmp_path):
    path = _write_cell(tmp_path, versioned=False)
    _mutate(path, lambda data: [
        data["trace"].pop(field) for field in
        ("prompt_tokens", "completion_tokens", "provider_usage_by_model")
    ])
    assert validate_pilot(tmp_path) == []


def test_unversioned_supplied_ledger_must_still_reconcile(tmp_path):
    path = _write_cell(tmp_path, versioned=False)
    _mutate(path, lambda data: data["trace"]["provider_usage_by_model"]["fast"].__setitem__("prompt_tokens", 19))
    assert "provider usage ledger mismatch" in _errors(tmp_path)


def test_unversioned_partial_token_fields_cannot_mask_missing_counts(tmp_path):
    path = _write_cell(tmp_path, versioned=False)
    _mutate(path, lambda data: data["trace"].pop("completion_tokens"))
    assert "trace.completion_tokens must be a nonnegative integer" in _errors(tmp_path)
