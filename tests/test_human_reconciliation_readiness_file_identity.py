"""Offline synthetic file-generation custody tests for reconciliation readiness.

These tests do not generate human ratings or rerun research treatments.
"""
from __future__ import annotations

import os

import pytest

from scripts import verify_human_reconciliation_readiness as readiness


def test_single_link_readiness_input_still_passes(tmp_path):
    path = tmp_path / "human-analysis.json"
    content = b'{"synthetic":true}'
    path.write_bytes(content)
    with readiness._capture_regular_inputs({"human_analysis": path}) as captured:
        assert captured["human_analysis"] == content


@pytest.mark.parametrize("label", ["automated_analysis", "human_analysis"])
def test_preexisting_hardlink_alias_rejected_before_readiness_capture(
    tmp_path, label
):
    path = tmp_path / f"{label}.json"
    path.write_bytes(b'{"synthetic":true}')
    alias = tmp_path / f"{label}-alias.json"
    os.link(path, alias)
    assert path.stat().st_nlink == 2
    # Both names have identical bytes and target the same inode; a path-only
    # digest/size/mtime check would incorrectly accept this source.
    with pytest.raises(ValueError, match="single-link regular file"):
        with readiness._capture_regular_inputs({label: path}):
            pytest.fail("a hardlinked readiness source must not be exposed")


def test_alias_created_during_readiness_window_fails_at_final_recheck(tmp_path):
    path = tmp_path / "human-analysis.json"
    path.write_bytes(b'{"synthetic":true}')
    alias = tmp_path / "late-alias.json"
    with pytest.raises(ValueError, match="single-link regular file"):
        with readiness._capture_regular_inputs({"human_analysis": path}) as captured:
            assert captured["human_analysis"] == path.read_bytes()
            os.link(path, alias)


def test_path_metadata_change_after_descriptor_recheck_fails_closed(
    tmp_path, monkeypatch
):
    path = tmp_path / "human-analysis.json"
    path.write_bytes(b'{"synthetic":true}')
    path.chmod(0o600)
    original_stat = os.stat
    mutated = False

    def chmod_at_path_recheck(candidate, *args, **kwargs):
        nonlocal mutated
        if (
            not mutated
            and candidate == path.name
            and kwargs.get("dir_fd") is not None
        ):
            mutated = True
            # Simulate a concurrent edit after the descriptor's last fstat,
            # but before the final pathname stat. The inode does not change.
            path.chmod(0o400)
        return original_stat(candidate, *args, **kwargs)

    with pytest.raises(ValueError, match="human_analysis changed during verification"):
        with readiness._capture_regular_inputs({"human_analysis": path}) as captured:
            assert captured["human_analysis"] == path.read_bytes()
            monkeypatch.setattr(readiness.os, "stat", chmod_at_path_recheck)
    assert mutated
