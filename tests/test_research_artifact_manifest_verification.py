"""Tests for fail-closed verification of preserved research artifacts."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import verify_research_artifact_manifest as manifest_verifier
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


@pytest.mark.parametrize("schema_version", [True, "1", 1.0, [], {}])
def test_verifier_rejects_noninteger_schema_types(tmp_path, schema_version):
    manifest, _, _ = _manifest(tmp_path)
    manifest["schema_version"] = schema_version

    with pytest.raises(ValueError, match="unsupported.*schema"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_extra_root_field(tmp_path):
    manifest, _, _ = _manifest(tmp_path)
    manifest["unreviewed_extension"] = True

    with pytest.raises(ValueError, match="exact root fields"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_extra_artifact_field(tmp_path):
    manifest, _, _ = _manifest(tmp_path)
    manifest["artifacts"][0]["unreviewed_extension"] = True

    with pytest.raises(ValueError, match="exact fields"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_boolean_byte_count(tmp_path):
    artifact = tmp_path / "one-byte.bin"
    artifact.write_bytes(b"x")
    manifest = build_manifest([artifact], root=tmp_path)
    manifest["artifacts"][0]["bytes"] = True
    canonical = json.dumps(
        manifest["artifacts"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest["aggregate_sha256"] = hashlib.sha256(canonical).hexdigest()

    with pytest.raises(ValueError, match="invalid byte count"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_symlink_substitution_with_identical_bytes(tmp_path):
    manifest, first, _ = _manifest(tmp_path)
    replacement = tmp_path / "replacement.csv"
    replacement.write_bytes(first.read_bytes())
    first.unlink()
    first.symlink_to(replacement)

    with pytest.raises(ValueError, match="regular file"):
        verify_manifest(manifest, root=tmp_path)


def test_verifier_rejects_symlinked_parent_directory(tmp_path):
    manifest, _, second = _manifest(tmp_path)
    original_parent = second.parent
    moved_parent = tmp_path / "moved"
    original_parent.rename(moved_parent)
    original_parent.symlink_to(moved_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="regular file"):
        verify_manifest(manifest, root=tmp_path)


@pytest.mark.parametrize(
    "ambiguous_json",
    [
        '{"schema_version":999,"schema_version":1}',
        '{"entry":{"path":"first","path":"second"}}',
    ],
)
def test_manifest_json_parser_rejects_duplicate_fields(ambiguous_json):
    with pytest.raises(ValueError, match="duplicate JSON field"):
        manifest_verifier.parse_manifest_json(ambiguous_json)


@pytest.mark.parametrize(
    "ambiguous_path",
    [r"C:\\outside\\artifact.csv", r"nested\\artifact.csv"],
)
def test_verifier_rejects_platform_ambiguous_paths(tmp_path, ambiguous_path):
    manifest, _, _ = _manifest(tmp_path)
    manifest["artifacts"][0]["path"] = ambiguous_path
    canonical = json.dumps(
        sorted(manifest["artifacts"], key=lambda item: item["path"]),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest["aggregate_sha256"] = hashlib.sha256(canonical).hexdigest()

    with pytest.raises(ValueError, match="canonical"):
        verify_manifest(manifest, root=tmp_path)
