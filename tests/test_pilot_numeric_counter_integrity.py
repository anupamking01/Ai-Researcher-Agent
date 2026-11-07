"""Offline diagnostic-pilot numeric telemetry checks; no experiments run."""
import json
import pytest
from scripts.validate_pilot_artifacts import validate_pilot


def write_cell(root, variant="D6"):
    planner = variant != "D6"
    verify = variant == "P6V"
    urls = [f"https://example.invalid/{n}" for n in range(6)]
    records = {
        "pilot_manifest.json": {
            "task_set_id": "synthetic", "variants": [variant],
            "task_ids": ["pilot-01"], "smart_model": "smart",
            "fast_model": "fast", "temperature": 1.0,
        },
        "pilot_progress.json": {
            "task_set_id": "synthetic", "variants": [variant],
            "task_ids": ["pilot-01"], "total_expected_runs": 1,
            "attempted_runs": 1, "completed_runs": 1,
            "failed_runs": 0, "timeout_runs": 0,
        },
        "pilot_summary.json": {
            "n_trace_files": 1,
            "variant_summary": {variant: {"n_runs": 1, "n_completed": 1}},
        },
    }
    for name, record in records.items():
        (root / name).write_text(json.dumps(record), encoding="utf-8")
    path = root / "experiment_traces" / variant / "run.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "experiment": {
            "variant_id": variant, "task_id": "pilot-01",
            "task_set_id": "synthetic", "source_budget": 6,
        },
        "trace": {
            "variant_id": variant, "task_id": "pilot-01",
            "task_set_id": "synthetic", "completed": True,
            "planning_mode": "planner" if planner else "direct",
            "verification_mode": "verify" if verify else "none",
            "source_budget": 6, "source_count": 6,
            "successful_source_count": 6, "failed_source_count": 0,
            "scheduled_urls": urls, "successful_urls": urls, "failed_urls": [],
            "query_count": 4 if planner else 1,
            "search_call_count": 4 if planner else 1,
            "research_context_words": 9, "report_words": 17,
            "model_call_count": 3, "total_tokens": 100,
            "usage_accounting_status": "provider_usage_complete",
            "smart_model": "smart", "fast_model": "fast", "temperature": 1.0,
            "verification_status": "ok" if verify else "not_requested",
            "verified_claim_count": 2 if verify else 0,
        },
    }), encoding="utf-8")


def mutate(root, target, field, value, variant="D6"):
    if target == "trace":
        path = root / "experiment_traces" / variant / "run.json"
        obj = json.loads(path.read_text(encoding="utf-8"))
        record = obj["trace"]
    else:
        path = root / target
        obj = json.loads(path.read_text(encoding="utf-8"))
        record = obj
        if target == "pilot_summary.json" and field.startswith("D6."):
            record = obj["variant_summary"]["D6"]
            field = field.split(".", 1)[1]
    if value == "DELETE_KEY":
        del record[field]
    else:
        record[field] = value
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.mark.parametrize("variant", ["D6", "P6", "P6V"])
def test_integer_telemetry_is_accepted(tmp_path, variant):
    write_cell(tmp_path, variant)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize("target,field,value,diagnostic", [
    ("pilot_progress.json", "total_expected_runs", True, "progress.total_expected_runs"),
    ("pilot_progress.json", "attempted_runs", 1.0, "progress.attempted_runs"),
    ("pilot_progress.json", "completed_runs", "1", "progress.completed_runs"),
    ("pilot_progress.json", "failed_runs", False, "progress.failed_runs"),
    ("pilot_progress.json", "timeout_runs", "0", "progress.timeout_runs"),
    ("pilot_progress.json", "failed_runs", "DELETE_KEY", "progress.failed_runs"),
    ("pilot_summary.json", "n_trace_files", "1", "summary.n_trace_files"),
    ("pilot_summary.json", "D6.n_runs", True, "summary D6.n_runs"),
    ("pilot_summary.json", "D6.n_completed", 1.9, "summary D6.n_completed"),
    ("trace", "source_budget", 6.0, "trace.source_budget"),
    ("trace", "source_count", "6", "trace.source_count"),
    ("trace", "source_count", -1, "trace.source_count"),
    ("trace", "successful_source_count", 6.8, "trace.successful_source_count"),
    ("trace", "failed_source_count", "0", "trace.failed_source_count"),
    ("trace", "failed_source_count", "DELETE_KEY", "trace.failed_source_count"),
    ("trace", "query_count", True, "trace.query_count"),
    ("trace", "search_call_count", 1.9, "trace.search_call_count"),
    ("trace", "research_context_words", "9", "trace.research_context_words"),
    ("trace", "report_words", float("nan"), "trace.report_words"),
    ("trace", "model_call_count", False, "trace.model_call_count"),
    ("trace", "total_tokens", "100", "trace.total_tokens"),
    ("trace", "total_tokens", float("inf"), "trace.total_tokens"),
    ("trace", "verified_claim_count", "0", "trace.verified_claim_count"),
])
def test_invalid_or_coerced_counter_is_reported(
    tmp_path, target, field, value, diagnostic
):
    write_cell(tmp_path)
    mutate(tmp_path, target, field, value)
    assert any(diagnostic + " must be a nonnegative integer" in e
               for e in validate_pilot(tmp_path))


@pytest.mark.parametrize("value", ["2", True, 2.5, None, float("inf")])
def test_p6v_verification_count_must_be_integer(tmp_path, value):
    write_cell(tmp_path, "P6V")
    mutate(tmp_path, "trace", "verified_claim_count", value, variant="P6V")
    assert any("trace.verified_claim_count must be a nonnegative integer" in e
               for e in validate_pilot(tmp_path))


@pytest.mark.parametrize("target,value,diagnostic", [
    ("trace", "1.0", "trace.temperature"),
    ("trace", True, "trace.temperature"),
    ("trace", "not-a-number", "trace.temperature"),
    ("trace", float("inf"), "trace.temperature"),
    ("trace", float("nan"), "trace.temperature"),
    ("pilot_manifest.json", "1.0", "manifest.temperature"),
    ("pilot_manifest.json", False, "manifest.temperature"),
    ("pilot_manifest.json", {}, "manifest.temperature"),
])
def test_invalid_temperatures_are_reported_not_coerced(
    tmp_path, target, value, diagnostic
):
    write_cell(tmp_path)
    mutate(tmp_path, target, "temperature", value)
    assert any(diagnostic + " must be a finite numeric value" in e
               for e in validate_pilot(tmp_path))


def test_distinct_valid_temperatures_still_fail(tmp_path):
    write_cell(tmp_path)
    mutate(tmp_path, "trace", "temperature", 0.5)
    assert "temperature differs from manifest" in " | ".join(validate_pilot(tmp_path))
