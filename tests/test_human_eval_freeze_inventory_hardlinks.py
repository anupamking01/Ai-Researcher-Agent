"""Synthetic hardlink custody checks for the independent blinded-freeze verifier.

An alias outside the archived freeze tree can change the same inode while
remaining invisible to manifest path enumeration. No human ratings are used.
"""
import os
from pathlib import Path

import pytest

from scripts import verify_human_eval_freeze as verifier


def test_standalone_inventory_accepts_single_link_files(tmp_path: Path):
    root = tmp_path / "freeze"
    nested = root / "raw_rating_inputs"
    nested.mkdir(parents=True)
    (root / "agreement.json").write_bytes(b"synthetic agreement")
    (nested / "0001.csv").write_bytes(b"synthetic rating")
    inventory = verifier._capture_freeze_inventory(root)
    assert len(inventory[1]) == 2


def test_standalone_inventory_rejects_external_alias_to_top_level_file(
    tmp_path: Path,
):
    root = tmp_path / "freeze"
    root.mkdir()
    original = root / "agreement.json"
    original.write_bytes(b"synthetic agreement")
    os.link(original, tmp_path / "outside-freeze.json")

    with pytest.raises(ValueError, match="single-link regular freeze file"):
        verifier._capture_freeze_inventory(root)


def test_standalone_inventory_rejects_external_alias_to_nested_rating(
    tmp_path: Path,
):
    root = tmp_path / "freeze"
    raw = root / "raw_rating_inputs"
    raw.mkdir(parents=True)
    original = raw / "0001.csv"
    original.write_bytes(b"synthetic rating")
    os.link(original, tmp_path / "outside-freeze.csv")

    with pytest.raises(ValueError, match="single-link regular freeze file"):
        verifier._capture_freeze_inventory(root)


def test_standalone_inventory_rejects_two_in_tree_names_for_one_inode(
    tmp_path: Path,
):
    root = tmp_path / "freeze"
    root.mkdir()
    original = root / "frozen_ratings.csv"
    original.write_bytes(b"synthetic ratings")
    os.link(original, root / "agreement.json")

    with pytest.raises(ValueError, match="single-link regular freeze file"):
        verifier._capture_freeze_inventory(root)


def test_standalone_inventory_detects_link_added_during_stability_check(
    tmp_path: Path, monkeypatch,
):
    root = tmp_path / "freeze"
    root.mkdir()
    original = root / "agreement.json"
    original.write_bytes(b"synthetic agreement")
    scan = verifier._bounded_inventory_names
    linked = []

    def add_alias_on_recheck(descriptor, *, maximum, label, stability_check=False):
        if stability_check and not linked:
            os.link(original, tmp_path / "late-outside-freeze.json")
            linked.append(True)
        return scan(
            descriptor, maximum=maximum, label=label,
            stability_check=stability_check,
        )

    monkeypatch.setattr(verifier, "_bounded_inventory_names", add_alias_on_recheck)
    with pytest.raises(ValueError, match="changed while it was being verified"):
        verifier._capture_freeze_inventory(root)
    assert linked == [True]


def test_standalone_inventory_accepts_restored_single_link_before_verification(
    tmp_path: Path,
):
    root = tmp_path / "freeze"
    root.mkdir()
    original = root / "freeze_manifest.json"
    original.write_bytes(b"synthetic manifest")
    alias = tmp_path / "temporary-alias.json"
    os.link(original, alias)
    alias.unlink()

    assert verifier._capture_freeze_inventory(root)[1][0][0] == original.name
