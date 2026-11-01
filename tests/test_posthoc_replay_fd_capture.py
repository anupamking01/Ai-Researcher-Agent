"""Descriptor-pinned noncanonical evaluator source reads (synthetic/offline).

No model calls or historical research artifacts are used.
"""
import os

import pytest

from scripts import evaluate_posthoc_support as evaluator


def test_read_ordinary_regular_source_and_byte_limit(tmp_path):
    path = tmp_path / "source.txt"
    path.write_bytes(b"evidence")
    assert evaluator._read_regular_bytes(
        path, label="Evaluator evidence", max_bytes=8
    ) == b"evidence"
    with pytest.raises(SystemExit, match="exceeds maximum 7 bytes"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=7
        )


def test_symlink_replacement_after_precheck_cannot_redirect_bytes(
    tmp_path, monkeypatch
):
    path = tmp_path / "source.txt"
    path.write_bytes(b"original")
    other = tmp_path / "unselected.txt"
    other.write_bytes(b"unselected")
    original_check = evaluator._require_regular_file

    def replace_after_check(selected, *, label):
        original_check(selected, label=label)
        path.unlink()
        path.symlink_to(other)

    monkeypatch.setattr(evaluator, "_require_regular_file", replace_after_check)
    with pytest.raises(SystemExit, match="Cannot read Evaluator evidence"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=64
        )


def test_parent_symlink_replacement_after_precheck_is_rejected(
    tmp_path, monkeypatch
):
    parent = tmp_path / "selected"
    parent.mkdir()
    path = parent / "source.txt"
    path.write_bytes(b"original")
    other = tmp_path / "unselected"
    other.mkdir()
    (other / "source.txt").write_bytes(b"unselected")
    original_check = evaluator._require_regular_file

    def replace_after_check(selected, *, label):
        original_check(selected, label=label)
        parent.rename(tmp_path / "moved")
        parent.symlink_to(other, target_is_directory=True)

    monkeypatch.setattr(evaluator, "_require_regular_file", replace_after_check)
    with pytest.raises(SystemExit, match="Cannot read Evaluator evidence"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=64
        )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_fifo_replacement_after_precheck_is_rejected_without_blocking(
    tmp_path, monkeypatch
):
    path = tmp_path / "source.txt"
    path.write_bytes(b"original")
    original_check = evaluator._require_regular_file

    def replace_after_check(selected, *, label):
        original_check(selected, label=label)
        path.unlink()
        os.mkfifo(path)

    monkeypatch.setattr(evaluator, "_require_regular_file", replace_after_check)
    with pytest.raises(SystemExit, match="must remain a regular file"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=64
        )


def test_in_place_growth_during_read_rejects_unstable_snapshot(
    tmp_path, monkeypatch
):
    path = tmp_path / "source.txt"
    path.write_bytes(b"original")
    original_fdopen = evaluator.os.fdopen

    def modify_after_descriptor_snapshot(fd, *args, **kwargs):
        with path.open("ab") as changed:
            changed.write(b"-altered")
            changed.flush()
            os.fsync(changed.fileno())
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(evaluator.os, "fdopen", modify_after_descriptor_snapshot)
    with pytest.raises(SystemExit, match="changed during read"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=64
        )
