"""Synthetic-only ancestor-custody regressions for retained CI evidence.

No treatment, common evaluator, external service, or human rating is invoked.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import verify_ci_test_evidence as evidence


def test_nested_regular_ci_capture_remains_byte_exact(tmp_path):
    directory = tmp_path / "checkout" / "evidence"
    directory.mkdir(parents=True)
    log = directory / "pytest.log"
    log.write_bytes(b"source-bound synthetic record\r\n")
    assert evidence.read_bounded_evidence(
        log, maximum=64, label="synthetic CI log"
    ) == b"source-bound synthetic record\r\n"


def test_ci_capture_refuses_symlinked_ancestor_even_for_regular_leaf(tmp_path):
    real = tmp_path / "physical-evidence"
    real.mkdir()
    (real / "log.txt").write_bytes(b"identical and regular")
    (tmp_path / "redirect").symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="regular file|no-follow"):
        evidence.read_bounded_evidence(
            tmp_path / "redirect" / "log.txt",
            maximum=64, label="synthetic CI log",
        )
    # The canonical path is independently acceptable; only the alias fails.
    assert evidence.read_bounded_evidence(
        real / "log.txt", maximum=64, label="synthetic CI log"
    ) == b"identical and regular"


def test_ci_capture_refuses_same_byte_ancestor_replacement_during_read(
    tmp_path, monkeypatch,
):
    original = tmp_path / "retained"
    original.mkdir()
    leaf = original / "receipt.json"
    leaf.write_bytes(b"same evidence bytes")
    original_fdopen = os.fdopen

    class ReparentingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def read(self, count):
            data = self.stream.read(count)
            original.rename(tmp_path / "old-retained")
            original.mkdir()
            (original / "receipt.json").write_bytes(data)
            return data

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

    monkeypatch.setattr(
        evidence.os, "fdopen",
        lambda fd, mode, closefd=False: ReparentingReader(
            original_fdopen(fd, mode, closefd=closefd)
        ),
    )
    with pytest.raises(ValueError, match="parent directory changed during capture"):
        evidence.read_bounded_evidence(
            leaf, maximum=64, label="synthetic CI receipt",
        )


def test_ci_capture_rejects_parent_traversal_before_read(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "log.txt").write_bytes(b"unchanged")
    with pytest.raises(ValueError, match="parent traversal"):
        evidence.read_bounded_evidence(
            real / ".." / "real" / "log.txt",
            maximum=64, label="synthetic CI log",
        )


def test_early_ci_producer_reuses_same_ancestor_bound_reader():
    from scripts import verify_ci_early_gate_evidence as early
    assert early.read_bounded_evidence is evidence.read_bounded_evidence
