"""Synthetic resource-boundary regressions for human-analysis output custody.

This does not create or analyze human ratings and does not touch frozen data.
"""
from __future__ import annotations

import os

import pytest

from scripts import analyze_human_eval as producer
from scripts import verify_human_eval_analysis_outputs as verifier


def _capture(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        return verifier._regular_snapshot_from_descriptor(
            descriptor, label="synthetic analysis artifact"
        )
    finally:
        os.close(descriptor)


def test_producer_and_verifier_share_one_output_byte_limit():
    assert producer.MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES == 16 * 1024 * 1024


@pytest.mark.parametrize("size", [0, 1, 128])
def test_descriptor_snapshot_accepts_exact_boundary(tmp_path, monkeypatch, size):
    monkeypatch.setattr(producer, "MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES", 128)
    path = tmp_path / "output.json"
    path.write_bytes(b"x" * size)
    captured, identity = _capture(path)
    assert captured == b"x" * size
    assert identity[2] == size


def test_oversized_sparse_output_rejected_without_read(tmp_path, monkeypatch):
    monkeypatch.setattr(producer, "MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES", 128)
    path = tmp_path / "oversized"
    with path.open("wb") as handle:
        handle.truncate(129)

    def forbid_pread(*_args):
        raise AssertionError("oversized descriptor must be rejected before pread")

    monkeypatch.setattr(verifier.os, "pread", forbid_pread)
    with pytest.raises(ValueError, match="exceeds 128 bytes"):
        _capture(path)


def test_snapshot_rejects_append_during_capture(tmp_path, monkeypatch):
    path = tmp_path / "growing"
    path.write_bytes(b"abc")
    real_pread = os.pread
    appended = False

    def append_after_first_read(fd, count, offset):
        nonlocal appended
        chunk = real_pread(fd, count, offset)
        if not appended:
            appended = True
            with path.open("ab") as handle:
                handle.write(b"d")
        return chunk

    monkeypatch.setattr(verifier.os, "pread", append_after_first_read)
    with pytest.raises(ValueError, match="changed while it was being read"):
        _capture(path)


def test_snapshot_rejects_early_eof(tmp_path, monkeypatch):
    path = tmp_path / "truncated"
    path.write_bytes(b"abc")
    real_pread = os.pread

    def early_eof(fd, count, offset):
        return b"" if offset else real_pread(fd, 1, offset)

    monkeypatch.setattr(verifier.os, "pread", early_eof)
    with pytest.raises(ValueError, match="changed while it was being read"):
        _capture(path)


def test_snapshot_never_requests_unbounded_read(tmp_path, monkeypatch):
    monkeypatch.setattr(producer, "MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES", 128)
    path = tmp_path / "bounded"
    path.write_bytes(b"a" * 128)
    real_pread = os.pread
    requests = []

    def watch(fd, count, offset):
        requests.append((count, offset))
        return real_pread(fd, count, offset)

    monkeypatch.setattr(verifier.os, "pread", watch)
    assert _capture(path)[0] == b"a" * 128
    assert requests == [(128, 0), (1, 128)]


def test_producer_rejects_large_json_before_reserving_output(tmp_path, monkeypatch):
    monkeypatch.setattr(producer, "MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES", 128)
    output = tmp_path / "not-created" / "analysis"
    with pytest.raises(ValueError, match="human-analysis JSON exceeds 128 bytes"):
        producer.write_bundle({"study_id": "synthetic", "padding": "x" * 256}, output)
    assert not output.parent.exists()


def test_producer_rejects_large_markdown_before_reserving_output(tmp_path, monkeypatch):
    monkeypatch.setattr(producer, "MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES", 128)
    monkeypatch.setattr(producer, "render_markdown", lambda _payload: "x" * 129)
    output = tmp_path / "not-created" / "analysis"
    with pytest.raises(ValueError, match="human-analysis Markdown exceeds 128 bytes"):
        producer.write_bundle({"study_id": "synthetic"}, output)
    assert not output.parent.exists()


def test_producer_rejects_large_manifest_before_reserving_output(tmp_path, monkeypatch):
    monkeypatch.setattr(producer, "MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES", 4096)
    monkeypatch.setattr(producer, "render_markdown", lambda _payload: "small")
    monkeypatch.setattr(producer, "ANALYSIS_INTEGRITY_NOTE", "x" * 8192)
    monkeypatch.setattr(verifier, "_validate_analysis_identity", lambda _payload: None)
    output = tmp_path / "not-created" / "analysis"
    with pytest.raises(ValueError, match="human-analysis output manifest exceeds 4096 bytes"):
        producer.write_bundle({"study_id": "synthetic"}, output)
    assert not output.parent.exists()
