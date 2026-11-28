"""Fail-closed hardlink custody checks for synthetic human-analysis inputs.

A hardlink outside an archived freeze tree can mutate the same inode through
a pathname the recursive inventory never sees. No human scores are used.
"""
import os
from pathlib import Path

import pytest

from scripts import human_eval_analysis_core as core


def test_direct_rating_source_rejects_external_hardlink_before_read(
    tmp_path: Path, monkeypatch,
):
    source = tmp_path / "raw-ratings.csv"
    source.write_bytes(b"synthetic ratings")
    os.link(source, tmp_path / "external-rating-alias.csv")
    destination = tmp_path / "scratch" / source.name

    monkeypatch.setattr(
        core.os, "pread",
        lambda *args: pytest.fail("aliased rating source must not be read"),
    )
    with pytest.raises(ValueError, match="single-link"):
        core._snapshot_file(source, destination, label="synthetic raw ratings")
    assert not destination.exists()


def test_recursive_freeze_file_rejects_external_hardlink_before_read(
    tmp_path: Path, monkeypatch,
):
    archive = tmp_path / "synthetic-freeze"
    nested = archive / "raw_rating_inputs"
    nested.mkdir(parents=True)
    source = nested / "0001.csv"
    source.write_bytes(b"synthetic frozen ratings")
    os.link(source, tmp_path / "outside-freeze.csv")

    monkeypatch.setattr(
        core.os, "pread",
        lambda *args: pytest.fail("aliased freeze source must not be read"),
    )
    with pytest.raises(ValueError, match="single-link"):
        core._snapshot_directory_tree(
            archive, tmp_path / "scratch-freeze", label="synthetic freeze"
        )


def test_direct_rating_hardlink_created_during_capture_fails(
    tmp_path: Path, monkeypatch,
):
    source = tmp_path / "rating.csv"
    source.write_bytes(b"synthetic")
    destination = tmp_path / "scratch" / source.name
    original_pread = os.pread
    linked = []

    def link_after_first_read(fd, requested, offset):
        chunk = original_pread(fd, requested, offset)
        if not linked and offset == 0:
            os.link(source, tmp_path / "late-rating-alias.csv")
            linked.append(True)
        return chunk

    monkeypatch.setattr(core.os, "pread", link_after_first_read)
    with pytest.raises(ValueError, match="changed while it was being read"):
        core._snapshot_file(source, destination, label="synthetic raw rating")
    assert linked == [True]
    assert not destination.exists()


def test_recursive_freeze_hardlink_created_during_capture_fails(
    tmp_path: Path, monkeypatch,
):
    archive = tmp_path / "synthetic-freeze"
    archive.mkdir()
    source = archive / "agreement.json"
    source.write_bytes(b'{"synthetic":true}')
    original_pread = os.pread
    linked = []

    def link_after_first_read(fd, requested, offset):
        chunk = original_pread(fd, requested, offset)
        if not linked and offset == 0:
            os.link(source, tmp_path / "late-freeze-alias.json")
            linked.append(True)
        return chunk

    monkeypatch.setattr(core.os, "pread", link_after_first_read)
    with pytest.raises(ValueError, match="changed while it was being read"):
        core._snapshot_directory_tree(
            archive, tmp_path / "scratch-freeze", label="synthetic freeze"
        )
    assert linked == [True]


def test_single_link_synthetic_freeze_and_direct_rating_remain_supported(
    tmp_path: Path,
):
    direct = tmp_path / "rating.csv"
    direct.write_bytes(b"synthetic")
    direct_copy = tmp_path / "scratch" / "rating.csv"
    assert core._snapshot_file(direct, direct_copy, label="synthetic rating") == direct_copy
    assert direct_copy.read_bytes() == b"synthetic"

    archive = tmp_path / "synthetic-freeze"
    archive.mkdir()
    (archive / "agreement.json").write_bytes(b"not a real agreement")
    copy = tmp_path / "freeze-copy"
    core._snapshot_directory_tree(archive, copy, label="synthetic freeze")
    assert (copy / "agreement.json").read_bytes() == b"not a real agreement"
