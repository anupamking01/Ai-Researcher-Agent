"""Synthetic regression coverage for full ancestor custody in human analysis.

The capture must never follow an indirect source symlink, including for
blinded pre-unblinding evidence and the later coordinator mapping. No real
human ratings or experimental outcomes are loaded or generated.
"""
import os
from pathlib import Path

import pytest

from scripts import human_eval_analysis_core as core


def test_direct_input_rejects_indirect_ancestor_symlink_before_read(
    tmp_path: Path, monkeypatch,
):
    real = tmp_path / "real"
    parent = real / "nested" / "ratings"
    parent.mkdir(parents=True)
    (parent / "synthetic.csv").write_bytes(b"synthetic ratings\n")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    monkeypatch.setattr(
        core.os, "pread",
        lambda *args: pytest.fail("indirectly aliased source must not be read"),
    )
    destination = tmp_path / "scratch" / "ratings.csv"
    with pytest.raises(ValueError, match="parent must be a regular directory"):
        core._snapshot_file(
            alias / "nested" / "ratings" / "synthetic.csv",
            destination,
            label="synthetic raw rating",
        )
    assert not destination.exists()


@pytest.mark.parametrize("capture", ["tree", "freeze"])
def test_freeze_archive_rejects_indirect_ancestor_symlink(
    tmp_path: Path, capture: str,
):
    real = tmp_path / "real"
    archive = real / "nested" / "frozen-v1"
    archive.mkdir(parents=True)
    (archive / "agreement.json").write_text('{"synthetic":true}', encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    source = alias / "nested" / "frozen-v1"
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="must be a regular directory"):
        if capture == "tree":
            core._snapshot_directory_tree(source, destination, label="synthetic freeze")
        else:
            core._snapshot_freeze_tree(source, destination)
    assert not destination.exists()


def test_direct_input_rejects_ancestor_replaced_during_read(
    tmp_path: Path, monkeypatch,
):
    ancestor = tmp_path / "archive"
    parent = ancestor / "nested"
    parent.mkdir(parents=True)
    source = parent / "synthetic.csv"
    source.write_bytes(b"synthetic ratings\n")
    moved = tmp_path / "archive-held"
    destination = tmp_path / "scratch" / "ratings.csv"
    original_pread = os.pread
    swapped = []

    def swap_after_read(fd, requested, offset):
        data = original_pread(fd, requested, offset)
        if not swapped and offset == 0:
            ancestor.rename(moved)
            ancestor.symlink_to(moved, target_is_directory=True)
            swapped.append(True)
        return data

    monkeypatch.setattr(core.os, "pread", swap_after_read)
    with pytest.raises(ValueError, match="ancestor directory changed during capture"):
        core._snapshot_file(source, destination, label="synthetic raw rating")
    assert swapped == [True]
    assert not destination.exists()


def test_directory_tree_rejects_ancestor_replaced_during_copy(
    tmp_path: Path, monkeypatch,
):
    ancestor = tmp_path / "archive"
    root = ancestor / "nested" / "frozen-v1"
    root.mkdir(parents=True)
    (root / "agreement.json").write_bytes(b"synthetic agreement")
    moved = tmp_path / "archive-held"
    destination = tmp_path / "scratch"
    original_copy = core._snapshot_tree_file
    swapped = []

    def swap_after_copy(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        if not swapped:
            ancestor.rename(moved)
            ancestor.symlink_to(moved, target_is_directory=True)
            swapped.append(True)
        return result

    monkeypatch.setattr(core, "_snapshot_tree_file", swap_after_copy)
    with pytest.raises(ValueError, match="ancestor directory changed during capture"):
        core._snapshot_directory_tree(root, destination, label="synthetic freeze")
    assert swapped == [True]


def test_nested_regular_sources_remain_supported(tmp_path: Path):
    directory = tmp_path / "real" / "nested"
    directory.mkdir(parents=True)
    source = directory / "ratings.csv"
    source.write_bytes(b"synthetic ratings")
    destination = tmp_path / "direct" / "ratings.csv"
    core._snapshot_file(source, destination, label="synthetic rating")
    assert destination.read_bytes() == b"synthetic ratings"
    archive = directory / "frozen-v1"
    archive.mkdir()
    (archive / "agreement.json").write_bytes(b"synthetic")
    tree = tmp_path / "archive-copy"
    core._snapshot_directory_tree(archive, tree, label="synthetic freeze")
    assert (tree / "agreement.json").read_bytes() == b"synthetic"
