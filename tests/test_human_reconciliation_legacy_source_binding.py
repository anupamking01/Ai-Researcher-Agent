"""Synthetic-only regression tests for pinned legacy verifier source binding.

No treatments, evaluator calls, ratings, or human analysis are executed.
"""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path

import pytest

from scripts import verify_human_reconciliation_readiness as readiness


SOURCES = {
    "legacy_provenance_builder": "scripts/build_analysis_provenance.py",
    "legacy_provenance_verifier": "scripts/verify_analysis_provenance.py",
    "legacy_output_verifier": "scripts/verify_main_study_outputs.py",
}


def _legacy_case(tmp_path):
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    originals = {}
    for label, relative_path in SOURCES.items():
        content = f"synthetic implementation: {label}\n".encode("ascii")
        (root / relative_path).write_bytes(content)
        originals[label] = content
    receipt = {
        "provenance_builder": {
            "path": SOURCES["legacy_provenance_builder"],
            "sha256": "historical-builder-hash",
        },
        "verification_implementations": {
            "provenance": {
                "path": SOURCES["legacy_provenance_verifier"],
                "sha256": "historical-verifier-hash",
            },
            "output_consistency": {
                "path": SOURCES["legacy_output_verifier"],
                "sha256": "historical-output-hash",
            },
        },
    }
    return root, receipt, originals


def test_legacy_compatibility_hashes_exact_captured_bytes_without_mutating_receipt(
    tmp_path, monkeypatch
):
    root, receipt, original_bytes = _legacy_case(tmp_path)
    preserved = copy.deepcopy(receipt)
    calls = []

    def verify_legacy(adapted, *, root):
        assert root == tmp_path / "checkout"
        assert adapted is not receipt
        assert adapted["provenance_builder"]["sha256"] == hashlib.sha256(
            original_bytes["legacy_provenance_builder"]
        ).hexdigest()
        for key, source_label in (
            ("provenance", "legacy_provenance_verifier"),
            ("output_consistency", "legacy_output_verifier"),
        ):
            assert adapted["verification_implementations"][key]["sha256"] == (
                hashlib.sha256(original_bytes[source_label]).hexdigest()
            )
        calls.append("legacy")

    def verify_recomputed(original_receipt, *, root):
        assert original_receipt is receipt
        calls.append("recomputed")

    monkeypatch.setattr(
        readiness.verify_analysis_provenance, "verify_receipt", verify_legacy
    )
    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_recomputed_outputs",
        verify_recomputed,
    )
    readiness._verify_preserved_legacy_receipt(receipt, root=root)
    assert calls == ["legacy", "recomputed"]
    assert receipt == preserved


@pytest.mark.parametrize("source_label", tuple(SOURCES))
def test_legacy_verification_rejects_same_byte_source_replacement(
    tmp_path, monkeypatch, source_label
):
    root, receipt, originals = _legacy_case(tmp_path)
    source = root / SOURCES[source_label]
    calls = []

    def replace_after_hash(*, root, **_kwargs):
        replacement = source.with_name(source.name + ".replacement")
        replacement.write_bytes(originals[source_label])
        os.replace(replacement, source)
        calls.append("tampered")

    # The first verifier executes while the source windows are held open.
    def verify_legacy(_receipt, *, root):
        replace_after_hash(root=root)

    def verify_recomputed(_receipt, *, root):
        calls.append("recomputed")

    monkeypatch.setattr(
        readiness.verify_analysis_provenance, "verify_receipt", verify_legacy
    )
    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_recomputed_outputs",
        verify_recomputed,
    )
    with pytest.raises(ValueError, match="changed during verification"):
        readiness._verify_preserved_legacy_receipt(receipt, root=root)
    assert calls == ["tampered", "recomputed"]


def test_legacy_verification_rejects_same_byte_parent_directory_replacement(
    tmp_path, monkeypatch
):
    root, receipt, originals = _legacy_case(tmp_path)

    def swap_source_directory(_receipt, *, root):
        (root / "scripts").rename(root / "retained-old-scripts")
        replacement = root / "scripts"
        replacement.mkdir()
        for label, path in SOURCES.items():
            (replacement / Path(path).name).write_bytes(originals[label])

    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_receipt",
        swap_source_directory,
    )
    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_recomputed_outputs",
        lambda _receipt, *, root: None,
    )
    with pytest.raises(ValueError, match="changed during verification"):
        readiness._verify_preserved_legacy_receipt(receipt, root=root)
