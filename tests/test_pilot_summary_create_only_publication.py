"""Synthetic tests: diagnostic-pilot summary exports must be create-only."""
import csv
import json
import os
from pathlib import Path

import pytest

from scripts import summarize_pilot as producer


def _paths(monkeypatch, tmp_path):
    monkeypatch.setattr(producer, "OUTPUT_JSON", tmp_path / "pilot_summary.json")
    monkeypatch.setattr(producer, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    return producer.OUTPUT_JSON, producer.OUTPUT_CSV


def _publish():
    producer._publish_pilot_outputs(
        {"schema_version": 5, "n_trace_files": 1},
        [{"variant_id": "D6", "task_id": "pilot-01"}],
    )


def test_publishes_complete_json_and_csv_with_no_staging_leaks(tmp_path, monkeypatch):
    summary, runs = _paths(monkeypatch, tmp_path)
    _publish()
    assert json.loads(summary.read_text(encoding="utf-8")) == {
        "schema_version": 5, "n_trace_files": 1,
    }
    with runs.open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == [
            {"variant_id": "D6", "task_id": "pilot-01"},
        ]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "pilot_runs.csv", "pilot_summary.json",
    ]


@pytest.mark.parametrize("existing", ["summary", "csv", "both", "symlink"])
def test_refuses_any_existing_output_without_replacing_or_creating_another(
    tmp_path, monkeypatch, existing,
):
    summary, runs = _paths(monkeypatch, tmp_path)
    if existing in ("summary", "both"):
        summary.write_text("PRESERVED SUMMARY", encoding="utf-8")
    if existing in ("csv", "both"):
        runs.write_text("PRESERVED CSV", encoding="utf-8")
    if existing == "symlink":
        summary.symlink_to(tmp_path / "missing-target")
    with pytest.raises(FileExistsError, match="already exists"):
        _publish()
    if existing in ("summary", "both"):
        assert summary.read_text(encoding="utf-8") == "PRESERVED SUMMARY"
    elif existing == "symlink":
        assert summary.is_symlink()
    else:
        assert not summary.exists()
    if existing in ("csv", "both"):
        assert runs.read_text(encoding="utf-8") == "PRESERVED CSV"
    else:
        assert not runs.exists()
    assert not list(tmp_path.glob(".pilot-publication-*.tmp"))


def test_racing_csv_creation_cannot_overwrite_or_leave_new_summary(
    tmp_path, monkeypatch,
):
    summary, runs = _paths(monkeypatch, tmp_path)
    original_link = os.link
    attempted = []

    def collide_at_second_link(source, target, *args, **kwargs):
        attempted.append(Path(target))
        if Path(target) == runs:
            runs.write_text("COMPETING EVIDENCE", encoding="utf-8")
        return original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(producer.os, "link", collide_at_second_link)
    with pytest.raises(FileExistsError):
        _publish()
    assert attempted == [summary, runs]
    assert not summary.exists()
    assert runs.read_text(encoding="utf-8") == "COMPETING EVIDENCE"
    assert not list(tmp_path.glob(".pilot-publication-*.tmp"))


@pytest.mark.parametrize("failed_link", [1, 2])
def test_link_failure_rolls_back_only_own_outputs(
    tmp_path, monkeypatch, failed_link,
):
    summary, runs = _paths(monkeypatch, tmp_path)
    original_link = os.link
    seen = 0

    def fail_link(source, target, *args, **kwargs):
        nonlocal seen
        seen += 1
        if seen == failed_link:
            raise OSError("synthetic publication fault")
        return original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(producer.os, "link", fail_link)
    with pytest.raises(OSError, match="synthetic publication fault"):
        _publish()
    assert not summary.exists()
    assert not runs.exists()
    assert not list(tmp_path.glob(".pilot-publication-*.tmp"))


def test_publication_links_only_fully_rendered_files(tmp_path, monkeypatch):
    summary, runs = _paths(monkeypatch, tmp_path)
    original_link = os.link
    verified = []

    def inspect_staged_source(source, target, *args, **kwargs):
        data = Path(source).read_bytes()
        assert data
        if Path(target) == summary:
            assert json.loads(data)["n_trace_files"] == 1
        else:
            assert b"pilot-01" in data and b"variant_id" in data
        verified.append(Path(target))
        return original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(producer.os, "link", inspect_staged_source)
    _publish()
    assert verified == [summary, runs]


def test_legacy_csv_rendering_retains_export_fields_and_empty_behavior():
    assert producer._render_csv([]) == ""
    assert producer._render_csv([{"x": "A", "y": 2}]) == (
        "x,y\r\nA,2\r\n"
    )
