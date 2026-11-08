"""Synthetic continuity tests for the five-task diagnostic-pilot summarizer.

No treatment/evaluator/human work is executed; all sources are temporary files.
"""
import json
import os
from pathlib import Path

import pytest

from scripts import summarize_pilot as pilot


def _source(root: Path) -> Path:
    directory = root / "traces" / "D6"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "d6-01.json"
    path.write_text(json.dumps({
        "trace": {
            "variant_id": "D6", "task_set_id": "synthetic-pilot",
            "task_id": "pilot-01", "run_id": "d6-01", "completed": True,
        },
        "experiment": {
            "variant_id": "D6", "task_set_id": "synthetic-pilot",
            "task_id": "pilot-01",
        },
    }), encoding="utf-8")
    return path


def _setup(tmp_path, monkeypatch):
    path = _source(tmp_path)
    monkeypatch.setattr(pilot, "TRACE_ROOT", tmp_path / "traces")
    monkeypatch.setattr(pilot, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pilot, "PRICING_FILE", tmp_path / "pricing.json")
    pilot.PRICING_FILE.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "OUTPUT_JSON", tmp_path / "pilot_summary.json")
    monkeypatch.setattr(pilot, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    return path


def test_unmodified_selected_sources_survive_prepublication_check(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    snapshot = pilot._capture_pilot_source_metadata()
    assert len(snapshot) == 1
    assert pilot._verify_pilot_source_metadata(snapshot) is None
    rows = pilot._load_traces({"models": {}})
    pilot._publish_pilot_outputs(
        {"schema_version": 5}, rows,
        prepublish_check=lambda: pilot._verify_pilot_source_metadata(snapshot),
    )
    assert pilot.OUTPUT_JSON.exists() and pilot.OUTPUT_CSV.exists()


def test_rejects_in_place_change_after_source_capture(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    snapshot = pilot._capture_pilot_source_metadata()
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="pilot source changed"):
        pilot._verify_pilot_source_metadata(snapshot)


def test_rejects_same_byte_pathname_replacement(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    snapshot = pilot._capture_pilot_source_metadata()
    candidate = tmp_path / "new-copy.json"  # outside the selected roster
    candidate.write_bytes(path.read_bytes())
    os.replace(candidate, path)
    with pytest.raises(ValueError, match="pilot source changed"):
        pilot._verify_pilot_source_metadata(snapshot)


@pytest.mark.parametrize("mutation", ["addition", "removal"])
def test_rejects_changed_source_roster(tmp_path, monkeypatch, mutation):
    path = _setup(tmp_path, monkeypatch)
    snapshot = pilot._capture_pilot_source_metadata()
    if mutation == "addition":
        (path.parent / "unselected.json").write_text("{}", encoding="utf-8")
    else:
        path.unlink()
    with pytest.raises(ValueError, match="pilot source inventory changed"):
        pilot._verify_pilot_source_metadata(snapshot)


def test_main_does_not_publish_after_postread_source_mutation(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(pilot, "_load_pricing", lambda: {"models": {}})
    original_loader = pilot._load_traces

    def mutate_after_load(pricing):
        rows = original_loader(pricing)
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return rows

    monkeypatch.setattr(pilot, "_load_traces", mutate_after_load)
    with pytest.raises(ValueError, match="pilot source changed before publication"):
        pilot.main()
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()
    assert not list(tmp_path.glob(".pilot-publication-*.tmp"))


def test_change_after_first_link_rolls_back_own_json(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    snapshot = pilot._capture_pilot_source_metadata()
    rows = pilot._load_traces({"models": {}})
    original_link = os.link

    def mutate_after_first_link(src, dst, *args, **kwargs):
        result = original_link(src, dst, *args, **kwargs)
        if Path(dst) == pilot.OUTPUT_JSON:
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return result

    monkeypatch.setattr(pilot.os, "link", mutate_after_first_link)
    with pytest.raises(ValueError, match="pilot source changed before publication"):
        pilot._publish_pilot_outputs(
            {"schema_version": 5}, rows,
            prepublish_check=lambda: pilot._verify_pilot_source_metadata(snapshot),
        )
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()
    assert not list(tmp_path.glob(".pilot-publication-*.tmp"))
