"""Reject ambiguous or nonstandard JSON before diagnostic-pilot validation.

All cases are offline synthetic artifacts; they do not run treatments or
modify the historical five-task pilot or frozen main-study results.
"""
import json

import pytest

from scripts.validate_pilot_artifacts import validate_pilot


def _valid_pilot(root):
    variant, task_id = "D6", "pilot-01"
    urls = [f"https://example.invalid/source-{i}" for i in range(6)]
    documents = {
        "pilot_manifest.json": {
            "task_set_id": "synthetic", "variants": [variant],
            "task_ids": [task_id], "smart_model": "smart",
            "fast_model": "fast", "temperature": 1.0,
        },
        "pilot_progress.json": {
            "task_set_id": "synthetic", "variants": [variant],
            "task_ids": [task_id], "total_expected_runs": 1,
            "attempted_runs": 1, "completed_runs": 1,
            "failed_runs": 0, "timeout_runs": 0,
        },
        "pilot_summary.json": {
            "n_trace_files": 1,
            "variant_summary": {variant: {"n_runs": 1, "n_completed": 1}},
        },
    }
    for name, payload in documents.items():
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    trace_file = root / "experiment_traces" / variant / "synthetic.json"
    trace_file.parent.mkdir(parents=True)
    trace_file.write_text(json.dumps({
        "experiment": {
            "variant_id": variant, "task_id": task_id,
            "task_set_id": "synthetic", "source_budget": 6,
        },
        "trace": {
            "variant_id": variant, "task_id": task_id,
            "task_set_id": "synthetic", "completed": True,
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
            "verified_claim_count": 0,
        }
    }), encoding="utf-8")
    return trace_file


def _path(root, name, trace_file):
    return trace_file if name == "trace" else root / name


@pytest.mark.parametrize("target,needle,replacement", [
    ("pilot_manifest.json",
     '"task_set_id": "synthetic"',
     '"task_set_id": "tampered", "task_set_id": "synthetic"'),
    ("pilot_progress.json",
     '"attempted_runs": 1',
     '"attempted_runs": 0, "attempted_runs": 1'),
    ("pilot_summary.json",
     '"n_completed": 1',
     '"n_completed": 0, "n_completed": 1'),
    ("trace",
     '"source_budget": 6',
     '"source_budget": 0, "source_budget": 6'),
    ("trace",
     '"variant_id": "D6"',
     '"variant_id": "P6V", "variant_id": "D6"'),
])
def test_duplicate_keys_at_any_depth_are_rejected(
    tmp_path, target, needle, replacement
):
    trace_file = _valid_pilot(tmp_path)
    path = _path(tmp_path, target, trace_file)
    original = path.read_text(encoding="utf-8")
    assert needle in original
    path.write_text(original.replace(needle, replacement, 1), encoding="utf-8")
    failures = validate_pilot(tmp_path)
    assert any("duplicate JSON key" in error and target.split("/")[-1] in error
               for error in failures), failures


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e309", "-1e309"])
@pytest.mark.parametrize("target", [
    "pilot_manifest.json", "pilot_progress.json", "pilot_summary.json", "trace"
])
def test_nonfinite_numeric_tokens_fail_even_in_unused_fields(
    tmp_path, target, literal
):
    trace_file = _valid_pilot(tmp_path)
    path = _path(tmp_path, target, trace_file)
    data = path.read_text(encoding="utf-8")
    assert data.startswith("{")
    path.write_text('{"unused_extra": ' + literal + ', ' + data[1:], encoding="utf-8")
    assert any("invalid JSON artifact" in e and
               ("numeric" in e or "nonfinite" in e)
               for e in validate_pilot(tmp_path))


@pytest.mark.parametrize("target", [
    "pilot_manifest.json", "pilot_progress.json", "pilot_summary.json", "trace"
])
def test_broken_json_produces_structured_error_not_uncaught_exception(tmp_path, target):
    trace_file = _valid_pilot(tmp_path)
    path = _path(tmp_path, target, trace_file)
    path.write_text('{"corrupt":', encoding="utf-8")
    failures = validate_pilot(tmp_path)
    assert any("invalid JSON artifact" in error and path.name in error
               for error in failures), failures


@pytest.mark.parametrize("target", [
    "pilot_manifest.json", "pilot_progress.json", "pilot_summary.json", "trace"
])
def test_non_object_documents_are_rejected(tmp_path, target):
    trace_file = _valid_pilot(tmp_path)
    path = _path(tmp_path, target, trace_file)
    path.write_text("[]", encoding="utf-8")
    failures = validate_pilot(tmp_path)
    assert any("top-level JSON document must be an object" in error
               for error in failures), failures


def test_valid_documents_allow_reused_field_names_in_distinct_objects(tmp_path):
    _valid_pilot(tmp_path)
    assert validate_pilot(tmp_path) == []
