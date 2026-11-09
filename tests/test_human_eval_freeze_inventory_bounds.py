"""Synthetic, offline bounds for the standalone blinded freeze verifier.

No treatment artifacts, human ratings, or human identities are used.
"""
import os
from pathlib import Path

import pytest

from scripts import verify_human_eval_freeze as verifier


def _inventory(root: Path):
    return verifier._capture_freeze_inventory(root)


def test_standalone_inventory_accepts_entry_ceiling(tmp_path: Path):
    for index in range(verifier.MAX_FREEZE_INVENTORY_ENTRIES):
        (tmp_path / f"synthetic-{index:04d}.txt").touch()
    assert len(_inventory(tmp_path)[1]) == verifier.MAX_FREEZE_INVENTORY_ENTRIES


def test_standalone_inventory_rejects_entry_overflow_before_parsing(tmp_path: Path):
    for index in range(verifier.MAX_FREEZE_INVENTORY_ENTRIES + 1):
        (tmp_path / f"synthetic-{index:04d}.txt").touch()
    with pytest.raises(ValueError, match="entry.*inventory limit"):
        _inventory(tmp_path)


def test_standalone_inventory_rejects_aggregate_sparse_bytes(tmp_path: Path):
    (tmp_path / "synthetic-a").write_bytes(b"a")
    with (tmp_path / "synthetic-b").open("wb") as target:
        target.truncate(verifier.MAX_FREEZE_INVENTORY_BYTES)
    with pytest.raises(ValueError, match="aggregate.*inventory limit"):
        _inventory(tmp_path)


def test_standalone_inventory_accepts_sparse_byte_ceiling_without_reading(
    tmp_path: Path, monkeypatch,
):
    with (tmp_path / "synthetic-large").open("wb") as target:
        target.truncate(verifier.MAX_FREEZE_INVENTORY_BYTES)
    monkeypatch.setattr(
        verifier, "_require_regular_file",
        lambda *args, **kwargs: pytest.fail("inventory must not read file contents"),
    )
    assert _inventory(tmp_path)[1][0][0] == "synthetic-large"


def test_standalone_inventory_rejects_excess_recursive_depth(tmp_path: Path):
    child = tmp_path
    for index in range(verifier.MAX_FREEZE_INVENTORY_DEPTH + 1):
        child = child / f"synthetic-{index}"
        child.mkdir()
    with pytest.raises(ValueError, match="depth limit"):
        _inventory(tmp_path)


def test_standalone_inventory_accepts_recursive_depth_boundary(tmp_path: Path):
    child = tmp_path
    for index in range(verifier.MAX_FREEZE_INVENTORY_DEPTH):
        child = child / f"synthetic-{index}"
        child.mkdir()
    assert _inventory(tmp_path)[1]
