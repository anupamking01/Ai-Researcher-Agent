"""Synthetic standalone diagnostic-pilot source-inventory and identity tests.

No web, model, evaluator, human rating, or historical treatment is executed.
"""
import json

import pytest

from scripts import summarize_pilot as pilot


def _write(root, *, arm="D6", filename="run-01.json",
           trace_overrides=None, experiment_overrides=None):
    folder = root / arm
    folder.mkdir(parents=True, exist_ok=True)
    trace = {
        "variant_id": arm,
        "task_set_id": "synthetic-pilot",
        "task_id": "pilot-01",
        "run_id": filename.removesuffix(".json"),
        "completed": True,
        "source_count": 6,
        "successful_source_count": 5,
        "failed_source_count": 1,
        "latency_seconds": 1.0,
    }
    experiment = {
        "variant_id": arm,
        "task_set_id": "synthetic-pilot",
        "task_id": "pilot-01",
    }
    if trace_overrides:
        trace.update(trace_overrides)
    if experiment_overrides:
        experiment.update(experiment_overrides)
    path = folder / filename
    path.write_text(json.dumps({"trace": trace, "experiment": experiment}), encoding="utf-8")
    return path


def _load(monkeypatch, root):
    monkeypatch.setattr(pilot, "TRACE_ROOT", root)
    return pilot._load_traces({"models": {}})


def test_valid_independent_trace_has_frozen_source_filename_identity(tmp_path, monkeypatch):
    _write(tmp_path, arm="D6", filename="source-run.json")
    rows = _load(monkeypatch, tmp_path)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "source-run"
    assert rows[0]["variant_id"] == "D6"


def test_unobserved_legacy_run_id_uses_filename_without_inventing_new_run(tmp_path, monkeypatch):
    path = _write(tmp_path)
    payload = json.loads(path.read_text())
    del payload["trace"]["run_id"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _load(monkeypatch, tmp_path)[0]["run_id"] == "run-01"


def test_explicit_run_id_cannot_claim_different_source_file(tmp_path, monkeypatch):
    _write(tmp_path, trace_overrides={"run_id": "selected-other-run"})
    with pytest.raises(ValueError, match="run_id disagrees with filename"):
        _load(monkeypatch, tmp_path)


@pytest.mark.parametrize("invalid", [None, "", "  ", " padded ", 0, False, 4.5, []])
def test_invalid_observed_run_id_is_not_replaced_by_file_stem(
    tmp_path, monkeypatch, invalid
):
    _write(tmp_path, trace_overrides={"run_id": invalid})
    with pytest.raises(ValueError, match="invalid pilot trace run_id"):
        _load(monkeypatch, tmp_path)


@pytest.mark.parametrize("field", ["variant_id", "task_set_id", "task_id"])
@pytest.mark.parametrize("invalid", ["", None, False, 0, " padded ", []])
@pytest.mark.parametrize("source", ["trace", "experiment"])
def test_present_invalid_identity_cannot_be_masked_by_other_record(
    tmp_path, monkeypatch, field, invalid, source
):
    overrides = {field: invalid}
    _write(
        tmp_path,
        trace_overrides=overrides if source == "trace" else None,
        experiment_overrides=overrides if source == "experiment" else None,
    )
    with pytest.raises(ValueError, match=f"invalid pilot {source}.{field}"):
        _load(monkeypatch, tmp_path)


@pytest.mark.parametrize("field,value", [
    ("variant_id", "P6"),
    ("task_set_id", "other-study"),
    ("task_id", "pilot-02"),
])
def test_valid_but_disagreeing_trace_and_experiment_identities_fail(
    tmp_path, monkeypatch, field, value
):
    _write(tmp_path, experiment_overrides={field: value})
    with pytest.raises(ValueError, match=f"{field} mismatch"):
        _load(monkeypatch, tmp_path)


@pytest.mark.parametrize("field", ["variant_id", "task_set_id", "task_id"])
def test_missing_identity_in_both_sources_cannot_be_inferred(
    tmp_path, monkeypatch, field
):
    path = _write(tmp_path)
    payload = json.loads(path.read_text())
    payload["trace"].pop(field)
    payload["experiment"].pop(field)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=f"missing pilot {field}"):
        _load(monkeypatch, tmp_path)


@pytest.mark.parametrize("name", ["P6V-copy", "unexpected"])
def test_unselected_arm_directory_is_not_silently_skipped(tmp_path, monkeypatch, name):
    _write(tmp_path)
    folder = tmp_path / name
    folder.mkdir()
    (folder / "recovered.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unselected pilot trace directory"):
        _load(monkeypatch, tmp_path)


@pytest.mark.parametrize("entry", [".partial.tmp", "leftover.csv", "README.txt"])
def test_unselected_nonjson_entry_fails_closed(tmp_path, monkeypatch, entry):
    _write(tmp_path)
    (tmp_path / "D6" / entry).write_text("incomplete", encoding="utf-8")
    with pytest.raises(ValueError, match="unselected pilot trace entry"):
        _load(monkeypatch, tmp_path)


def test_nested_json_source_cannot_be_silently_skipped(tmp_path, monkeypatch):
    _write(tmp_path)
    nested = tmp_path / "D6" / "retry"
    nested.mkdir()
    (nested / "run-01.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unselected pilot trace entry"):
        _load(monkeypatch, tmp_path)


def test_unexpected_root_entry_cannot_be_silently_skipped(tmp_path, monkeypatch):
    _write(tmp_path)
    (tmp_path / "untracked.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unselected pilot trace directory"):
        _load(monkeypatch, tmp_path)


def test_symlink_to_trace_file_rejected(tmp_path, monkeypatch):
    original = _write(tmp_path)
    (tmp_path / "D6" / "alias.json").symlink_to(original)
    with pytest.raises(ValueError, match="unselected pilot trace entry"):
        _load(monkeypatch, tmp_path)


def test_symlink_to_arm_rejected(tmp_path, monkeypatch):
    _write(tmp_path)
    (tmp_path / "P6").symlink_to(tmp_path / "D6", target_is_directory=True)
    with pytest.raises(ValueError, match="unselected pilot trace directory"):
        _load(monkeypatch, tmp_path)


def test_symlink_to_trace_root_rejected(tmp_path, monkeypatch):
    source = tmp_path / "source"
    _write(source)
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="pilot trace root must not be a symlink"):
        _load(monkeypatch, alias)


def test_non_directory_trace_root_rejected(tmp_path, monkeypatch):
    path = tmp_path / "trace-root"
    path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="pilot trace root must be a directory"):
        _load(monkeypatch, path)


def test_absent_trace_root_retains_prior_empty_inventory_semantics(
    tmp_path, monkeypatch
):
    assert _load(monkeypatch, tmp_path / "absent") == []


def test_full_summary_refuses_unselected_source_before_any_publication(
    tmp_path, monkeypatch
):
    _write(tmp_path / "traces")
    (tmp_path / "traces" / "D6" / "staging.tmp").write_text("incomplete", encoding="utf-8")
    monkeypatch.setattr(pilot, "TRACE_ROOT", tmp_path / "traces")
    monkeypatch.setattr(pilot, "_load_pricing", lambda: {"models": {}})
    monkeypatch.setattr(pilot, "OUTPUT_JSON", tmp_path / "published.json")
    monkeypatch.setattr(pilot, "OUTPUT_CSV", tmp_path / "published.csv")
    with pytest.raises(ValueError, match="unselected pilot trace entry"):
        pilot.main()
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()
