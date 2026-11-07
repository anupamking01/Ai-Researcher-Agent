"""Portable path identity regressions for research-artifact provenance.

These synthetic files exercise cross-filesystem aliases, not experimental data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.fingerprint_research_artifacts import build_manifest
from scripts.verify_research_artifact_manifest import verify_manifest


def _signed_manifest(entries):
    canonical = json.dumps(
        sorted(entries, key=lambda entry: entry["path"]),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "algorithm": "sha256",
        "artifacts": entries,
        "aggregate_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _entry(path: Path):
    payload = path.read_bytes()
    return {
        "path": path.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


@pytest.mark.parametrize(
    "first,second",
    [
        ("Run.csv", "run.csv"),
        ("café.csv", "cafe\u0301.csv"),
        ("MATRIX.csv", "ＭＡＴＲＩＸ.csv"),
    ],
)
def test_builder_rejects_case_and_unicode_aliases(tmp_path, first, second):
    a, b = tmp_path / first, tmp_path / second
    a.write_bytes(b"original source")
    b.write_bytes(b"separate source")
    with pytest.raises(ValueError, match="portable research artifact path collision"):
        build_manifest([a, b], root=tmp_path)


@pytest.mark.parametrize(
    "first,second",
    [
        ("Run.csv", "run.csv"),
        ("café.csv", "cafe\u0301.csv"),
        ("MATRIX.csv", "ＭＡＴＲＩＸ.csv"),
    ],
)
def test_verifier_rejects_rehashed_case_and_unicode_aliases(tmp_path, first, second):
    a, b = tmp_path / first, tmp_path / second
    a.write_bytes(b"original source")
    b.write_bytes(b"separate source")
    manifest = _signed_manifest([_entry(a), _entry(b)])
    with pytest.raises(ValueError, match="portable research artifact path collision"):
        verify_manifest(manifest, root=tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "CON.csv",  # Windows reserved device, even with extension
        "LPT１.log",  # compatibility digit becomes Windows LPT1
        "run.csv:revision",  # NTFS alternate data stream
        "trailing. ",
        "file?.txt",
        "fullwidth／slash.csv",  # NFKC introduces a path separator
        "override\u202E.csv",  # directional control obscures path rendering
    ],
)
def test_builder_and_verifier_reject_nonportable_path_components(tmp_path, name):
    file = tmp_path / name
    file.write_bytes(b"research artifact")
    with pytest.raises(ValueError, match="non-portable research artifact path"):
        build_manifest([file], root=tmp_path)
    manifest = _signed_manifest([_entry(file)])
    with pytest.raises(ValueError, match="non-portable research artifact path"):
        verify_manifest(manifest, root=tmp_path)


def test_distinct_portable_artifacts_round_trip(tmp_path):
    a, b = tmp_path / "task_D3.csv", tmp_path / "task_D6.csv"
    a.write_bytes(b"one")
    b.write_bytes(b"two")
    manifest = build_manifest([a, b], root=tmp_path)
    assert [row["path"] for row in verify_manifest(manifest, root=tmp_path)] == [
        "task_D3.csv",
        "task_D6.csv",
    ]
