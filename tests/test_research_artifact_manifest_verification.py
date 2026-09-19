"""Tests for fail-closed verification of preserved research artifacts."""
from pathlib import Path

import pytest

from scripts.fingerprint_research_artifacts import build_manifest
from scripts.verify_research_artifact_manifest import verify_manifest


def _manifest(tmp_path: Path):
    first = tmp_path / "first.csv"
    second = tmp_path / "nested" / "second.json"
    second.parent.mkdir()
    first.write_text("task,score\na,1\n", encoding="utf-8")
    second.write_text('{"status":"ok"}\n', encoding="utf-8")
    return build_manifest([first, second], root=tmp_path), first, second


def test_generated_manifest_round_trips(tmp_path):
    manifest, _, _ = _manifest(tmp_path)
    entries = verify_manifest(manifest, root=tmp_path)
    assert [entry["path"] for entry in entries] == ["first.csv", "nested/second.json"]


def test_verifier_detects_content_mutation_even_when_file_still_exists(tmp_path):
    manifest, first, _ = _manifest(tmp_path)
    first.write_text("task,score\na,9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_detects_truncation_by_byte_size(tmp_path):
    manifest, _, second = _manifest(tmp_path)
    second.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="byte-size mismatch"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_aggregate_tampering(tmp_path):
    manifest, _, _ = _manifest(tmp_path)
    manifest["aggregate_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="aggregate research-artifact fingerprint mismatch"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_duplicate_paths(tmp_path):
    manifest, _, _ = _manifest(tmp_path)
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    with pytest.raises(ValueError, match="duplicate research artifact"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_path_escape(tmp_path):
    manifest, _, _ = _manifest(tmp_path)
    outside = tmp_path.parent / "outside-research-artifact.txt"
    outside.write_text("outside", encoding="utf-8")
    entry = manifest["artifacts"][0]
    entry["path"] = "../outside-research-artifact.txt"
    entry["bytes"] = outside.stat().st_size
    from scripts.fingerprint_research_artifacts import sha256_file
    entry["sha256"] = sha256_file(outside)
    with pytest.raises(ValueError, match="escapes repository root"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_unsupported_schema_and_algorithm(tmp_path):
    manifest, _, _ = _manifest(tmp_path)
    bad_schema = dict(manifest, schema_version=2)
    with pytest.raises(ValueError, match="unsupported.*schema"):
        verify_manifest(bad_schema, root=tmp_path)
    bad_algorithm = dict(manifest, algorithm="md5")
    with pytest.raises(ValueError, match="unsupported.*algorithm"):
        verify_manifest(bad_algorithm, root=tmp_path)
