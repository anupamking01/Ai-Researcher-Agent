"""Immutable provider-observed source escrow: bytes and evidence-claim boundaries.

This tests the actually committed canonical ZIP. It does not authenticate
historical treatment traces or produce any human ratings.
"""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import preflight_recovered_artifact_zip as zip_preflight
from scripts import verify_canonical_archive_checkout as concordance
from scripts import verify_retained_canonical_download as source

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research-evidence" / "canonical-analysis-36070798723"
ZIP = Path(str(BASE) + ".zip")
METADATA = Path(str(BASE) + ".metadata.json")
RECEIPT = Path(str(BASE) + ".verification.json")


def _load_json(path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=source._unique_object,
        parse_constant=source._reject_constant,
    )


def test_git_escrow_is_exact_original_provider_observed_zip():
    assert ZIP.is_file(), "verified canonical ZIP must be checked into Git"
    blob = ZIP.read_bytes()
    assert len(blob) == source.OBSERVED_ZIP_BYTES == 10270
    assert hashlib.sha256(blob).hexdigest() == source.OBSERVED_ZIP_SHA256
    inspected = zip_preflight.audit_recovered_zip(ZIP)
    assert {item["path"] for item in inspected["files"]} == set(
        concordance.CANONICAL_MEMBERS
    )
    for item in inspected["files"]:
        path = item["path"]
        observed = item["sha256"]
        if path == concordance.PROVENANCE_RECEIPT:
            assert observed == concordance.PUBLISHED_ARCHIVED_PROVENANCE_SHA256
        else:
            assert observed == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_git_escrow_records_provider_identity_without_authentication_overclaim():
    metadata, receipt = _load_json(METADATA), _load_json(RECEIPT)
    assert metadata["id"] == receipt["source_artifact_id"] == source.ARTIFACT_ID
    assert metadata["name"] == source.ARTIFACT_NAME
    assert metadata["workflow_run"]["id"] == source.RUN_ID
    assert metadata["workflow_run"]["head_sha"] == source.RUN_HEAD
    assert metadata["digest"] == "sha256:" + source.OBSERVED_ZIP_SHA256
    assert receipt["archive_sha256_observed_now"] == source.OBSERVED_ZIP_SHA256
    assert receipt["provider_reported_zip_sha256_matched"] is True
    assert receipt["published_provider_observed_zip_sha256_matched"] is True
    assert receipt["checkout_concordance"]["historical_workflow_receipt_exception_used"] is True
    assert receipt["independent_historical_custody_authenticated"] is False
    assert receipt["original_treatment_traces_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["treatments_or_evaluators_rerun"] is False
    assert receipt["human_ratings_generated"] is False


def test_altered_git_escrow_bytes_fail_before_any_analysis(tmp_path):
    altered = bytearray(ZIP.read_bytes())
    altered[0] ^= 1
    bad = tmp_path / "tampered-canonical.zip"
    bad.write_bytes(altered)
    with pytest.raises(ValueError, match="retained ZIP bytes differ"):
        source.verify_download(METADATA, bad, root=tmp_path)
