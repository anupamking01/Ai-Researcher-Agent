from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

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
