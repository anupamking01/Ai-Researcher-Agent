"""Synthetic regressions for bounded, descriptor-bound manifest JSON capture.

This suite never opens frozen study inputs or generates human ratings.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import verify_research_artifact_manifest as verifier
from scripts.fingerprint_research_artifacts import build_manifest


def _synthetic_manifest(tmp_path: Path) -> Path:
    artifact = tmp_path / "synthetic-report.csv"
    artifact.write_bytes(b"task_id,support\nSYN-01,1\n")
    document = build_manifest([artifact], root=tmp_path)
    manifest_path = tmp_path / "fingerprints.json"
    manifest_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_manifest_verification_does_not_reopen_with_path_read_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _synthetic_manifest(tmp_path)
    ordinary_read_bytes = Path.read_bytes

    def forbid_unchecked_read(self):
        if self == path:
            raise AssertionError("manifest was read through Path.read_bytes")
        return ordinary_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", forbid_unchecked_read)
    entries = verifier.verify_manifest_file(path, root=tmp_path)
    assert len(entries) == 1
    assert entries[0]["path"] == "synthetic-report.csv"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is not available")
def test_substituted_fifo_is_rejected_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _synthetic_manifest(tmp_path)
    original = verifier.fingerprint_regular_file_with_identity
    first = True

    def replace_after_first_capture(candidate):
        nonlocal first
        fingerprint = original(candidate)
        if Path(candidate) == path and first:
            first = False
            path.rename(tmp_path / "unchanged-manifest.json")
            os.mkfifo(path)
        return fingerprint

    monkeypatch.setattr(
        verifier, "fingerprint_regular_file_with_identity",
        replace_after_first_capture,
    )
    with pytest.raises(ValueError, match="manifest capture requires a regular file"):
        verifier.verify_manifest_file(path, root=tmp_path)
    assert first is False


@pytest.mark.skipif(
    not getattr(os, "O_NOFOLLOW", 0), reason="no-follow leaf open is unavailable"
)
def test_substituted_symlink_is_not_followed_for_raw_manifest_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _synthetic_manifest(tmp_path)
    original = verifier.fingerprint_regular_file_with_identity
    first = True

    def replace_after_first_capture(candidate):
        nonlocal first
        fingerprint = original(candidate)
        if Path(candidate) == path and first:
            first = False
            renamed = tmp_path / "unchanged-manifest.json"
            path.rename(renamed)
            path.symlink_to(renamed)
        return fingerprint

    monkeypatch.setattr(
        verifier, "fingerprint_regular_file_with_identity",
        replace_after_first_capture,
    )
    with pytest.raises(ValueError, match="manifest capture requires a regular file"):
        verifier.verify_manifest_file(path, root=tmp_path)
    assert first is False


def test_oversized_sparse_manifest_is_rejected_before_loading_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    oversized = tmp_path / "oversized-manifest.json"
    with oversized.open("wb") as handle:
        handle.truncate(verifier.MAX_MANIFEST_BYTES + 1)

    def forbid_descriptor_capture(_):
        raise AssertionError("oversized manifest should not be loaded into memory")

    monkeypatch.setattr(verifier, "_read_regular_manifest_bytes", forbid_descriptor_capture)
    with pytest.raises(ValueError, match="16 MiB safety limit"):
        verifier.verify_manifest_file(oversized, root=tmp_path)


def test_descriptor_capture_rejects_same_size_mutation_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _synthetic_manifest(tmp_path)
    original_capture = verifier._read_regular_manifest_bytes
    original_read = os.read
    changed = False

    def read_then_mutate(descriptor, count):
        nonlocal changed
        raw = original_read(descriptor, count)
        if raw and not changed:
            changed = True
            with path.open("r+b") as handle:
                handle.seek(0)
                handle.write(b"Z")
                handle.flush()
        return raw

    def capture_with_mutation(candidate):
        monkeypatch.setattr(os, "read", read_then_mutate)
        try:
            return original_capture(candidate)
        finally:
            monkeypatch.setattr(os, "read", original_read)

    monkeypatch.setattr(verifier, "_read_regular_manifest_bytes", capture_with_mutation)
    with pytest.raises(ValueError, match="manifest file changed during descriptor capture"):
        verifier.verify_manifest_file(path, root=tmp_path)
    assert changed
