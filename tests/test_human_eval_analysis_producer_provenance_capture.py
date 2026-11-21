"""Synthetic producer provenance capture checks; no ratings or treatments."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from scripts import analyze_human_eval as producer
from scripts import freeze_human_eval_ratings as freeze


def test_implementation_fingerprint_captures_exact_stable_source(tmp_path: Path):
    path = tmp_path / "synthetic_source.py"
    path.write_bytes(b"# synthetic module\\n")
    result = producer._implementation_fingerprint(
        path, logical_path="scripts/synthetic_source.py"
    )
    assert result == {
        "path": "scripts/synthetic_source.py",
        "bytes": len(path.read_bytes()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_oversized_producer_source_rejected_before_capture(tmp_path, monkeypatch):
    path = tmp_path / "oversized.py"
    with path.open("wb") as stream:
        stream.truncate(33)
    monkeypatch.setattr(producer, "MAX_HUMAN_ANALYSIS_SOURCE_BYTES", 32)

    def must_not_capture(*args, **kwargs):
        raise AssertionError("oversized source must be rejected before read")

    monkeypatch.setattr(freeze, "_capture_regular_input", must_not_capture)
    with pytest.raises(ValueError, match="exceeds 32 bytes"):
        producer._implementation_fingerprint(
            path, logical_path="scripts/synthetic_source.py"
        )


def test_producer_source_append_during_descriptor_read_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "mutating_source.py"
    path.write_bytes(b"# original synthetic source\\n")
    real_pread = os.pread
    changed = []

    def append_after_first_read(fd, count, offset):
        data = real_pread(fd, count, offset)
        if offset == 0 and not changed:
            with path.open("ab") as stream:
                stream.write(b"# appended while fingerprinting\\n")
            changed.append(True)
        return data

    monkeypatch.setattr(freeze.os, "pread", append_after_first_read)
    with pytest.raises(ValueError, match="(grew|changed) while it was being read"):
        producer._implementation_fingerprint(
            path, logical_path="scripts/mutating_source.py"
        )
    assert changed == [True]


def test_producer_rejects_symlink_source_before_hashing(tmp_path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_bytes(b"# synthetic\\n")
    path = tmp_path / "linked_source.py"
    path.symlink_to(target)

    def must_not_capture(*args, **kwargs):
        raise AssertionError("symlink source must not be read")

    monkeypatch.setattr(freeze, "_capture_regular_input", must_not_capture)
    with pytest.raises(ValueError, match="must be a regular file"):
        producer._implementation_fingerprint(
            path, logical_path="scripts/linked_source.py"
        )
