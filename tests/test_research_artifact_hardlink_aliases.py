"""Synthetic hard-link alias regression tests for research input provenance.

The file bytes and names are synthetic; no study treatment or human ratings run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import fingerprint_research_artifacts as fingerprints
from scripts.fingerprint_research_artifacts import build_manifest
from scripts.verify_research_artifact_manifest import verify_manifest


def _link(source: Path, alias: Path) -> None:
    try:
        os.link(source, alias)
    except (AttributeError, NotImplementedError, OSError) as exc:
        pytest.skip(f"hard links unavailable on this filesystem: {exc}")


def _manifest_from_existing_paths(paths: list[Path]) -> dict:
    entries = []
    for path in paths:
        data = path.read_bytes()
        entries.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    entries.sort(key=lambda row: row["path"])
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": 1,
        "algorithm": "sha256",
        "artifacts": entries,
        "aggregate_sha256": hashlib.sha256(canonical).hexdigest(),
    }


@pytest.mark.parametrize("reverse", [False, True])
def test_builder_rejects_two_names_for_same_inode(tmp_path: Path, reverse: bool) -> None:
    first = tmp_path / "original.csv"
    second = tmp_path / "independent_name.csv"
    first.write_bytes(b"synthetic report bytes\n")
    _link(first, second)
    paths = [first, second]
    if reverse:
        paths.reverse()

    with pytest.raises(ValueError, match="research artifact hard-link alias"):
        build_manifest(paths, root=tmp_path)


def test_verifier_rejects_independently_rehashed_hardlinked_inputs(tmp_path: Path) -> None:
    first = tmp_path / "original.csv"
    second = tmp_path / "other.csv"
    first.write_bytes(b"synthetic evaluation bytes\n")
    _link(first, second)
    # Deliberately bypass the generator: hashes and aggregate are all valid.
    manifest = _manifest_from_existing_paths([first, second])

    with pytest.raises(ValueError, match="research artifact hard-link alias"):
        verify_manifest(manifest, root=tmp_path)


def test_nested_path_hardlink_is_not_mistaken_for_an_independent_file(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    first.write_bytes(b"synthetic row\n")
    nested = tmp_path / "nested"
    nested.mkdir()
    alias = nested / "alias.csv"
    _link(first, alias)

    with pytest.raises(ValueError, match="research artifact hard-link alias"):
        build_manifest([first, alias], root=tmp_path)


def test_identical_bytes_in_separate_files_still_round_trip(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_bytes(b"same exact bytes\n")
    second.write_bytes(b"same exact bytes\n")
    if (first.stat().st_dev, first.stat().st_ino) == (
        second.stat().st_dev, second.stat().st_ino
    ):
        pytest.skip("filesystem does not distinguish separately created file identities")

    manifest = build_manifest([first, second], root=tmp_path)
    assert [x["path"] for x in verify_manifest(manifest, root=tmp_path)] == [
        "first.csv",
        "second.csv",
    ]
    assert manifest["artifacts"][0]["sha256"] == manifest["artifacts"][1]["sha256"]


def test_portable_fallback_also_rejects_hardlink_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "original.csv"
    second = tmp_path / "alias.csv"
    first.write_bytes(b"fallback evidence\n")
    _link(first, second)
    manifest = _manifest_from_existing_paths([first, second])
    monkeypatch.setattr(fingerprints, "SUPPORTS_DESCRIPTOR_TRAVERSAL", False)

    with pytest.raises(ValueError, match="research artifact hard-link alias"):
        build_manifest([first, second], root=tmp_path)
    with pytest.raises(ValueError, match="research artifact hard-link alias"):
        verify_manifest(manifest, root=tmp_path)


def test_public_fingerprint_two_value_contract_unchanged(tmp_path: Path) -> None:
    artifact = tmp_path / "single.csv"
    artifact.write_bytes(b"synthetic\n")
    digest, nbytes = fingerprints.fingerprint_regular_file(artifact)
    assert (digest, nbytes) == (hashlib.sha256(b"synthetic\n").hexdigest(), 10)
