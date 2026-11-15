"""Synthetic-only pre-install evidence-file capture checks; no research runs."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from scripts import verify_ci_early_gate_evidence as early


SHA = "a" * 40
RECEIPT = {"status": "synthetic-only", "schema_version": 1}


def _invoke(tmp_path: Path, monkeypatch, *, mode: str) -> int:
    # Isolate the file-capture contract; test-source/transcript semantics are
    # independently covered by the dependency-free unittest suite.
    monkeypatch.setattr(early, "ROOT", tmp_path)
    monkeypatch.setattr(early, "build_receipt", lambda *_args, **_kw: RECEIPT)
    for name in early.SOURCES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic source")
    monkeypatch.setattr(sys, "argv", [
        "verify_ci_early_gate_evidence", "--mode", mode,
        "--log", str(tmp_path / "early.log"),
        "--receipt", str(tmp_path / "receipt.json"),
        "--checkout-sha", SHA, "--run-id", "123", "--run-attempt", "1",
        "--event", "push", "--repository", "anupamking01/Ai-Researcher-Agent",
    ])
    return early.main()


def test_stable_regular_files_support_early_create_and_replay(tmp_path, monkeypatch):
    (tmp_path / "early.log").write_bytes(b"synthetic transcript\n")
    assert _invoke(tmp_path, monkeypatch, mode="create") == 0
    assert (tmp_path / "receipt.json").read_bytes() == early._canonical(RECEIPT)
    assert _invoke(tmp_path, monkeypatch, mode="verify") == 0


@pytest.mark.parametrize("mode", ["create", "verify"])
@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_early_cli_rejects_aliased_transcript_and_receipt(
    tmp_path, monkeypatch, capsys, mode, alias,
):
    (tmp_path / "early.log").write_bytes(b"synthetic transcript\n")
    (tmp_path / "receipt.json").write_bytes(early._canonical(RECEIPT))
    attacked = tmp_path / ("early.log" if mode == "create" else "receipt.json")
    outside = tmp_path / "outside"
    outside.write_bytes(attacked.read_bytes())
    attacked.unlink()
    if alias == "symlink":
        attacked.symlink_to(outside)
    else:
        os.link(outside, attacked)
    if mode == "create":
        (tmp_path / "receipt.json").unlink()
    with pytest.raises(SystemExit) as error:
        _invoke(tmp_path, monkeypatch, mode=mode)
    assert error.value.code == 1
    expected = "regular file" if alias == "symlink" else "exactly one filesystem link"
    assert expected in capsys.readouterr().err


def test_early_source_fingerprints_cover_imported_capture_dependencies():
    assert "scripts/verify_ci_test_evidence.py" in early.SOURCES
    assert "scripts/select_full_ci_shard.py" in early.SOURCES
    assert early.read_bounded_evidence.__module__ == "scripts.verify_ci_test_evidence"
    assert early.MAX_SOURCE_BYTES > 0
