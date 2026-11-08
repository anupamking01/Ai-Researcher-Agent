"""Synthetic offline progress-event custody checks for the diagnostic pilot.

No treatment, evaluator, model, web request, or human rating is executed.
"""
import json

import pytest

from scripts.validate_pilot_artifacts import validate_pilot


def _write_valid(root, *, versioned=True, with_events=True):
    tasks = ["pilot-01", "pilot-02"]
    variant = "D6"
    manifest = {
        "task_set_id": "synthetic-ledger", "variants": [variant],
        "task_ids": tasks, "smart_model": "smart", "fast_model": "fast",
        "temperature": 1.0,
    }
    progress = {
        "task_set_id": "synthetic-ledger", "variants": [variant],
        "task_ids": tasks, "total_expected_runs": 2,
        "attempted_runs": 2, "completed_runs": 2,
        "failed_runs": 0, "timeout_runs": 0,
        "current": None,
    }
    if versioned:
        progress["schema_version"] = 1
    if with_events:
        progress["events"] = [
            {"variant": variant, "task_id": task, "status": "completed"}
            for task in tasks
        ]
    summary = {
        "n_trace_files": 2,
        "variant_summary": {"D6": {"n_runs": 2, "n_completed": 2}},
    }
    for path, data in (
        ("pilot_manifest.json", manifest),
        ("pilot_progress.json", progress),
        ("pilot_summary.json", summary),
    ):
        (root / path).write_text(json.dumps(data), encoding="utf-8")
    target = root / "experiment_traces" / variant
    target.mkdir(parents=True)
    urls = [f"https://example.invalid/evidence/{n}" for n in range(6)]
    for task in tasks:
        experiment = {
            "variant_id": variant, "task_id": task,
            "task_set_id": "synthetic-ledger", "source_budget": 6,
        }
        trace = {
            "variant_id": variant, "task_id": task,
            "task_set_id": "synthetic-ledger", "completed": True,
            "planning_mode": "direct", "verification_mode": "none",
            "source_budget": 6, "source_count": 6,
            "successful_source_count": 6, "failed_source_count": 0,
            "scheduled_urls": urls, "successful_urls": urls, "failed_urls": [],
            "query_count": 1, "search_call_count": 1,
            "research_context_words": 9, "report_words": 17,
            "model_call_count": 3, "total_tokens": 100,
            "usage_accounting_status": "provider_usage_complete",
            "smart_model": "smart", "fast_model": "fast", "temperature": 1.0,
            "verification_status": "not_requested",
        }
        (target / f"{task}.json").write_text(
            json.dumps({"experiment": experiment, "trace": trace}),
            encoding="utf-8",
        )
    return progress


def _write_progress(root, progress):
    (root / "pilot_progress.json").write_text(
        json.dumps(progress), encoding="utf-8"
    )


def _invalid(root, progress, expected):
    _write_progress(root, progress)
    errors = validate_pilot(root)
    assert expected in " | ".join(errors), errors


def test_versioned_run_with_exact_completed_events_passes(tmp_path):
    _write_valid(tmp_path)
    assert validate_pilot(tmp_path) == []


def test_event_completion_order_not_assumed(tmp_path):
    progress = _write_valid(tmp_path)
    progress["events"].reverse()
    _write_progress(tmp_path, progress)
    assert validate_pilot(tmp_path) == []


def test_versioned_checkpoint_requires_event_ledger(tmp_path):
    _write_valid(tmp_path, with_events=False)
    assert "versioned progress is missing its events ledger" in (
        " | ".join(validate_pilot(tmp_path))
    )


def test_unversioned_legacy_record_retains_existing_compatibility(tmp_path):
    _write_valid(tmp_path, versioned=False, with_events=False)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize("invalid", [None, {}, "completed", True, 2])
def test_present_malformed_event_collection_fails(tmp_path, invalid):
    progress = _write_valid(tmp_path)
    progress["events"] = invalid
    _invalid(tmp_path, progress, "progress.events must be a list")


def test_missing_event_does_not_pass_correct_aggregate_counters(tmp_path):
    progress = _write_valid(tmp_path)
    progress["events"].pop()
    _invalid(tmp_path, progress, "progress events=1 expected=2")


def test_duplicate_event_does_not_hide_missing_cell(tmp_path):
    progress = _write_valid(tmp_path)
    progress["events"][1] = dict(progress["events"][0])
    _invalid(tmp_path, progress, "duplicates treatment/task cell")


@pytest.mark.parametrize("field,value", [
    ("variant", "P6"), ("task_id", "unknown-task"),
])
def test_unplanned_cell_rejected(tmp_path, field, value):
    progress = _write_valid(tmp_path)
    progress["events"][0][field] = value
    _invalid(tmp_path, progress, "unplanned treatment/task cell")


@pytest.mark.parametrize("field,value", [
    ("variant", ""), ("variant", " D6 "),
    ("task_id", None), ("task_id", 1), ("task_id", False),
])
def test_malformed_event_identity_rejected(tmp_path, field, value):
    progress = _write_valid(tmp_path)
    progress["events"][0][field] = value
    _invalid(tmp_path, progress, "invalid treatment/task identity")


@pytest.mark.parametrize("status", [
    "failed", "timeout", "running", None, "", True, 1,
])
def test_noncompleted_event_rejected_even_if_counters_claim_success(tmp_path, status):
    progress = _write_valid(tmp_path)
    progress["events"][0]["status"] = status
    _invalid(tmp_path, progress, "not a completed terminal event")


@pytest.mark.parametrize("event", [None, [], 1, "D6/pilot-01"])
def test_nonobject_event_rejected(tmp_path, event):
    progress = _write_valid(tmp_path)
    progress["events"][0] = event
    _invalid(tmp_path, progress, "must be an object")


def test_active_current_event_cannot_be_called_finished(tmp_path):
    progress = _write_valid(tmp_path)
    progress["current"] = {"variant": "D6", "task_id": "pilot-02", "status": "running"}
    _invalid(tmp_path, progress, "progress.current must be null")


def test_event_count_cannot_disagree_with_attempted_counter(tmp_path):
    progress = _write_valid(tmp_path)
    progress["attempted_runs"] = 3
    _invalid(tmp_path, progress, "progress events count differs from attempted_runs")


def test_event_status_cannot_disagree_with_completed_counter(tmp_path):
    progress = _write_valid(tmp_path)
    progress["completed_runs"] = 1
    _invalid(tmp_path, progress, "progress completed event count differs from completed_runs")
