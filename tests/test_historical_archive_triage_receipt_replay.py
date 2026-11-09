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
    with pytest.raises(verify.ReceiptVerificationError, match="inconsistent claims"):
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


@pytest.mark.parametrize("corruption", [
    "missing_row", "reordered_rows", "wrong_role", "wrong_filename", "boolean_index",
])
def test_bad_receipt_roster_rejected_before_any_archive_scan(
    tmp_path, monkeypatch, corruption,
):
    first = _zip(tmp_path / "treatment.zip", b"synthetic treatment")
    second = _zip(tmp_path / "recovery.zip", b"synthetic evaluator")
    assignments = [("original_treatment", first), ("evaluator_recovery", second)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    if corruption == "missing_row":
        doc["candidates"].pop()
    elif corruption == "reordered_rows":
        doc["candidates"].reverse()
    elif corruption == "wrong_role":
        doc["candidates"][0]["role"] = "evaluator_recovery"
    elif corruption == "wrong_filename":
        doc["candidates"][0]["supplied_filename"] = "replacement.zip"
    else:
        doc["candidates"][0]["candidate_index"] = True  # True == 1 in Python
    receipt.write_text(json.dumps(doc), encoding="utf-8")

    def no_archive_scan(*args, **kwargs):
        raise AssertionError("malformed receipt must fail before ZIP inspection")

    monkeypatch.setattr(verify.triage, "triage_candidates", no_archive_scan)
    with pytest.raises(verify.ReceiptVerificationError, match="differs"):
        verify.verify_receipt(receipt, assignments)


def test_deep_receipt_json_fails_closed_before_archive_scan(tmp_path, monkeypatch):
    candidate = _zip(tmp_path / "candidate.zip", b"synthetic")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        '{"schema_version":3,"candidates":' + "[" * 1200 + "0"
        + "]" * 1200 + "}", encoding="utf-8",
    )

    def no_archive_scan(*args, **kwargs):
        raise AssertionError("unparseable receipt must fail before ZIP inspection")

    monkeypatch.setattr(verify.triage, "triage_candidates", no_archive_scan)
    with pytest.raises(verify.ReceiptVerificationError, match="valid UTF-8 JSON"):
        verify.verify_receipt(receipt, [("original_treatment", candidate)])


@pytest.mark.parametrize("number,diagnostic", [
    ("9" * (verify.MAX_RECEIPT_NUMBER_TOKEN_CHARS + 1), "oversized JSON number"),
    ("1e400", "nonfinite JSON number"),
])
def test_invalid_receipt_numeric_tokens_fail_before_archive_scan(
    tmp_path, monkeypatch, number, diagnostic,
):
    candidate = _zip(tmp_path / "candidate.zip", b"synthetic")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        '{"schema_version":3,"candidates":[],"extra":' + number + "}",
        encoding="utf-8",
    )

    def no_archive_scan(*args, **kwargs):
        raise AssertionError("invalid JSON numeric token must fail before ZIP inspection")

    monkeypatch.setattr(verify.triage, "triage_candidates", no_archive_scan)
    with pytest.raises(verify.ReceiptVerificationError, match=diagnostic):
        verify.verify_receipt(receipt, [("original_treatment", candidate)])


