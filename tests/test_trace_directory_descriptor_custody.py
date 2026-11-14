"""Fail-closed POSIX directory identity checks for experimental trace custody.

All data are synthetic; no experiment treatments are executed.
"""
import os
import stat
from pathlib import Path

import pytest

from logic.experiment import ExperimentConfig, save_run_trace


def _config(tmp_path):
    return ExperimentConfig(
        variant_id="D3",
        planning_mode="direct",
        source_budget=3,
        verification_mode="none",
        trace_root=str(tmp_path / "traces"),
    )


def _publish(config):
    return save_run_trace(
        trace={"run_id": "synthetic-run", "source_count": 2},
        config=config,
        run_id="synthetic-run",
    )


def test_directory_entries_are_fsynced_after_publish_and_cleanup(
    tmp_path, monkeypatch
):
    actual_fsync = os.fsync
    observed_directory_fsyncs = []

    def observe_fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            observed_directory_fsyncs.append(fd)
        return actual_fsync(fd)

    monkeypatch.setattr(os, "fsync", observe_fsync)
    path = Path(_publish(_config(tmp_path)))
    assert path.exists()
    assert len(observed_directory_fsyncs) >= 2
    assert list(path.parent.iterdir()) == [path]


def test_hard_link_names_are_anchored_to_same_open_directory(tmp_path, monkeypatch):
    actual_link = os.link
    observed = []

    def check_link(source, dest, **kwargs):
        observed.append((source, dest, kwargs))
        assert kwargs["src_dir_fd"] == kwargs["dst_dir_fd"]
        assert kwargs["follow_symlinks"] is False
        assert "/" not in source and "/" not in dest
        return actual_link(source, dest, **kwargs)

    monkeypatch.setattr(os, "link", check_link)
    assert Path(_publish(_config(tmp_path))).is_file()
    assert len(observed) == 1


def test_variant_replaced_by_external_symlink_mid_publication_fails_closed(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "traces"
    variant = root / "D3"
    renamed = root / "renamed-original"
    actual_link = os.link

    def swap_variant(source, dest, **kwargs):
        variant.rename(renamed)
        variant.symlink_to(outside, target_is_directory=True)
        return actual_link(source, dest, **kwargs)

    monkeypatch.setattr(os, "link", swap_variant)
    with pytest.raises(ValueError, match="namespace changed"):
        _publish(config)
    assert list(outside.iterdir()) == []
    assert sorted(p.name for p in renamed.iterdir()) == ["synthetic-run.json"]


def test_variant_replaced_by_different_regular_directory_mid_publication_fails_closed(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    root = tmp_path / "traces"
    variant = root / "D3"
    renamed = root / "renamed-original"
    actual_link = os.link

    def replace_variant(source, dest, **kwargs):
        variant.rename(renamed)
        variant.mkdir()
        return actual_link(source, dest, **kwargs)

    monkeypatch.setattr(os, "link", replace_variant)
    with pytest.raises(ValueError, match="namespace changed"):
        _publish(config)
    assert list(variant.iterdir()) == []
    assert sorted(p.name for p in renamed.iterdir()) == ["synthetic-run.json"]


def test_root_replaced_by_external_symlink_mid_publication_fails_closed(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "traces"
    renamed = tmp_path / "renamed-root"
    actual_link = os.link

    def swap_root(source, dest, **kwargs):
        root.rename(renamed)
        root.symlink_to(outside, target_is_directory=True)
        return actual_link(source, dest, **kwargs)

    monkeypatch.setattr(os, "link", swap_root)
    with pytest.raises(ValueError, match="namespace changed"):
        _publish(config)
    assert list(outside.iterdir()) == []
    assert sorted(p.name for p in (renamed / "D3").iterdir()) == [
        "synthetic-run.json"
    ]
