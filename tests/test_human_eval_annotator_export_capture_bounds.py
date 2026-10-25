"""Synthetic bounds and identity regressions for annotator distribution reads.

No real annotators, ratings, treatment calls, or human outcomes are involved.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as packet
from scripts import export_human_eval_annotator_bundle as exporter


def _file(tmp_path: Path, *, content: bytes = b"synthetic evidence\n") -> Path:
    path = tmp_path / "input.jsonl"
    path.write_bytes(content)
    return path


def test_bounded_reader_preserves_unchanged_evidence(tmp_path):
    path = _file(tmp_path)
    assert exporter._regular_bytes(path, label="synthetic input") == path.read_bytes()


@pytest.mark.parametrize("oversized_name", exporter.COORDINATOR_ARTIFACTS)
def test_coordinator_snapshot_rejects_oversized_artifact(tmp_path, oversized_name):
    source = tmp_path / "coordinator"
    target = tmp_path / "scratch"
    source.mkdir()
    target.mkdir()
    for name in exporter.COORDINATOR_ARTIFACTS:
        with (source / name).open("wb") as handle:
            if name == oversized_name:
                # Sparse size probe: no 64 MiB allocation or treatment run.
                handle.truncate(packet.MAX_PACKET_CAPTURE_BYTES + 1)
            else:
                handle.write(b"synthetic")
    with pytest.raises(ValueError, match="packet-capture limit"):
        exporter._snapshot_coordinator_bundle(source, target)


def test_standalone_verifier_rejects_oversized_annotator_packet(tmp_path):
    root = tmp_path / "annotator"
    root.mkdir()
    for name in exporter.ANNOTATOR_ARTIFACTS:
        with (root / name).open("wb") as handle:
            if name == "packet.jsonl":
                handle.truncate(packet.MAX_PACKET_CAPTURE_BYTES + 1)
            else:
                handle.write(b"synthetic")
    with pytest.raises(ValueError, match="packet-capture limit"):
        exporter.verify_annotator_bundle(root)


def test_reader_rejects_symlinked_evidence(tmp_path):
    original = _file(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(original)
    with pytest.raises(ValueError, match="stable regular file"):
        exporter._regular_bytes(alias, label="synthetic input")


def test_reader_rejects_symlinked_parent(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    (original / "input.jsonl").write_bytes(b"synthetic")
    alias = tmp_path / "alias"
    alias.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="stable regular file"):
        exporter._regular_bytes(alias / "input.jsonl", label="synthetic input")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_reader_rejects_fifo_without_blocking(tmp_path):
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    with pytest.raises(ValueError, match="regular file"):
        exporter._regular_bytes(pipe, label="synthetic input")


def _interrupt_after_initial_read(monkeypatch, path: Path, mutate):
    original_read = packet.os.read
    stat_before = path.stat()
    identity = (stat_before.st_dev, stat_before.st_ino)
    intervened = []

    def read_with_interference(descriptor, count):
        content = original_read(descriptor, count)
        opened = packet.os.fstat(descriptor)
        if (
            content
            and not intervened
            and (opened.st_dev, opened.st_ino) == identity
        ):
            mutate()
            intervened.append(True)
        return content

    monkeypatch.setattr(packet.os, "read", read_with_interference)
    return intervened


def test_reader_rejects_growth_during_capture(tmp_path, monkeypatch):
    path = _file(tmp_path)
    def append():
        with path.open("ab") as handle:
            handle.write(b"another synthetic observation\n")
    events = _interrupt_after_initial_read(monkeypatch, path, append)
    with pytest.raises(ValueError, match="changed during capture"):
        exporter._regular_bytes(path, label="synthetic input")
    assert events == [True]


def test_reader_rejects_same_byte_path_replacement(tmp_path, monkeypatch):
    path = _file(tmp_path)
    original_bytes = path.read_bytes()
    detached = tmp_path / "detached.jsonl"
    def replace():
        path.rename(detached)
        path.write_bytes(original_bytes)
    events = _interrupt_after_initial_read(monkeypatch, path, replace)
    with pytest.raises(ValueError, match="replaced during capture"):
        exporter._regular_bytes(path, label="synthetic input")
    assert events == [True]


def test_reader_rejects_truncation_during_capture(tmp_path, monkeypatch):
    path = _file(tmp_path)
    events = _interrupt_after_initial_read(monkeypatch, path, lambda: path.write_bytes(b""))
    with pytest.raises(ValueError, match="replaced during capture|changed during capture"):
        exporter._regular_bytes(path, label="synthetic input")
    assert events == [True]


def test_reader_rejects_parent_replacement(tmp_path, monkeypatch):
    parent = tmp_path / "evidence"
    parent.mkdir()
    path = parent / "input.jsonl"
    path.write_bytes(b"synthetic evidence\n")
    detached_parent = tmp_path / "detached"
    def replace_parent():
        parent.rename(detached_parent)
        parent.mkdir()
        (parent / "input.jsonl").write_bytes(b"synthetic evidence\n")
    events = _interrupt_after_initial_read(monkeypatch, path, replace_parent)
    with pytest.raises(ValueError, match="replaced during capture"):
        exporter._regular_bytes(path, label="synthetic input")
    assert events == [True]
