"""Synthetic safety regressions for bounded blinded human-analysis snapshots.

No test loads collected human annotations, canonical inference data, or a
coordinator's real treatment mapping.
"""
import os
from pathlib import Path

import pytest

from scripts import human_eval_analysis_core as core


def test_snapshot_limit_is_a_fixed_safety_boundary():
    assert core.MAX_HUMAN_ANALYSIS_SNAPSHOT_FILE_BYTES == 16 * 1024 * 1024


def test_regular_snapshot_accepts_exact_byte_limit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_FILE_BYTES", 32)
    source = tmp_path / "input.csv"
    source.write_bytes(b"x" * 32)
    destination = tmp_path / "isolated" / "input.csv"

    assert core._snapshot_file(source, destination, label="synthetic CSV") == destination
    assert destination.read_bytes() == source.read_bytes()


def test_regular_snapshot_rejects_oversized_sparse_source_before_pread(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_FILE_BYTES", 32)
    source = tmp_path / "oversized.csv"
    with source.open("wb") as handle:
        handle.truncate(33)
    destination = tmp_path / "isolated" / "oversized.csv"

    def forbidden_pread(*args):
        raise AssertionError("oversized source should not be read")

    monkeypatch.setattr(core.os, "pread", forbidden_pread)
    with pytest.raises(ValueError, match="human-analysis snapshot limit"):
        core._snapshot_file(source, destination, label="synthetic CSV")
    assert not destination.exists()
    assert not destination.parent.exists()


def test_recursive_freeze_snapshot_rejects_oversized_nested_file_before_pread(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_FILE_BYTES", 32)
    archive = tmp_path / "synthetic-freeze"
    nested = archive / "submission_preflights" / "0001" / "receipt"
    nested.mkdir(parents=True)
    with (nested / "preflight_receipt.json").open("wb") as handle:
        handle.truncate(33)

    def forbidden_pread(*args):
        raise AssertionError("oversized archived source should not be read")

    monkeypatch.setattr(core.os, "pread", forbidden_pread)
    with pytest.raises(ValueError, match="human-analysis snapshot limit"):
        core._snapshot_directory_tree(
            archive, tmp_path / "scratch-freeze", label="synthetic freeze"
        )


def test_recursive_freeze_snapshot_preserves_exact_limit_file(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(core, "MAX_HUMAN_ANALYSIS_SNAPSHOT_FILE_BYTES", 32)
    archive = tmp_path / "synthetic-freeze"
    archive.mkdir()
    (archive / "agreement.json").write_bytes(b"a" * 32)
    (archive / "frozen_ratings.csv").write_bytes(b"b" * 8)
    snapshot = tmp_path / "scratch-freeze"
    core._snapshot_directory_tree(archive, snapshot, label="synthetic freeze")
    assert (snapshot / "agreement.json").read_bytes() == b"a" * 32
    assert (snapshot / "frozen_ratings.csv").read_bytes() == b"b" * 8


def test_regular_snapshot_rejects_observed_append_without_copying(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "blinded-packet.jsonl"
    source.write_bytes(b"original")
    destination = tmp_path / "snapshot" / source.name
    real_pread = core.os.pread
    appended = []

    def append_after_first_read(fd, size, offset):
        result = real_pread(fd, size, offset)
        if offset == 0 and not appended:
            with source.open("ab") as handle:
                handle.write(b"-extra")
            appended.append(True)
        return result

    monkeypatch.setattr(core.os, "pread", append_after_first_read)
    with pytest.raises(ValueError, match="changed while it was being read"):
        core._snapshot_file(source, destination, label="synthetic packet")
    assert appended == [True]
    assert not destination.exists()


def test_regular_snapshot_rejects_premature_end_of_file(tmp_path: Path, monkeypatch):
    source = tmp_path / "blinded.csv"
    source.write_bytes(b"12345678")
    destination = tmp_path / "snapshot" / source.name
    real_pread = core.os.pread

    def short_read(fd, size, offset):
        if offset == 0:
            return real_pread(fd, 3, offset)
        return b""

    monkeypatch.setattr(core.os, "pread", short_read)
    with pytest.raises(ValueError, match="changed while it was being read"):
        core._snapshot_file(source, destination, label="synthetic ratings")
    assert not destination.exists()


def test_bounded_reader_never_requests_unbounded_growth(tmp_path: Path, monkeypatch):
    source = tmp_path / "growing.csv"
    source.write_bytes(b"12345678")
    destination = tmp_path / "scratch" / source.name
    requested = []
    real_pread = core.os.pread

    def track_growth(fd, length, offset):
        requested.append((length, offset))
        result = real_pread(fd, length, offset)
        if offset == 0:
            with source.open("ab") as handle:
                handle.write(b"9" * 64)
        return result

    monkeypatch.setattr(core.os, "pread", track_growth)
    with pytest.raises(ValueError, match="changed while it was being read"):
        core._snapshot_file(source, destination, label="synthetic ratings")
    assert requested == [(8, 0), (1, 8)]
    assert not destination.exists()
