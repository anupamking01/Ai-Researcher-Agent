"""Offline source-lineage tests for the diagnostic pilot validator.

These synthetic records never rerun treatments or modify historical results.
"""
import json

import pytest

from scripts.validate_pilot_artifacts import validate_pilot


def _write_valid(root):
    manifest = {
        "task_set_id": "synthetic-pilot", "variants": ["D6"],
        "task_ids": ["pilot-01"], "smart_model": "test-smart",
        "fast_model": "test-fast", "temperature": 1.0,
    }
    progress = {
        "task_set_id": "synthetic-pilot", "variants": ["D6"],
        "task_ids": ["pilot-01"], "total_expected_runs": 1,
        "attempted_runs": 1, "completed_runs": 1,
        "failed_runs": 0, "timeout_runs": 0,
    }
    summary = {
        "n_trace_files": 1, "variant_summary": {
            "D6": {"n_runs": 1, "n_completed": 1}
        }
    }
    urls = [f"https://example.org/source/{n}" for n in range(6)]
    trace = {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "synthetic-pilot", "completed": True,
        "source_budget": 6, "source_count": 6,
        "successful_source_count": 4, "failed_source_count": 2,
        "scheduled_urls": list(urls), "successful_urls": urls[:4],
        "failed_urls": urls[4:], "planning_mode": "direct",
        "query_count": 1, "search_call_count": 1,
        "research_context_words": 10, "report_words": 20,
        "model_call_count": 1, "total_tokens": 100,
        "usage_accounting_status": "provider_usage_complete",
        "smart_model": "test-smart", "fast_model": "test-fast",
        "temperature": 1.0, "verification_mode": "none",
        "verification_status": "not_requested",
    }
    experiment = {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "synthetic-pilot", "source_budget": 6,
    }
    for path, payload in (
        (root / "pilot_manifest.json", manifest),
        (root / "pilot_progress.json", progress),
        (root / "pilot_summary.json", summary),
    ):
        path.write_text(json.dumps(payload), encoding="utf-8")
    trace_path = root / "experiment_traces" / "D6" / "synthetic.json"
    trace_path.parent.mkdir(parents=True)
    trace_path.write_text(
        json.dumps({"experiment": experiment, "trace": trace}),
        encoding="utf-8",
    )
    return trace_path, trace, urls


def _save_trace(path, trace):
    path.write_text(json.dumps({
        "experiment": {
            "variant_id": "D6", "task_id": "pilot-01",
            "task_set_id": "synthetic-pilot", "source_budget": 6,
        },
        "trace": trace,
    }), encoding="utf-8")


def test_valid_source_partition_passes(tmp_path):
    _write_valid(tmp_path)
    assert validate_pilot(tmp_path) == []


def test_source_partition_does_not_require_completion_order(tmp_path):
    path, trace, _ = _write_valid(tmp_path)
    trace["successful_urls"].reverse()
    trace["failed_urls"].reverse()
    _save_trace(path, trace)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize(
    ("name", "replacement", "message"),
    [
        (
            "scheduled_urls",
            ["https://example.org/source/0"] * 6,
            "duplicate scheduled source URL",
        ),
        (
            "successful_urls",
            ["https://example.org/source/0",
             "https://example.org/source/1",
             "https://example.org/source/2",
             "https://example.org/unrelated"],
            "do not partition scheduled source URLs",
        ),
        (
            "failed_urls",
            ["https://example.org/source/4",
             "https://example.org/source/4"],
            "do not partition scheduled source URLs",
        ),
        (
            "successful_urls",
            ["https://example.org/source/0",
             "https://example.org/source/1",
             "https://example.org/source/2",
             "https://example.org/source/4"],
            "do not partition scheduled source URLs",
        ),
        ("scheduled_urls", "xxxxxx", "must be a list"),
        ("successful_urls", None, "must be a list"),
        ("failed_urls", ["https://example.org/source/4", ""],
         "must be a list"),
        ("failed_urls", ["https://example.org/source/4",
                         " https://example.org/source/5 "],
         "must be a list"),
    ],
)
def test_invalid_source_identity_is_rejected(tmp_path, name, replacement, message):
    path, trace, _ = _write_valid(tmp_path)
    trace[name] = replacement
    _save_trace(path, trace)
    assert message in " | ".join(validate_pilot(tmp_path))


def test_missing_source_list_does_not_pass_as_empty(tmp_path):
    path, trace, _ = _write_valid(tmp_path)
    del trace["failed_urls"]
    _save_trace(path, trace)
    assert "failed_urls must be a list" in " | ".join(validate_pilot(tmp_path))
