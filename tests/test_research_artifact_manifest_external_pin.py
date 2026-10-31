"""Synthetic tests for independent manifest pins; no experimental data is modified."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import verify_research_artifact_manifest as verifier
from scripts.fingerprint_research_artifacts import build_manifest


def _example(tmp_path: Path) -> tuple[Path, Path, str]:
    artifact = tmp_path / "preserved.csv"
    artifact.write_bytes(b"task,result\nT001,original\n")
    manifest = build_manifest([artifact], root=tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return (
        artifact,
        manifest_path,
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )


def test_independent_raw_manifest_pin_accepts_exact_frozen_bytes(tmp_path):
    _, manifest_path, expected = _example(tmp_path)
    entries = verifier.verify_manifest_file(
        manifest_path, root=tmp_path, expected_manifest_sha256=expected
    )
    assert len(entries) == 1
    assert entries[0]["path"] == "preserved.csv"


def test_simultaneous_rehash_of_artifact_and_manifest_requires_external_pin(tmp_path):
    artifact, manifest_path, independent_pin = _example(tmp_path)
    artifact.write_bytes(b"task,result\nT001,replaced\n")
    attacker_manifest = build_manifest([artifact], root=tmp_path)
    manifest_path.write_bytes(
        (json.dumps(attacker_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    # Every internal hash checks out, but the separately held pin detects drift.
    assert len(verifier.verify_manifest_file(manifest_path, root=tmp_path)) == 1
    with pytest.raises(ValueError, match="external manifest SHA-256 pin mismatch"):
        verifier.verify_manifest_file(
            manifest_path, root=tmp_path, expected_manifest_sha256=independent_pin
        )


@pytest.mark.parametrize("invalid", ["f" * 63, "F" * 64, "not-a-digest", "", 123])
def test_external_pin_rejects_malformed_inputs(tmp_path, invalid):
    _, manifest_path, _ = _example(tmp_path)
    with pytest.raises(ValueError, match="expected manifest SHA-256"):
        verifier.verify_manifest_file(
            manifest_path, root=tmp_path, expected_manifest_sha256=invalid
        )


def test_manifest_bytes_changed_during_initial_capture_fail_closed(tmp_path, monkeypatch):
    _, manifest_path, _ = _example(tmp_path)
    original = verifier.fingerprint_regular_file_with_identity
    calls = 0

    def change_after_hash(path):
        nonlocal calls
        fingerprint = original(path)
        if Path(path) == manifest_path:
            calls += 1
            if calls == 1:
                manifest_path.write_bytes(b'{"rewritten":true}\n')
        return fingerprint

    monkeypatch.setattr(verifier, "fingerprint_regular_file_with_identity", change_after_hash)
    with pytest.raises(ValueError, match="manifest file changed during verification"):
        verifier.verify_manifest_file(manifest_path, root=tmp_path)
    assert calls == 1


def test_byte_identical_manifest_inode_replacement_fail_closed(tmp_path, monkeypatch):
    _, manifest_path, _ = _example(tmp_path)
    original = verifier.fingerprint_regular_file_with_identity
    calls = 0

    def replace_after_hash(path):
        nonlocal calls
        fingerprint = original(path)
        if Path(path) == manifest_path:
            calls += 1
            if calls == 1:
                swap = tmp_path / "new_inode.json"
                swap.write_bytes(manifest_path.read_bytes())
                os.replace(swap, manifest_path)
        return fingerprint

    monkeypatch.setattr(verifier, "fingerprint_regular_file_with_identity", replace_after_hash)
    with pytest.raises(ValueError, match="manifest file changed during verification"):
        verifier.verify_manifest_file(manifest_path, root=tmp_path)
    assert calls == 2


def test_manifest_invalid_utf8_is_a_declared_validation_failure(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="manifest file is not valid UTF-8"):
        verifier.verify_manifest_file(path, root=tmp_path)
