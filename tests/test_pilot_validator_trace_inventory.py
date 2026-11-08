"""Fail-closed original-file inventory for postrun diagnostic-pilot validation.

All evidence in this module is synthetic; no model, evaluator, treatment, or
human evaluation is run. In particular, this does not authenticate historical
main-study reports or traces.
"""
import json

import pytest

from scripts.validate_pilot_artifacts import validate_pilot


def _write(root):
    arm, task_id, run_id = "D6", "pilot-01", "run-001"
    urls = [f"https://example.invalid/source/{i}" for i in range(6)]
    manifest = {
        "schema_version": 1, "task_set_id": "synthetic-inventory",
        "variants": [arm], "task_ids": [task_id],
        "smart_model": "smart", "fast_model": "fast", "temperature": 1.0,
    }
    progress = {
        "schema_version": 1, "task_set_id": "synthetic-inventory",
        "variants": [arm], "task_ids": [task_id],
        "total_expected_runs": 1, "attempted_runs": 1, "completed_runs": 1,
        "failed_runs": 0, "timeout_runs": 0, "current": None,
        "events": [{"variant": arm, "task_id": task_id, "status": "completed"}],
    }
    summary = {
        "n_trace_files": 1,
        "variant_summary": {arm: {"n_runs": 1, "n_completed": 1}},
    }
    for name, data in (
        ("pilot_manifest.json", manifest),
        ("pilot_progress.json", progress),
        ("pilot_summary.json", summary),
    ):
        (root / name).write_text(json.dumps(data), encoding="utf-8")
    path = root / "experiment_traces" / arm / (run_id + ".json")
    path.parent.mkdir(parents=True)
    trace = {
        "variant_id": arm, "task_set_id": "synthetic-inventory",
        "task_id": task_id, "run_id": run_id, "completed": True,
        "planning_mode": "direct", "verification_mode": "none",
        "source_budget": 6, "source_count": 6,
        "successful_source_count": 6, "failed_source_count": 0,
        "scheduled_urls": urls, "successful_urls": urls, "failed_urls": [],
        "query_count": 1, "search_call_count": 1,
        "research_context_words": 10, "report_words": 20,
        "model_call_count": 3, "total_tokens": 100,
        "usage_accounting_status": "provider_usage_complete",
        "smart_model": "smart", "fast_model": "fast", "temperature": 1.0,
        "verification_status": "not_requested", "verified_claim_count": 0,
    }
    path.write_text(json.dumps({
        "experiment": {"variant_id": arm, "task_set_id": "synthetic-inventory",
                       "task_id": task_id, "source_budget": 6, "run_id": run_id},
        "trace": trace,
    }), encoding="utf-8")
    return path


def _errors(root):
    return " | ".join(validate_pilot(root))


def test_complete_unambiguous_inventory_passes(tmp_path):
    _write(tmp_path)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize("name", ["P6", "unexpected", "D6-backup"])
def test_unselected_arm_directory_is_not_invisible(tmp_path, name):
    _write(tmp_path)
    folder = tmp_path / "experiment_traces" / name
    folder.mkdir()
    (folder / "other.json").write_text("{}", encoding="utf-8")
    assert "unselected pilot trace directory or entry" in _errors(tmp_path)


@pytest.mark.parametrize("name", ["unselected.json", "README.txt", ".stage"])
def test_unselected_trace_root_file_is_not_invisible(tmp_path, name):
    _write(tmp_path)
    (tmp_path / "experiment_traces" / name).write_text("stale", encoding="utf-8")
    assert "unselected pilot trace directory or entry" in _errors(tmp_path)


@pytest.mark.parametrize("name", ["run-001.json.tmp", "notes.txt", ".partial"])
def test_unselected_trace_arm_entry_is_not_invisible(tmp_path, name):
    _write(tmp_path)
    (tmp_path / "experiment_traces" / "D6" / name).write_text("stale", encoding="utf-8")
    assert "unselected pilot trace entry" in _errors(tmp_path)


def test_nested_retry_artifacts_are_rejected(tmp_path):
    _write(tmp_path)
    folder = tmp_path / "experiment_traces" / "D6" / "retry"
    folder.mkdir()
    (folder / "other.json").write_text("{}", encoding="utf-8")
    assert "unselected pilot trace entry" in _errors(tmp_path)


def test_symlinked_trace_root_is_not_followed(tmp_path):
    _write(tmp_path)
    source = tmp_path / "experiment_traces"
    source.rename(tmp_path / "real-traces")
    source.symlink_to(tmp_path / "real-traces", target_is_directory=True)
    assert "pilot trace root must not be a symlink" in _errors(tmp_path)


def test_symlinked_arm_is_not_followed(tmp_path):
    _write(tmp_path)
    (tmp_path / "experiment_traces" / "P6").symlink_to(
        tmp_path / "experiment_traces" / "D6", target_is_directory=True
    )
    assert "unselected pilot trace directory or entry" in _errors(tmp_path)


def test_symlinked_json_source_is_not_followed(tmp_path):
    path = _write(tmp_path)
    (path.parent / "alias.json").symlink_to(path)
    assert "unselected pilot trace entry" in _errors(tmp_path)


@pytest.mark.parametrize("name", [
    "pilot_manifest.json", "pilot_progress.json", "pilot_summary.json"
])
def test_symlinked_required_document_is_rejected(tmp_path, name):
    _write(tmp_path)
    path = tmp_path / name
    original = tmp_path / ("old-" + name)
    path.rename(original)
    path.symlink_to(original)
    assert f"required artifact is a symlink: {name}" in _errors(tmp_path)


def test_symlinked_output_root_is_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write(source)
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    assert "pilot output root must not be a symlink" in _errors(alias)


@pytest.mark.parametrize("source", ["trace", "experiment"])
@pytest.mark.parametrize("invalid", ["other-run", " run-001 ", "", None, True, 1])
def test_observed_run_identity_must_match_source_filename(
    tmp_path, source, invalid
):
    path = _write(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    document[source]["run_id"] = invalid
    path.write_text(json.dumps(document), encoding="utf-8")
    assert f"{source}.run_id disagrees with source filename" in _errors(tmp_path)


def test_legacy_unobserved_run_id_is_not_fabricated(tmp_path):
    path = _write(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["trace"]["run_id"]
    del document["experiment"]["run_id"]
    path.write_text(json.dumps(document), encoding="utf-8")
    assert validate_pilot(tmp_path) == []


def test_missing_trace_inventory_is_not_treated_as_empty_valid_set(tmp_path):
    _write(tmp_path)
    root = tmp_path / "experiment_traces"
    for path in (root / "D6").iterdir():
        path.unlink()
    (root / "D6").rmdir()
    root.rmdir()
    assert "missing or invalid pilot trace root directory" in _errors(tmp_path)
