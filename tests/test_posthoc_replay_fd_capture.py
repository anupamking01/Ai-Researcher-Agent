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
def test_regular_file_swap_before_open_is_rejected(tmp_path, monkeypatch):
    """A same-sized replacement after precheck must not be silently consumed."""
    path = tmp_path / "source.txt"
    path.write_bytes(b"original")
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"altered!")
    original_open = evaluator.os.open
    swapped = False

    def swap_after_parent_open(selected, flags, *args, **kwargs):
        nonlocal swapped
        fd = original_open(selected, flags, *args, **kwargs)
        if (
            not swapped
            and os.fspath(selected) == os.fspath(tmp_path)
            and flags & os.O_DIRECTORY
        ):
            os.replace(replacement, path)
            swapped = True
        return fd

    monkeypatch.setattr(evaluator.os, "open", swap_after_parent_open)
    with pytest.raises(SystemExit, match="source pathname changed before read"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=64
        )
    assert swapped


def test_regular_file_swap_after_open_is_rejected_even_for_identical_bytes(
    tmp_path, monkeypatch
):
    """Descriptor bytes can remain identical while visible file custody changes."""
    path = tmp_path / "source.txt"
    path.write_bytes(b"same-bytes")
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"same-bytes")
    original_fdopen = evaluator.os.fdopen

    def swap_before_read(fd, *args, **kwargs):
        os.replace(replacement, path)
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(evaluator.os, "fdopen", swap_before_read)
    with pytest.raises(SystemExit, match="source pathname changed during read"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=64
        )


def test_regular_parent_directory_swap_during_read_is_rejected(
    tmp_path, monkeypatch
):
    """Reading from an open old directory does not validate its new pathname."""
    parent = tmp_path / "selected"
    parent.mkdir()
    path = parent / "source.txt"
    path.write_bytes(b"original")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "source.txt").write_bytes(b"original")
    original_fdopen = evaluator.os.fdopen

    def swap_directory_before_read(fd, *args, **kwargs):
        parent.rename(tmp_path / "moved")
        replacement.rename(parent)
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(evaluator.os, "fdopen", swap_directory_before_read)
    with pytest.raises(SystemExit, match="directory pathname changed during read"):
        evaluator._read_regular_bytes(
            path, label="Evaluator evidence", max_bytes=64
        )
