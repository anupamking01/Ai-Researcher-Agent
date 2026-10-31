"""Synthetic safety regression for create-only research manifest output.

No study inputs, model treatments, evaluator results or human ratings are used.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from scripts import fingerprint_research_artifacts as producer
from scripts.verify_research_artifact_manifest import verify_manifest


def _render(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "preserved-study.csv"
    source.write_bytes(b"variant,strict_support\nD3,0.5\n")
    manifest = producer.build_manifest([source], root=tmp_path)
    return source, json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def test_nested_new_manifest_is_created_and_verifiable(tmp_path: Path) -> None:
    source, content = _render(tmp_path)
    destination = tmp_path / "new" / "nested" / "manifest.json"
    producer.write_manifest_create_only(destination, content)
    assert destination.read_text(encoding="utf-8") == content
    assert verify_manifest(json.loads(destination.read_text()), root=tmp_path)
    assert source.read_bytes() == b"variant,strict_support\nD3,0.5\n"


def test_existing_manifest_cannot_be_overwritten(tmp_path: Path) -> None:
    _, content = _render(tmp_path)
    destination = tmp_path / "manifest.json"
    destination.write_bytes(b"original immutable manifest")
    with pytest.raises(ValueError, match="already exists"):
        producer.write_manifest_create_only(destination, content)
    assert destination.read_bytes() == b"original immutable manifest"


def test_existing_study_input_cannot_be_clobbered_as_output(tmp_path: Path) -> None:
    source, content = _render(tmp_path)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        producer.write_manifest_create_only(source, content)
    assert source.read_bytes() == original


@pytest.mark.parametrize("dangling", [False, True])
def test_existing_output_symlink_does_not_replace_target(
    tmp_path: Path, dangling: bool
) -> None:
    _, content = _render(tmp_path)
    target = tmp_path / ("missing.json" if dangling else "preserved.json")
    if not dangling:
        target.write_bytes(b"valuable")
    destination = tmp_path / "manifest.json"
    destination.symlink_to(target)
    with pytest.raises(ValueError, match="already exists"):
        producer.write_manifest_create_only(destination, content)
    assert destination.is_symlink()
    if dangling:
        assert not target.exists()
    else:
        assert target.read_bytes() == b"valuable"


def test_symlinked_parent_does_not_redirect_manifest_output(tmp_path: Path) -> None:
    _, content = _render(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe|unavailable"):
        producer.write_manifest_create_only(alias / "manifest.json", content)
    assert not (real / "manifest.json").exists()


def test_partial_write_is_removed_and_not_reported_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, content = _render(tmp_path)
    destination = tmp_path / "manifest.json"
    actual_write = producer.os.write
    writes = 0

    def interrupted_write(fd, data):
        nonlocal writes
        writes += 1
        if writes == 1:
            return actual_write(fd, data[:4])
        raise OSError("simulated disk-write failure")

    monkeypatch.setattr(producer.os, "write", interrupted_write)
    with pytest.raises(ValueError, match="unsafe|unavailable"):
        producer.write_manifest_create_only(destination, content)
    assert not destination.exists()


def test_cli_refuses_output_that_is_an_input_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = _render(tmp_path)
    original_bytes = source.read_bytes()
    original_builder = producer.build_manifest
    monkeypatch.setattr(producer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        producer, "build_manifest",
        lambda paths: original_builder(paths, root=tmp_path),
    )
    monkeypatch.setattr(sys, "argv", [
        "fingerprint_research_artifacts.py",
        "preserved-study.csv",
        "--output", "preserved-study.csv",
    ])
    with pytest.raises(ValueError, match="already exists"):
        producer.main()
    assert source.read_bytes() == original_bytes


def test_cli_creates_new_output_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _render(tmp_path)
    original_builder = producer.build_manifest
    monkeypatch.setattr(producer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        producer, "build_manifest",
        lambda paths: original_builder(paths, root=tmp_path),
    )
    monkeypatch.setattr(sys, "argv", [
        "fingerprint_research_artifacts.py",
        "preserved-study.csv", "--output", "fingerprints/new.json",
    ])
    assert producer.main() == 0
    assert verify_manifest(
        json.loads((tmp_path / "fingerprints" / "new.json").read_text()),
        root=tmp_path,
    )
    with pytest.raises(ValueError, match="already exists"):
        producer.main()
