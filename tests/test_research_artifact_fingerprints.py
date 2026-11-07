from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import fingerprint_research_artifacts as fingerprints
from scripts.fingerprint_research_artifacts import build_manifest, sha256_file


def test_sha256_file_matches_known_digest(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.csv"
    artifact.write_bytes(b"a,b\n1,2\n")

    assert sha256_file(artifact) == hashlib.sha256(b"a,b\n1,2\n").hexdigest()


def test_manifest_is_independent_of_argument_order(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.json"
    first.write_text("x\n1\n", encoding="utf-8")
    second.write_text('{"ok":true}\n', encoding="utf-8")

    forward = build_manifest([first, second], root=tmp_path)
    reverse = build_manifest([second, first], root=tmp_path)

    assert forward == reverse
    assert [entry["path"] for entry in forward["artifacts"]] == ["first.csv", "second.json"]
    assert forward["algorithm"] == "sha256"
    assert len(forward["aggregate_sha256"]) == 64


def test_manifest_changes_when_artifact_bytes_change(tmp_path: Path) -> None:
    artifact = tmp_path / "study.csv"
    artifact.write_text("score\n0.5\n", encoding="utf-8")
    before = build_manifest([artifact], root=tmp_path)

    artifact.write_text("score\n0.6\n", encoding="utf-8")
    after = build_manifest([artifact], root=tmp_path)

    assert before["aggregate_sha256"] != after["aggregate_sha256"]
    assert before["artifacts"][0]["sha256"] != after["artifacts"][0]["sha256"]


def test_manifest_records_exact_byte_size(tmp_path: Path) -> None:
    artifact = tmp_path / "unicode.txt"
    payload = "café\n".encode("utf-8")
    artifact.write_bytes(payload)

    manifest = build_manifest([artifact], root=tmp_path)

    assert manifest["artifacts"][0]["bytes"] == len(payload)


def test_manifest_rejects_duplicate_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "study.csv"
    artifact.write_text("x\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate research artifact"):
        build_manifest([artifact, artifact], root=tmp_path)


def test_manifest_rejects_artifacts_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("x\n", encoding="utf-8")

    with pytest.raises(ValueError, match="inside repository root"):
        build_manifest([outside], root=root)


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing or not a file"):
        sha256_file(tmp_path / "missing.csv")


def test_sha256_file_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.csv"
    target.write_text("x\n", encoding="utf-8")
    alias = tmp_path / "alias.csv"
    alias.symlink_to(target)

    with pytest.raises(ValueError, match="regular file"):
        sha256_file(alias)


def test_manifest_rejects_symlinked_artifact(tmp_path: Path) -> None:
    target = tmp_path / "target.csv"
    target.write_text("x\n", encoding="utf-8")
    alias = tmp_path / "alias.csv"
    alias.symlink_to(target)

    with pytest.raises(ValueError, match="regular file"):
        build_manifest([alias], root=tmp_path)


def test_manifest_rejects_artifact_through_symlinked_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    artifact = real / "artifact.csv"
    artifact.write_text("x\n", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(ValueError, match="regular file"):
        build_manifest([alias / "artifact.csv"], root=tmp_path)


def test_fingerprint_rejects_parent_directory_swap_during_open(
    tmp_path: Path, monkeypatch
) -> None:
    parent = tmp_path / "inputs"
    parent.mkdir()
    artifact = parent / "artifact.csv"
    artifact.write_bytes(b"canonical")
    moved = tmp_path / "moved-inputs"
    substitute = tmp_path / "substitute"
    substitute.mkdir()
    (substitute / artifact.name).write_bytes(b"substituted")
    real_open = fingerprints.os.open
    swapped = False

    def swap_parent_before_leaf_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and str(path) in {str(artifact), artifact.name}:
            swapped = True
            parent.rename(moved)
            parent.symlink_to(substitute, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(fingerprints.os, "open", swap_parent_before_leaf_open)

    with pytest.raises(ValueError, match="changed|regular file"):
        sha256_file(artifact)


def test_portable_fallback_streams_without_descriptor_traversal(
    tmp_path: Path, monkeypatch
) -> None:
    artifact = tmp_path / "artifact.csv"
    artifact.write_bytes(b"portable")
    monkeypatch.setattr(fingerprints, "SUPPORTS_DESCRIPTOR_TRAVERSAL", False)

    assert sha256_file(artifact) == hashlib.sha256(b"portable").hexdigest()
