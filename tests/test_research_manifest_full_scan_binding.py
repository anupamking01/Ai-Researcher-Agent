"""Synthetic checks that the manifest itself stays bound through source verification.

No actual experiment, frozen analysis, or human-evaluation artifact is accessed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import verify_research_artifact_manifest as verifier
from scripts.fingerprint_research_artifacts import build_manifest


def _synthetic_inputs(root: Path) -> tuple[Path, str]:
    source = root / "source.csv"
    source.write_bytes(b"task_id,score\nSYN-001,1\n")
    manifest = build_manifest([source], root=root)
    path = root / "manifest.json"
    original = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(original)
    return path, hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("mode", ["rewrite", "replace_same_bytes", "remove"])
@pytest.mark.parametrize("pinned", [False, True])
def test_manifest_change_during_artifact_scan_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, pinned: bool
) -> None:
    path, external_pin = _synthetic_inputs(tmp_path)
    original_verify = verifier.verify_manifest

    def mutate_after_source_scan(manifest: dict, *, root: Path) -> list[dict]:
        entries = original_verify(manifest, root=root)
        if mode == "rewrite":
            path.write_bytes(b'{"changed":"during scan"}\n')
        elif mode == "replace_same_bytes":
            replacement = tmp_path / "replacement.json"
            replacement.write_bytes(path.read_bytes())
            os.replace(replacement, path)
        else:
            path.unlink()
        return entries

    monkeypatch.setattr(verifier, "verify_manifest", mutate_after_source_scan)
    kwargs = {"expected_manifest_sha256": external_pin} if pinned else {}
    with pytest.raises(
        ValueError, match="manifest file changed during artifact verification"
    ):
        verifier.verify_manifest_file(path, root=tmp_path, **kwargs)


@pytest.mark.parametrize("pinned", [False, True])
def test_unchanged_manifest_remains_accepted_through_full_scan(
    tmp_path: Path, pinned: bool
) -> None:
    path, external_pin = _synthetic_inputs(tmp_path)
    kwargs = {"expected_manifest_sha256": external_pin} if pinned else {}
    entries = verifier.verify_manifest_file(path, root=tmp_path, **kwargs)
    assert len(entries) == 1
    assert entries[0]["path"] == "source.csv"
