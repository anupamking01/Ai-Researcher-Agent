"""Synthetic source-custody regressions for the exploratory influence CLI.

These test local descriptor safety only. They do not create research outcomes.
"""
import os

import pytest

from scripts import analyze_main_study_task_influence as influence


def test_bounded_regular_source_capture_is_unchanged(tmp_path):
    source = tmp_path / "source.json"
    payload = b'{"schema_version": 1, "study_id": "budget-main-v1"}'
    source.write_bytes(payload)
    assert influence._read_regular_bounded(source, label="inference") == payload


def test_empty_source_is_captured_without_spurious_growth(tmp_path):
    source = tmp_path / "empty.json"
    source.write_bytes(b"")
    assert influence._read_regular_bounded(source, label="inference") == b""


def test_symlinked_parent_is_not_used_to_select_an_ambient_source(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "source.json").write_bytes(b"{}")
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="regular directory"):
        influence._read_regular_bounded(alias / "source.json", label="inference")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_fifo_source_rejected_without_opening_or_blocking(tmp_path):
    source = tmp_path / "source.json"
    os.mkfifo(source)
    with pytest.raises(ValueError, match="regular file"):
        influence._read_regular_bounded(source, label="inference")


def test_identical_content_in_new_inode_cannot_replace_prechecked_source(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.json"
    replacement = tmp_path / "replacement.json"
    source.write_bytes(b'{"x":1}')
    replacement.write_bytes(source.read_bytes())
    real_open = os.open
    exchanged = []

    def swap_between_stat_and_open(name, flags, *args, **kwargs):
        if name == source.name and kwargs.get("dir_fd") is not None and not exchanged:
            os.replace(replacement, source)
            exchanged.append(True)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(influence.os, "open", swap_between_stat_and_open)
    with pytest.raises(ValueError, match="changed during source capture"):
        influence._read_regular_bounded(source, label="inference")
    assert exchanged


def test_symlink_swap_between_stat_and_open_fails_closed(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    outside = tmp_path / "outside.json"
    source.write_bytes(b"original")
    outside.write_bytes(b"outside")
    real_open = os.open
    exchanged = []

    def swap_to_symlink(name, flags, *args, **kwargs):
        if name == source.name and kwargs.get("dir_fd") is not None and not exchanged:
            source.unlink()
            source.symlink_to(outside)
            exchanged.append(True)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(influence.os, "open", swap_to_symlink)
    with pytest.raises(ValueError, match="changed during source capture"):
        influence._read_regular_bounded(source, label="inference")
    assert exchanged


def test_in_place_modification_during_descriptor_read_fails_closed(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.json"
    source.write_bytes(b"A" * 128)
    real_pread = os.pread
    mutated = []

    def write_while_reading(fd, size, offset):
        chunk = real_pread(fd, size, offset)
        if not mutated and offset == 0:
            source.write_bytes(b"B" * 128)
            mutated.append(True)
        return chunk

    monkeypatch.setattr(influence.os, "pread", write_while_reading)
    with pytest.raises(ValueError, match="changed during source capture"):
        influence._read_regular_bounded(source, label="inference")
    assert mutated


def test_same_bytes_replaced_after_descriptor_capture_fails_closed(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.json"
    replacement = tmp_path / "replacement.json"
    source.write_bytes(b'{"same":"bytes"}')
    replacement.write_bytes(source.read_bytes())
    real_stat = os.stat
    inspected = []

    def swap_before_final_path_check(name, *args, **kwargs):
        if name == source.name and kwargs.get("dir_fd") is not None:
            inspected.append(True)
            if len(inspected) == 2:
                os.replace(replacement, source)
        return real_stat(name, *args, **kwargs)

    monkeypatch.setattr(influence.os, "stat", swap_before_final_path_check)
    with pytest.raises(ValueError, match="changed during source capture"):
        influence._read_regular_bounded(source, label="inference")
    assert len(inspected) == 2
