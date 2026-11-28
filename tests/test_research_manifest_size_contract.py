"""Synthetic producer/verifier size-contract regressions; no study data is read."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import fingerprint_research_artifacts as producer
from scripts import verify_research_artifact_manifest as verifier


def _manifest(tmp_path: Path) -> Path:
    artifact = tmp_path / "synthetic.csv"
    artifact.write_bytes(b"task,score\nSYN-1,1\n")
    record = producer.build_manifest([artifact], root=tmp_path)
    manifest = tmp_path / "synthetic-manifest.json"
    manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def test_shared_metadata_bound_is_the_same_for_both_tools() -> None:
    assert producer.MAX_MANIFEST_BYTES == verifier.MAX_MANIFEST_BYTES == 16 * 1024 * 1024


def test_verifier_rejects_oversize_before_first_full_hash(tmp_path, monkeypatch):
    path = _manifest(tmp_path)
    monkeypatch.setattr(verifier, "MAX_MANIFEST_BYTES", path.stat().st_size - 1)

    def no_expensive_hash(_):
        raise AssertionError("over-limit manifest should not be hashed")

    monkeypatch.setattr(verifier, "fingerprint_regular_file_with_identity", no_expensive_hash)
    with pytest.raises(ValueError, match="16 MiB safety limit"):
        verifier.verify_manifest_file(path, root=tmp_path)


def test_oversize_replacement_after_artifact_scan_skips_closing_hash(tmp_path, monkeypatch):
    path = _manifest(tmp_path)
    monkeypatch.setattr(verifier, "MAX_MANIFEST_BYTES", path.stat().st_size + 10)
    original_verify = verifier.verify_manifest
    original_hash = verifier.fingerprint_regular_file_with_identity
    calls = []

    def guarded_hash(candidate):
        if Path(candidate) == path:
            calls.append("manifest")
            if path.stat().st_size > verifier.MAX_MANIFEST_BYTES:
                raise AssertionError("over-limit closing hash must be skipped")
        return original_hash(candidate)

    def change_after_scan(manifest, *, root):
        entries = original_verify(manifest, root=root)
        with path.open("ab") as output:
            output.write(b" " * 11)
        return entries

    monkeypatch.setattr(verifier, "fingerprint_regular_file_with_identity", guarded_hash)
    monkeypatch.setattr(verifier, "verify_manifest", change_after_scan)
    with pytest.raises(ValueError, match="manifest file changed during artifact verification"):
        verifier.verify_manifest_file(path, root=tmp_path)
    assert calls == ["manifest", "manifest"]


def test_direct_writer_rejects_over_limit_before_creating_parent(tmp_path, monkeypatch):
    # Multi-byte UTF-8 makes character count smaller than byte count.
    rendered = '{"note":"ααα"}\n'
    assert len(rendered) < len(rendered.encode("utf-8"))
    monkeypatch.setattr(producer, "MAX_MANIFEST_BYTES", len(rendered.encode("utf-8")) - 1)
    output = tmp_path / "uncreated" / "manifest.json"
    with pytest.raises(ValueError, match="16 MiB safety limit"):
        producer.write_manifest_create_only(output, rendered)
    assert not output.parent.exists()


def test_direct_writer_accepts_exact_utf8_byte_boundary(tmp_path, monkeypatch):
    rendered = '{"note":"α"}\n'
    monkeypatch.setattr(producer, "MAX_MANIFEST_BYTES", len(rendered.encode("utf-8")))
    output = tmp_path / "new" / "manifest.json"
    producer.write_manifest_create_only(output, rendered)
    assert output.read_bytes() == rendered.encode("utf-8")


@pytest.mark.parametrize("with_output", [False, True])
def test_cli_rejects_over_limit_before_stdout_or_destination(
    tmp_path, monkeypatch, capsys, with_output
):
    monkeypatch.setattr(producer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(producer, "build_manifest", lambda _: {"synthetic": "x" * 100})
    monkeypatch.setattr(producer, "MAX_MANIFEST_BYTES", 30)
    arguments = ["fingerprint_research_artifacts.py"]
    if with_output:
        arguments += ["--output", "uncreated/manifest.json"]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(ValueError, match="16 MiB safety limit"):
        producer.main()
    assert capsys.readouterr().out == ""
    assert not (tmp_path / "uncreated").exists()