@pytest.mark.parametrize("tamper", [
    "readiness", "authenticated", "role_count", "provider_count",
    "duplicate_count", "archive_budget", "negative_reservation",
    "boolean_reservation", "unknown_role", "unhashable_digest",
])
def test_contradictory_receipt_claims_fail_before_archive_scan(
    tmp_path, monkeypatch, tamper,
):
    candidate = _zip(tmp_path / "candidate.zip", b"synthetic evidence")
    assignments = [("original_treatment", candidate)]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    document = json.loads(receipt.read_text(encoding="utf-8"))

    if tamper == "readiness":
        document["human_evaluation_ready"] = True
    elif tamper == "authenticated":
        document["original_treatment_evidence_authenticated"] = True
    elif tamper == "role_count":
        document["by_role"]["original_treatment"]["candidate_count"] = 0
    elif tamper == "provider_count":
        document["by_role"]["original_treatment"]["provider_concordant_count"] = 1
    elif tamper == "duplicate_count":
        document["verified_zip_byte_duplicate_count"] = 1
    elif tamper == "archive_budget":
        document["batch_archive_byte_budget"] += 1
    elif tamper == "negative_reservation":
        document["batch_archive_bytes_reserved"] = -1
    elif tamper == "boolean_reservation":
        document["batch_declared_uncompressed_bytes_reserved"] = True
    elif tamper == "unhashable_digest":
        document["candidates"][0]["observed_regular_member_content_sha256"] = []
    else:
        document["by_role"]["invented_source"] = {}
    receipt.write_text(json.dumps(document), encoding="utf-8")

    def no_archive_scan(*args, **kwargs):
        raise AssertionError("contradictory receipt must fail before ZIP inspection")

    monkeypatch.setattr(verify.triage, "triage_candidates", no_archive_scan)
    with pytest.raises(verify.ReceiptVerificationError, match="inconsistent claims"):
        verify.verify_receipt(receipt, assignments)


@pytest.mark.parametrize("corruption", [
    "forged_provider_match", "forged_alternate_role", "forged_status",
    "boolean_zip_size", "missing_zip_digest", "nonhex_zip_digest",
    "forged_duplicate_pointer", "unexpected_verified_field",
    "failure_claims_provider", "failure_claims_success_status",
    "failure_contains_success_field", "failure_diagnostic_not_string",
    "success_flag_changed", "provider_flag_integer",
])
def test_source_identity_claims_rejected_before_any_archive_rescan(
    tmp_path, monkeypatch, corruption,
):
    """A saved receipt must not spend a large ZIP budget on impossible claims."""
    candidate = _zip(tmp_path / "synthetic.zip", b"synthetic verified candidate")
    missing = tmp_path / "missing.zip"
    assignments = [
        ("original_treatment", candidate), ("evaluator_recovery", missing),
    ]
    receipt = _receipt(tmp_path / "receipt.json", assignments)
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    verified, failed = doc["candidates"]

    if corruption == "forged_provider_match":
        verified["github_provider_zip_digest_and_size_match"] = True
    elif corruption == "forged_alternate_role":
        verified["other_role_github_provider_zip_match"] = "evaluator_recovery"
    elif corruption == "forged_status":
        verified["status"] = "github_provider_zip_concordant_not_authenticated"
    elif corruption == "boolean_zip_size":
        verified["observed_zip_bytes"] = True
    elif corruption == "missing_zip_digest":
        verified.pop("observed_zip_sha256")
    elif corruption == "nonhex_zip_digest":
        verified["observed_zip_sha256"] = "z" * 64
    elif corruption == "forged_duplicate_pointer":
        verified["duplicate_verified_zip_of_candidate_index"] = 1
    elif corruption == "unexpected_verified_field":
        verified["diagnostic"] = "synthetic"
    elif corruption == "failure_claims_provider":
        failed["github_provider_zip_digest_and_size_match"] = True
    elif corruption == "failure_claims_success_status":
        failed["status"] = "does_not_match_historical_github_provider_zip"
    elif corruption == "failure_contains_success_field":
        failed["observed_zip_sha256"] = "a" * 64
    elif corruption == "failure_diagnostic_not_string":
        failed["diagnostic"] = 1
    elif corruption == "success_flag_changed":
        verified["structural_preflight_succeeded"] = False
    else:
        verified["github_provider_zip_digest_and_size_match"] = 1

    receipt.write_text(json.dumps(doc), encoding="utf-8")

    def no_archive_scan(*_args, **_kwargs):
        raise AssertionError("invalid source claims must fail before ZIP I/O")

    monkeypatch.setattr(verify.triage, "triage_candidates", no_archive_scan)
    with pytest.raises(
        verify.ReceiptVerificationError, match="inconsistent candidate source claims"
    ):
        verify.verify_receipt(receipt, assignments)
