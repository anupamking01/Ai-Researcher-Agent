"""Synthetic-only bounded input-capture tests for the blinded rating freeze.

These tests never generate or claim human annotations. They exercise the shared
producer/independent-verifier descriptor reader without changing frozen rubrics.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as verifier


def _capture(path: Path) -> bytes:
    return freeze._capture_regular_input(path, label="synthetic rating")


def test_small_regular_input_is_captured_without_mutation(tmp_path):
    path = tmp_path / "ratings.csv"
    payload = b"synthetic ratings\r\n"
    path.write_bytes(payload)
    before = path.stat()
    assert _capture(path) == payload
    assert (path.stat().st_size, path.stat().st_mtime_ns) == (
        before.st_size, before.st_mtime_ns
    )


def test_empty_regular_input_has_a_bounded_capture(tmp_path):
    path = tmp_path / "empty.csv"
    path.touch()
    assert _capture(path) == b""


def test_exact_capture_limit_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "MAX_HUMAN_FREEZE_INPUT_BYTES", 8)
    path = tmp_path / "exact.csv"
    path.write_bytes(b"12345678")
    assert _capture(path) == b"12345678"


def test_oversize_rejected_before_any_content_read(tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "MAX_HUMAN_FREEZE_INPUT_BYTES", 8)
    path = tmp_path / "oversize.csv"
    # A sparse file proves the stat gate works without allocating a huge input.
    with path.open("wb") as output:
        output.truncate(9)

    def must_not_read(*args, **kwargs):
        raise AssertionError("oversized input was read")

    monkeypatch.setattr(freeze.os, "pread", must_not_read)
    with pytest.raises(ValueError, match="exceeds 8 byte"):
        _capture(path)


def test_independent_verifier_inherits_the_same_size_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "MAX_HUMAN_FREEZE_INPUT_BYTES", 4)
    path = tmp_path / "retained.csv"
    path.write_bytes(b"12345")
    with pytest.raises(ValueError, match="exceeds 4 byte"):
        verifier._require_regular_file(path, label="retained ratings")


def test_short_descriptor_reads_are_joined_without_dropping_bytes(tmp_path, monkeypatch):
    path = tmp_path / "short.csv"
    path.write_bytes(b"abcdefgh")
    real_pread = os.pread

    def short_pread(descriptor, size, offset):
        return real_pread(descriptor, min(size, 2), offset)

    monkeypatch.setattr(freeze.os, "pread", short_pread)
    assert _capture(path) == b"abcdefgh"


def test_mid_capture_truncation_fails_explicitly(tmp_path, monkeypatch):
    path = tmp_path / "truncate.csv"
    path.write_bytes(b"abcdefgh")
    real_pread = os.pread
    changed = False

    def truncate_after_short_read(descriptor, size, offset):
        nonlocal changed
        if not changed and offset == 0:
            first = real_pread(descriptor, 1, 0)
            path.write_bytes(b"")
            changed = True
            return first
        return real_pread(descriptor, size, offset)

    monkeypatch.setattr(freeze.os, "pread", truncate_after_short_read)
    with pytest.raises(ValueError, match="truncated while it was being read"):
        _capture(path)
    assert changed


def test_append_after_initial_snapshot_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "append.csv"
    path.write_bytes(b"abcd")
    real_pread = os.pread
    appended = False

    def append_after_first_read(descriptor, size, offset):
        nonlocal appended
        captured = real_pread(descriptor, size, offset)
        if offset == 0 and captured and not appended:
            with path.open("ab") as output:
                output.write(b"e")
            appended = True
        return captured

    monkeypatch.setattr(freeze.os, "pread", append_after_first_read)
    with pytest.raises(ValueError, match="grew while it was being read"):
        _capture(path)
    assert appended


def test_continuously_growing_source_never_causes_an_eof_read_loop(
    tmp_path, monkeypatch
):
    path = tmp_path / "growing.csv"
    path.write_bytes(b"abcd")
    real_pread = os.pread
    calls = 0

    def adversarial_pread(descriptor, size, offset):
        nonlocal calls
        calls += 1
        if calls > 5:
            raise AssertionError("unbounded read over continuously growing file")
        captured = real_pread(descriptor, size, offset)
        with path.open("ab") as output:
            output.write(b"x")
        return captured

    monkeypatch.setattr(freeze.os, "pread", adversarial_pread)
    with pytest.raises(ValueError, match="grew while it was being read"):
        _capture(path)
    assert calls == 2


def test_same_byte_path_replacement_is_not_accepted(tmp_path, monkeypatch):
    path = tmp_path / "ratings.csv"
    replacement = tmp_path / "replacement.csv"
    path.write_bytes(b"unchanged")
    replacement.write_bytes(b"unchanged")
    original_pread = os.pread
    replaced = False

    def replace_after_capture(descriptor, size, offset):
        nonlocal replaced
        captured = original_pread(descriptor, size, offset)
        if offset == 0 and captured and not replaced:
            os.replace(replacement, path)
            replaced = True
        return captured

    monkeypatch.setattr(freeze.os, "pread", replace_after_capture)
    with pytest.raises(ValueError, match="changed while it was being read"):
        _capture(path)
    assert replaced


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO only")
def test_named_pipe_is_rejected_without_waiting_for_a_writer(tmp_path):
    path = tmp_path / "synthetic-rating.fifo"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="must be a regular file"):
        _capture(path)


def test_leaf_symlink_is_rejected(tmp_path):
    genuine = tmp_path / "genuine.csv"
    genuine.write_bytes(b"abc")
    linked = tmp_path / "linked.csv"
    try:
        linked.symlink_to(genuine)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="must be a regular file"):
        _capture(linked)
