"""Offline regression: bounded diagnostic-pilot source roster and trace capture.

All evidence here is synthetic temporary JSON; no experimental execution.
"""
import json
import os
from pathlib import Path

import pytest

from scripts import summarize_pilot as pilot


def _write(root: Path, arm="D6", task=1) -> Path:
    folder = root / arm
    folder.mkdir(parents=True, exist_ok=True)
    run_id = f"{arm.lower()}-{task:02d}"
    source = {
        "trace": {
            "variant_id": arm,
            "task_set_id": "synthetic-five-task-pilot",
            "task_id": f"pilot-{task:02d}",
            "run_id": run_id,
            "completed": True,
            "source_count": 6,
        },
        "experiment": {
            "variant_id": arm,
            "task_set_id": "synthetic-five-task-pilot",
            "task_id": f"pilot-{task:02d}",
        },
    }
    path = folder / f"{run_id}.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    return path


def _load(monkeypatch, root: Path):
    monkeypatch.setattr(pilot, "TRACE_ROOT", root)
    return pilot._load_traces({"models": {}})


def test_complete_five_task_three_arm_roster_is_retained(tmp_path, monkeypatch):
    for arm in pilot.VARIANT_ORDER:
        for task in range(1, 6):
            _write(tmp_path, arm, task)
    rows = _load(monkeypatch, tmp_path)
    assert len(rows) == 15
    assert {(row["variant_id"], row["task_id"]) for row in rows} == {
        (arm, f"pilot-{task:02d}")
        for arm in pilot.VARIANT_ORDER for task in range(1, 6)
    }


def test_partial_static_roster_remains_supported(tmp_path, monkeypatch):
    _write(tmp_path)
    assert len(_load(monkeypatch, tmp_path)) == 1


def test_excess_trace_candidate_rejected_before_reading_any_source(
    tmp_path, monkeypatch,
):
    for task in range(1, 7):
        _write(tmp_path, task=task)
    monkeypatch.setattr(
        pilot, "_load_captured_pilot_trace",
        lambda path: pytest.fail("no trace should be parsed after inventory overflow"),
    )
    with pytest.raises(ValueError, match="inventory entry limit exceeded"):
        _load(monkeypatch, tmp_path)


def test_extra_arm_root_entries_are_bounded(tmp_path, monkeypatch):
    for arm in (*pilot.VARIANT_ORDER, "unplanned"):
        _write(tmp_path, arm)
    with pytest.raises(ValueError, match="(inventory entry limit|unselected pilot trace)"):
        _load(monkeypatch, tmp_path)


def test_oversize_trace_fails_before_json_parser_or_publication(tmp_path, monkeypatch):
    path = _write(tmp_path)
    with path.open("r+b") as handle:
        handle.truncate(pilot.MAX_PILOT_TRACE_JSON_BYTES + 1)
    monkeypatch.setattr(
        pilot, "_parse_strict_pilot_json_document",
        lambda raw: pytest.fail("oversized source must never reach JSON parser"),
    )
    with pytest.raises(ValueError, match="8 MiB source-size limit"):
        _load(monkeypatch, tmp_path)


def test_external_hardlink_alias_rejected(tmp_path, monkeypatch):
    path = _write(tmp_path / "traces")
    os.link(path, tmp_path / "external-copy.json")
    with pytest.raises(ValueError, match="single-link regular file"):
        _load(monkeypatch, tmp_path / "traces")


def test_detects_in_place_growth_during_descriptor_read(tmp_path, monkeypatch):
    path = _write(tmp_path)
    original_read = pilot.os.read
    mutated = False

    def grow_on_read(fd, size):
        nonlocal mutated
        chunk = original_read(fd, size)
        if not mutated:
            mutated = True
            with path.open("ab") as handle:
                handle.write(b" ")
        return chunk

    monkeypatch.setattr(pilot.os, "read", grow_on_read)
    with pytest.raises(ValueError, match="changed during bounded source capture"):
        _load(monkeypatch, tmp_path)


def test_detects_pathname_replacement_during_descriptor_read(tmp_path, monkeypatch):
    path = _write(tmp_path)
    # Keep the replacement staged outside the trace-root inventory.
    # Otherwise the inventory correctly rejects it before capture begins.
    replacement = tmp_path.parent / f"{tmp_path.name}-replacement.json"
    replacement.write_bytes(path.read_bytes())
    original_read = pilot.os.read
    replaced = False

    def replace_on_read(fd, size):
        nonlocal replaced
        chunk = original_read(fd, size)
        if not replaced:
            replaced = True
            os.replace(replacement, path)
        return chunk

    monkeypatch.setattr(pilot.os, "read", replace_on_read)
    with pytest.raises(ValueError, match="changed during bounded source capture"):
        _load(monkeypatch, tmp_path)


def test_duplicate_json_keys_still_fail_after_descriptor_capture(tmp_path, monkeypatch):
    path = _write(tmp_path)
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace('"completed": true', '"completed": false, "completed": true'), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _load(monkeypatch, tmp_path)
