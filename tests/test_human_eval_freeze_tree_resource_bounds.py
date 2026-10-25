"""Synthetic bounds for recursive human-analysis freeze capture.

No real annotator submissions or treatment outputs are read or generated.
The limits guard capture resources; they do not establish source authenticity.
"""
from pathlib import Path

import pytest

from scripts import human_eval_analysis_core as core


def _write(root: Path, relative: str, content: bytes):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_freeze_tree_capture_limits_are_explicit():
    assert core.MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_ENTRIES == 256
    assert core.MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_BYTES == 64 * 1024 * 1024
    assert core.MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_DEPTH == 8


def test_direct_tree_snapshot_accepts_exact_entry_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_ENTRIES", 3)
    root = tmp_path / "synthetic"
    _write(root, "folder/one", b"1")
    _write(root, "two", b"2")
    dest = tmp_path / "copy"
    core._snapshot_directory_tree(root, dest, label="synthetic tree")
    assert (dest / "folder" / "one").read_bytes() == b"1"
    assert (dest / "two").read_bytes() == b"2"


def test_direct_tree_snapshot_rejects_excess_entries_before_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_ENTRIES", 3)
    root = tmp_path / "synthetic"
    for name in ("a", "b", "c", "d"):
        _write(root, name, name.encode())
    dest = tmp_path / "copy"
    with pytest.raises(ValueError, match="freeze snapshot entry limit"):
        core._snapshot_directory_tree(root, dest, label="synthetic tree")
    assert not dest.exists()


def test_freeze_inventory_rejects_excess_nested_entries_before_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_ENTRIES", 3)
    root = tmp_path / "synthetic-freeze"
    for name in ("one", "two", "three"):
        _write(root, "governing_inputs/" + name, b"x")
    dest = tmp_path / "freeze-copy"
    with pytest.raises(ValueError, match="freeze snapshot entry limit"):
        core._snapshot_freeze_tree(root, dest)
    assert not dest.exists()


def test_direct_tree_snapshot_accepts_exact_aggregate_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_BYTES", 10)
    root = tmp_path / "synthetic"
    _write(root, "nested/a", b"a" * 6)
    _write(root, "b", b"b" * 4)
    dest = tmp_path / "copy"
    core._snapshot_directory_tree(root, dest, label="synthetic tree")
    assert (dest / "nested" / "a").read_bytes() == b"a" * 6
    assert (dest / "b").read_bytes() == b"b" * 4


def test_direct_tree_snapshot_rejects_excess_total_bytes_before_read(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_BYTES", 10)
    root = tmp_path / "synthetic"
    _write(root, "a", b"a" * 6)
    _write(root, "b", b"b" * 5)
    dest = tmp_path / "copy"

    def forbidden_pread(*args):
        raise AssertionError("aggregate over-limit tree must fail before reading")

    monkeypatch.setattr(core.os, "pread", forbidden_pread)
    with pytest.raises(ValueError, match="aggregate human-analysis freeze snapshot limit"):
        core._snapshot_directory_tree(root, dest, label="synthetic tree")
    assert not dest.exists()


def test_freeze_inventory_rejects_excess_total_bytes_before_read(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_BYTES", 10)
    root = tmp_path / "synthetic-freeze"
    _write(root, "governing_inputs/a", b"a" * 6)
    _write(root, "governing_inputs/b", b"b" * 5)
    dest = tmp_path / "freeze-copy"

    def forbidden_pread(*args):
        raise AssertionError("over-limit inventory must fail before copying")

    monkeypatch.setattr(core.os, "pread", forbidden_pread)
    with pytest.raises(ValueError, match="aggregate human-analysis freeze snapshot limit"):
        core._snapshot_freeze_tree(root, dest)
    assert not dest.exists()


def test_direct_tree_snapshot_rejects_excess_depth(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_DEPTH", 1)
    root = tmp_path / "synthetic"
    _write(root, "parent/child/item", b"x")
    dest = tmp_path / "copy"
    with pytest.raises(ValueError, match="freeze snapshot depth limit"):
        core._snapshot_directory_tree(root, dest, label="synthetic tree")


def test_freeze_inventory_rejects_excess_depth_before_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_DEPTH", 1)
    root = tmp_path / "synthetic-freeze"
    _write(root, "governing_inputs/deeper/item", b"x")
    dest = tmp_path / "freeze-copy"
    with pytest.raises(ValueError, match="freeze snapshot depth limit"):
        core._snapshot_freeze_tree(root, dest)
    assert not dest.exists()


def test_exact_depth_limit_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_DEPTH", 1)
    root = tmp_path / "synthetic"
    _write(root, "parent/item", b"safe")
    dest = tmp_path / "copy"
    core._snapshot_directory_tree(root, dest, label="synthetic tree")
    assert (dest / "parent" / "item").read_bytes() == b"safe"
