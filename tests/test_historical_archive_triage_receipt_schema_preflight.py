"""Synthetic source-recovery receipt schema checks; no original reports or ratings."""
from __future__ import annotations

import json
import zipfile

import pytest

from scripts import triage_historical_archive_candidates as triage
from scripts import verify_historical_archive_triage_receipt as verify


def _sample(tmp_path):
    candidate = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(candidate, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("reports/fictional.md", b"synthetic fixture only")
    # Include a failed source row to exercise controlled diagnostic parsing.
    assignments = [
        ("original_treatment", candidate),
        ("evaluator_recovery", tmp_path / "absent.zip"),
    ]
    document = triage.triage_candidates(assignments)
    receipt = tmp_path / "triage.json"
    receipt.write_text(json.dumps(document), encoding="utf-8")
    return receipt, assignments, document


def test_producer_claim_contract_is_preserved_for_a_valid_receipt(tmp_path):
    receipt, assignments, document = _sample(tmp_path)
    assert document["interpretation"] == triage.TRIAGE_INTERPRETATION
    result = verify.verify_receipt(receipt, assignments)
    assert result["diagnostic_inventory_replayed"] is True
    assert result["full_recorded_inventory_replayed"] is False
    assert result["historical_evidence_authenticated"] is False
    assert result["human_evaluation_ready"] is False


@pytest.mark.parametrize("change", [
    "omitted_interpretation",
    "reworded_interpretation",
    "object_interpretation",
    "extra_readiness_claim",
    "removed_non_authentication_claim",
    "nonstring_top_level_status",
    "failed_candidate_status_list",
    "failed_candidate_status_object",
])
def test_corrupted_schema_and_claim_text_fail_before_rescanning_sources(
    tmp_path, monkeypatch, change,
):
    receipt, assignments, document = _sample(tmp_path)
    if change == "omitted_interpretation":
        del document["interpretation"]
    elif change == "reworded_interpretation":
        document["interpretation"] += " Human evaluation is complete."
    elif change == "object_interpretation":
        document["interpretation"] = {"claim": "authenticated"}
    elif change == "extra_readiness_claim":
        document["human_evaluation_complete"] = True
    elif change == "removed_non_authentication_claim":
        del document["github_service_metadata_is_independent_custody"]
    elif change == "nonstring_top_level_status":
        document["status"] = []
    elif change == "failed_candidate_status_list":
        document["candidates"][1]["status"] = []
    else:
        document["candidates"][1]["status"] = {"nested": "failure"}
    receipt.write_text(json.dumps(document), encoding="utf-8")

    def forbidden_archive_scan(*_args, **_kwargs):
        raise AssertionError("invalid receipt must not rescan candidate ZIPs")

    monkeypatch.setattr(verify.triage, "triage_candidates", forbidden_archive_scan)
    with pytest.raises(verify.ReceiptVerificationError, match="inconsistent claims"):
        verify.verify_receipt(receipt, assignments)
