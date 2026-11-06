"""Synthetic-only regressions: no original ZIPs, treatments or ratings."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from scripts import triage_historical_archive_candidates as triage
from scripts import verify_historical_archive_triage_receipt as verify


def _zip(path: Path, content: bytes) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("reports/synthetic.md", content)
    return path


def _receipt(path: Path, assignments) -> Path:
    path.write_text(
        json.dumps(triage.triage_candidates(assignments), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def test_full_exact_replay_is_read_only_and_never_authenticates(tmp_path):
    first = _zip(tmp_path / "treatment.zip", b"treatment fixture")
    second = _zip(tmp_path / "recovery.zip", b"recovery fixture")
    assignments = [("evaluator_recovery", second), ("original_treatment", first)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    before = {p.name: p.read_bytes() for p in (first, second, receipt)}
    result = verify.verify_receipt(receipt, assignments)
    assert result["candidate_count"] == 2
    assert result["full_recorded_inventory_replayed"] is True
    for name in ("historical_evidence_authenticated", "human_evaluation_ready",
                 "experimental_treatments_rerun", "evaluator_rerun",
                 "human_ratings_generated"):
        assert result[name] is False
    assert before == {p.name: p.read_bytes() for p in (first, second, receipt)}


def test_replay_rejects_changed_candidate_bytes(tmp_path):
    candidate = _zip(tmp_path / "candidate.zip", b"before")
    assignments = [("original_treatment", candidate)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    _zip(candidate, b"after")
    with pytest.raises(verify.ReceiptVerificationError, match="differs"):
        verify.verify_receipt(receipt, assignments)


def test_replay_rejects_changed_receipt_claim_even_when_python_compares_equal(tmp_path):
    candidate = _zip(tmp_path / "candidate.zip", b"synthetic")
    assignments = [("original_treatment", candidate)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    doc = json.loads(receipt.read_text())
    doc["all_explicit_candidates_accounted_for"] = 1  # 1 == True in Python
    receipt.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(verify.ReceiptVerificationError, match="differs"):
        verify.verify_receipt(receipt, assignments)


def test_replay_rejects_different_order_and_declared_role(tmp_path):
    first = _zip(tmp_path / "first.zip", b"one")
    second = _zip(tmp_path / "second.zip", b"two")
    assignments = [("original_treatment", first), ("evaluator_recovery", second)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    with pytest.raises(verify.ReceiptVerificationError, match="differs"):
        verify.verify_receipt(receipt, list(reversed(assignments)))
    with pytest.raises(verify.ReceiptVerificationError, match="differs"):
        verify.verify_receipt(receipt, [
            ("evaluator_recovery", first), ("original_treatment", second),
        ])


def test_replay_rejects_duplicate_json_keys(tmp_path):
    candidate = _zip(tmp_path / "candidate.zip", b"synthetic")
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"schema_version":3,"schema_version":3}', encoding="utf-8")
    with pytest.raises(verify.ReceiptVerificationError, match="duplicate JSON"):
        verify.verify_receipt(receipt, [("original_treatment", candidate)])


def test_replay_rejects_unbounded_receipt_before_scanning_archives(tmp_path, monkeypatch):
    candidate = _zip(tmp_path / "candidate.zip", b"synthetic")
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(b"x" * (verify.MAX_RECEIPT_BYTES + 1))
    def no_scan(*args, **kwargs):
        raise AssertionError("reject oversized receipt before scanning any archive")
    monkeypatch.setattr(verify.triage, "triage_candidates", no_scan)
    with pytest.raises(verify.ReceiptVerificationError, match="stable bounded"):
        verify.verify_receipt(receipt, [("original_treatment", candidate)])


def test_failed_candidate_inventory_is_diagnostic_only_without_source_digest(tmp_path):
    candidate = tmp_path / "missing.zip"
    assignments = [("original_treatment", candidate)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    result = verify.verify_receipt(receipt, assignments)
    assert result["diagnostic_inventory_replayed"] is True
    assert result["full_recorded_inventory_replayed"] is False
    assert result["unverified_candidate_indexes"] == [1]
    assert result["status"].endswith("unverified_candidate_sources")
    assert result["human_evaluation_ready"] is False


def test_different_invalid_zip_bytes_cannot_yield_full_source_replay(tmp_path):
    candidate = tmp_path / "corrupt.zip"
    candidate.write_bytes(b"invalid-A")
    assignments = [("original_treatment", candidate)]
    original = triage.triage_candidates(assignments)
    assert original["candidates"][0]["status"] == "structural_preflight_failed"
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    # Both source generations produce exactly the same negative diagnostic.
    # A row-only comparison would incorrectly assert full replay success.
    candidate.write_bytes(b"invalid-B")
    assert triage.triage_candidates(assignments) == original
    result = verify.verify_receipt(receipt, assignments)
    assert result["diagnostic_inventory_replayed"] is True
    assert result["full_recorded_inventory_replayed"] is False
    assert result["unverified_candidate_indexes"] == [1]


def test_partial_replay_prints_diagnostic_but_cli_exits_nonzero(tmp_path, monkeypatch, capsys):
    import sys

    valid = _zip(tmp_path / "valid.zip", b"present")
    invalid = tmp_path / "missing.zip"
    assignments = [("original_treatment", valid), ("evaluator_recovery", invalid)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    monkeypatch.setattr(sys, "argv", [
        "verify_historical_archive_triage_receipt.py",
        "--receipt", str(receipt),
        "--original-treatment", str(valid),
        "--evaluator-recovery", str(invalid),
    ])
    assert verify.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostic_inventory_replayed"] is True
    assert result["full_recorded_inventory_replayed"] is False
    assert result["unverified_candidate_indexes"] == [2]
    assert result["human_evaluation_ready"] is False
