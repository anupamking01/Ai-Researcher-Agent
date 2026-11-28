"""Synthetic-only checks that hashed and parsed frozen ratings cannot diverge.

File edits are injected at a deterministic read boundary, not with timing or
threads. No values here are collected human annotations or study results.
"""
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as verify
from human_eval_test_support import write_valid_annotator_attestations


@pytest.fixture
def frozen_case(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text(
        json.dumps({
            "blind_id": "H001", "task_id": "synthetic-01",
            "question": "Synthetic question", "report_markdown": "Synthetic report",
        }) + "\n", encoding="utf-8",
    )
    ratings = []
    for annotator in ("synthetic-a", "synthetic-b"):
        path = tmp_path / f"{annotator}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(freeze.RATING_FIELDS)
            writer.writerow([annotator, "H001", "3", "3", "4", "4", "3", ""])
        ratings.append(path)
    root = tmp_path / "frozen"
    freeze.freeze_ratings(
        ratings,
        annotator_attestations_path=write_valid_annotator_attestations(
            tmp_path / "annotator_attestations.csv",
            ("synthetic-a", "synthetic-b"),
        ),
        packet_path=packet,
        output_root=root,
    )
    return root, packet


def _verify(case, retained):
    root, packet = case
    options = {"use_retained_inputs": True} if retained else {"packet_path": packet}
    return verify.verify_frozen_snapshot(freeze_root=root, **options)


def _snapshot(root):
    return {path.relative_to(root): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def _inject_edit(case, monkeypatch, kind):
    root, _ = case
    path = root / "frozen_ratings.csv"
    original = path.read_bytes()
    if kind == "line_endings":
        assert b"\r\n" in original
        first, second = original, original.replace(b"\r\n", b"\n")
    else:
        # Hash a substituted score, then restore the genuine rows for parsing.
        # Both revisions have the same length, so checking byte count alone fails.
        needle = b"synthetic-a,H001,3,"
        assert needle in original
        first, second = original.replace(needle, b"synthetic-a,H001,4,", 1), original
        assert len(first) == len(second)
        path.write_bytes(first)
        manifest_path = root / "freeze_manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["frozen_ratings"].update(
            bytes=len(first), sha256=hashlib.sha256(first).hexdigest(),
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = _snapshot(root)
    real_read = Path.read_bytes
    real_pread = freeze.os.pread
    path_stat = path.stat()
    target_identity = (path_stat.st_dev, path_stat.st_ino)
    reads = []
    agreement_reads = []

    def edit_after_read(source):
        content = real_read(source)
        if source == path:
            reads.append(content)
            if len(reads) == 1:
                source.write_bytes(second)
        if source == root / "agreement.json":
            agreement_reads.append(content)
        return content

    def observe_descriptor_read(file_descriptor, size, offset):
        content = real_pread(file_descriptor, size, offset)
        opened = freeze.os.fstat(file_descriptor)
        if (
            content
            and offset == 0
            and (opened.st_dev, opened.st_ino) == target_identity
        ):
            reads.append(content)
            if len(reads) == 1:
                path.write_bytes(second)
        return content

    monkeypatch.setattr(Path, "read_bytes", edit_after_read)
    monkeypatch.setattr(freeze.os, "pread", observe_descriptor_read)
    return first, second, before, reads, agreement_reads


@pytest.mark.parametrize("retained", [False, True], ids=["external", "retained"])
@pytest.mark.parametrize("kind", ["line_endings", "substituted_score"])
def test_edit_between_hash_and_parse_is_rejected(frozen_case, monkeypatch, retained, kind):
    root, _ = frozen_case
    with monkeypatch.context() as context:
        first, second, before, reads, agreement_reads = _inject_edit(
            frozen_case, context, kind,
        )
        with pytest.raises(
            ValueError,
            match=(
                "frozen ratings changed while it was being read"
                "|frozen-ratings parsed fingerprint"
            ),
        ):
            _verify(frozen_case, retained)
    assert reads[0] == first
    assert not agreement_reads  # Reject before recomputing/reporting agreement.
    before[Path("frozen_ratings.csv")] = second
    assert _snapshot(root) == before  # The verifier did not repair or rewrite files.


@pytest.mark.parametrize("retained", [False, True], ids=["external", "retained"])
def test_unchanged_freeze_still_verifies_without_writes(frozen_case, retained):
    root, _ = frozen_case
    before = _snapshot(root)
    receipt = _verify(frozen_case, retained)
    assert receipt["status"] == "blinded_human_ratings_verified"
    assert receipt["blinding_key_used"] is False
    assert receipt["n_rows"] == 2
    assert _snapshot(root) == before


def test_manifest_path_replacement_during_capture_is_rejected(
    frozen_case, monkeypatch
):
    """A byte-identical pathname swap must not become newly trusted."""
    root, _ = frozen_case
    target = root / "freeze_manifest.json"
    replacement = root / "freeze_manifest.replacement.json"
    replacement.write_bytes(target.read_bytes())
    target_stat = target.stat()
    target_identity = (target_stat.st_dev, target_stat.st_ino)
    real_read = Path.read_bytes
    real_pread = os.pread
    replaced = False

    def replace_target():
        nonlocal replaced
        if not replaced:
            os.replace(replacement, target)
            replaced = True

    def replace_after_path_read(source):
        content = real_read(source)
        if source == target:
            replace_target()
        return content

    def replace_after_descriptor_read(file_descriptor, size, offset):
        content = real_pread(file_descriptor, size, offset)
        opened = os.fstat(file_descriptor)
        if (
            content
            and offset == 0
            and (opened.st_dev, opened.st_ino) == target_identity
        ):
            replace_target()
        return content

    monkeypatch.setattr(Path, "read_bytes", replace_after_path_read)
    monkeypatch.setattr(os, "pread", replace_after_descriptor_read)

    with pytest.raises(ValueError, match="freeze manifest changed while it was being read"):
        _verify(frozen_case, retained=True)


def test_undeclared_sidecar_added_after_layout_check_is_rejected(
    frozen_case, monkeypatch
):
    """A late bundle addition must not coexist with a success receipt."""
    root, _ = frozen_case
    real_verify_layout = verify._verify_bundle_layout
    injected = False

    def add_sidecar_after_layout(freeze_root, manifest):
        nonlocal injected
        real_verify_layout(freeze_root, manifest)
        if not injected:
            (root / "raw_rating_inputs" / "late-sidecar.txt").write_text(
                "undeclared\n", encoding="utf-8"
            )
            injected = True

    monkeypatch.setattr(verify, "_verify_bundle_layout", add_sidecar_after_layout)

    with pytest.raises(
        ValueError, match="freeze root changed while it was being verified"
    ):
        _verify(frozen_case, retained=True)


def test_cli_read_drift_has_no_success_receipt(frozen_case, monkeypatch, capsys):
    root, _ = frozen_case
    _inject_edit(frozen_case, monkeypatch, "line_endings")
    monkeypatch.setattr(sys, "argv", [
        "verify_human_eval_freeze", "--freeze-root", str(root), "--retained-inputs",
    ])
    with pytest.raises(
        SystemExit,
        match=(
            "HUMAN EVAL VERIFY: FAIL:.*"
            "(changed while it was being read|parsed fingerprint)"
        ),
    ):
        verify.main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "HUMAN EVAL VERIFY: PASS" not in captured.err
