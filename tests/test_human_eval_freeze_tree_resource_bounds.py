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



def test_bounded_scan_accepts_exact_limit_without_listdir(tmp_path, monkeypatch):
    """A valid directory still has a deterministic name order."""
    root = tmp_path / "synthetic"
    _write(root, "z", b"z")
    _write(root, "a", b"a")
    _write(root, "m", b"m")
    original_listdir = core.os.listdir
    with monkeypatch.context() as patch:
        patch.setattr(
            core.os, "listdir",
            lambda *args, **kwargs: pytest.fail("unbounded listdir called"),
        )
        descriptor, directory_chain = core._open_snapshot_directory(
            root, label="synthetic"
        )
        try:
            assert core._bounded_snapshot_names(
                descriptor, maximum=3, label="synthetic"
            ) == ("a", "m", "z")
            copy = tmp_path / "copy"
            core._snapshot_directory_tree(root, copy, label="synthetic")
        finally:
            core._close_snapshot_directory(root, directory_chain, label="synthetic")
    assert original_listdir is core.os.listdir
    assert sorted(path.name for path in copy.iterdir()) == ["a", "m", "z"]


def test_bounded_scan_stops_after_first_excess_entry(tmp_path, monkeypatch):
    """Do not collect/sort an adversarial directory before checking the cap."""
    root = tmp_path / "synthetic"
    for index in range(30):
        _write(root, f"{index:04d}.csv", b"x")
    original_scandir = core.os.scandir
    observed = []

    class GuardedScanner:
        def __init__(self, iterator):
            self.iterator = iterator

        def __enter__(self):
            self.iterator.__enter__()
            return self

        def __exit__(self, *args):
            return self.iterator.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            observed.append(1)
            if len(observed) > 4:
                pytest.fail("read past the first entry over the scan cap")
            return next(self.iterator)

    def limited_scandir(path):
        iterator = original_scandir(path)
        if isinstance(path, int) and (
            core.os.fstat(path).st_dev, core.os.fstat(path).st_ino
        ) == (root.stat().st_dev, root.stat().st_ino):
            return GuardedScanner(iterator)
        return iterator

    with monkeypatch.context() as patch:
        patch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_ENTRIES", 3)
        patch.setattr(core.os, "scandir", limited_scandir)
        patch.setattr(
            core.os, "listdir",
            lambda *args, **kwargs: pytest.fail("unbounded listdir called"),
        )
        with pytest.raises(ValueError, match="freeze snapshot entry limit"):
            core._snapshot_directory_tree(root, tmp_path / "copy", label="synthetic")
    assert len(observed) == 4
    assert not (tmp_path / "copy").exists()


def test_inventory_scan_rejects_overflow_without_listdir(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    for index in range(4):
        _write(root, f"{index}.csv", b"x")
    with monkeypatch.context() as patch:
        patch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_ENTRIES", 3)
        patch.setattr(
            core.os, "listdir",
            lambda *args, **kwargs: pytest.fail("unbounded listdir called"),
        )
        descriptor, directory_chain = core._open_snapshot_directory(
            root, label="synthetic"
        )
        try:
            with pytest.raises(ValueError, match="freeze snapshot entry limit"):
                core._snapshot_directory_inventory(root, descriptor, label="synthetic")
        finally:
            core._close_snapshot_directory(root, directory_chain, label="synthetic")



def test_snapshot_directory_close_rejects_ancestor_swap_and_releases_every_fd(tmp_path):
    """Even a failed ancestry recheck must release the entire pinned chain."""
    ancestor = tmp_path / "original"
    root = ancestor / "nested"
    root.mkdir(parents=True)
    descriptor, directory_chain = core._open_snapshot_directory(
        root, label="synthetic"
    )
    assert descriptor == directory_chain[-1]
    assert all(core.os.fstat(fd).st_ino for fd in directory_chain)

    displaced = tmp_path / "relocated"
    ancestor.rename(displaced)
    ancestor.symlink_to(displaced, target_is_directory=True)
    with pytest.raises(ValueError, match="ancestor directory changed during capture"):
        core._close_snapshot_directory(root, directory_chain, label="synthetic")
    for fd in directory_chain:
        with pytest.raises(OSError, match="Bad file descriptor"):
            core.os.fstat(fd)


def test_freeze_root_rejects_overflow_before_inventory_or_copy(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-freeze"
    for index in range(4):
        _write(root, f"{index}.csv", b"x")
    destination = tmp_path / "copy"
    with monkeypatch.context() as patch:
        patch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_TREE_ENTRIES", 3)
        patch.setattr(
            core.os, "listdir",
            lambda *args, **kwargs: pytest.fail("unbounded listdir called"),
        )
        with pytest.raises(ValueError, match="freeze snapshot entry limit"):
            core._snapshot_freeze_tree(root, destination)
    assert not destination.exists()


def test_provenance_scan_rejects_sidecars_before_copy(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-freeze"
    for index in range(3):
        _write(root, f"provenance/{index}.py", b"x")
    destination = tmp_path / "copy"
    with monkeypatch.context() as patch:
        patch.setattr(
            core.os, "listdir",
            lambda *args, **kwargs: pytest.fail("unbounded listdir called"),
        )
        with pytest.raises(ValueError, match="provenance archive contents mismatch"):
            core._snapshot_freeze_tree(root, destination)
    assert not destination.exists()
