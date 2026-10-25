"""Synthetic regression: failed manifest writes must not delete a replacement.

The tests use only temporary files; no VERA study outputs or ratings are read.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import fingerprint_research_artifacts as producer


@pytest.mark.parametrize("replacement", ["hardlink", "symlink"])
def test_failed_write_preserves_replaced_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: str
) -> None:
    if not (os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd):
        pytest.skip("requires directory-descriptor manifest writer")
    destination = tmp_path / "manifest.json"
    displaced = tmp_path / "partial-created-by-writer.json"
    preserved = tmp_path / "preserved-experiment.csv"
    preserved.write_bytes(b"immutable synthetic input\\n")
    expected = preserved.read_bytes()
    original_write = producer.os.write
    calls = 0

    def interrupt_after_replacement(fd: int, data) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_write(fd, data[:4])
        os.replace(destination, displaced)
        if replacement == "hardlink":
            os.link(preserved, destination)
        else:
            destination.symlink_to(preserved)
        raise OSError("injected write failure after destination replacement")

    monkeypatch.setattr(producer.os, "write", interrupt_after_replacement)
    with pytest.raises(ValueError, match="unsafe or unavailable"):
        producer.write_manifest_create_only(destination, '{"synthetic": true}\n')

    assert displaced.read_bytes() == b'{"sy'
    assert preserved.read_bytes() == expected
    assert destination.read_bytes() == expected
    if replacement == "symlink":
        assert destination.is_symlink()
    else:
        assert not destination.is_symlink()
        assert os.stat(destination).st_ino == os.stat(preserved).st_ino


def test_failed_write_cleans_unreplaced_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not (os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd):
        pytest.skip("requires directory-descriptor manifest writer")
    destination = tmp_path / "manifest.json"
    original_write = producer.os.write
    calls = 0

    def interrupt(fd: int, data) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_write(fd, data[:3])
        raise OSError("injected partial write failure")

    monkeypatch.setattr(producer.os, "write", interrupt)
    with pytest.raises(ValueError, match="unsafe or unavailable"):
        producer.write_manifest_create_only(destination, '{"synthetic": true}\n')
    assert not destination.exists()
