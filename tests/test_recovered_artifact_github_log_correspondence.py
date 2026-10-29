"""Synthetic, offline ZIP-correspondence tests; no research artifacts or reruns."""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile

import pytest

from scripts import preflight_recovered_artifact_zip as preflight


def _zip(path, payload=b"synthetic evidence"):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("reports/synthetic.md", payload)
    return path


def _synthetic_log_anchor(monkeypatch, role, path, *, sha=None, size=None):
    original = preflight.GITHUB_JOB_LOG_ARCHIVES[role]
    anchor = {
        **original,
        "zip_sha256": sha if sha is not None else hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": size if size is not None else path.stat().st_size,
    }
    monkeypatch.setattr(preflight, "GITHUB_JOB_LOG_ARCHIVES", {
        **preflight.GITHUB_JOB_LOG_ARCHIVES, role: anchor,
    })
    return anchor


@pytest.mark.parametrize("role", ("original_treatment", "evaluator_recovery"))
def test_same_provider_correspondence_is_explicitly_not_independent_custody(
    tmp_path, monkeypatch, role
):
    path = _zip(tmp_path / "synthetic.zip")
    anchor = _synthetic_log_anchor(monkeypatch, role, path)
    receipt = preflight.audit_recovered_zip(path, github_job_log_artifact=role)
    match = receipt["github_job_log_zip_correspondence"]
    assert match["source"] == "github_actions_same_provider_job_log"
    assert match["artifact_role"] == role
    assert match["source_run_id"] == anchor["run_id"]
    assert match["source_job_id"] == anchor["job_id"]
    assert match["source_artifact_id"] == anchor["artifact_id"]
    assert match["expected_archive_sha256"] == anchor["zip_sha256"]
    assert match["expected_archive_bytes"] == anchor["size_bytes"]
    assert match["sha256_and_byte_size_matched"] is True
    assert match["independent_archive_pin"] is False
    assert receipt["expected_archive_sha256_matched"] is False
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["file_count"] == 1
    assert list(tmp_path.iterdir()) == [path]


def test_same_byte_count_different_zip_digest_cannot_match(tmp_path, monkeypatch):
    expected = _zip(tmp_path / "logged.zip", b"first")
    candidate = _zip(tmp_path / "candidate.zip", b"other")
    assert expected.stat().st_size == candidate.stat().st_size
    assert expected.read_bytes() != candidate.read_bytes()
    _synthetic_log_anchor(monkeypatch, "original_treatment", expected)
    with pytest.raises(preflight.RecoveredArchiveError, match="SHA-256 differs from historical GitHub"):
        preflight.audit_recovered_zip(candidate, github_job_log_artifact="original_treatment")


def test_matching_sha_but_wrong_logged_byte_count_is_rejected(tmp_path, monkeypatch):
    path = _zip(tmp_path / "candidate.zip")
    _synthetic_log_anchor(
        monkeypatch, "evaluator_recovery", path, size=path.stat().st_size + 1,
    )
    with pytest.raises(preflight.RecoveredArchiveError, match="byte size differs from historical GitHub"):
        preflight.audit_recovered_zip(path, github_job_log_artifact="evaluator_recovery")


@pytest.mark.parametrize("role", ("other", 0, True))
def test_unknown_or_nonstring_role_is_rejected_before_io(tmp_path, role):
    with pytest.raises(preflight.RecoveredArchiveError, match="unknown historical GitHub job-log artifact"):
        preflight.audit_recovered_zip(tmp_path / "missing.zip", github_job_log_artifact=role)


def test_ordinary_structural_preflight_does_not_infer_github_log_match(tmp_path):
    path = _zip(tmp_path / "candidate.zip")
    receipt = preflight.audit_recovered_zip(path)
    assert receipt["github_job_log_zip_correspondence"] is None
    assert receipt["expected_archive_sha256_matched"] is False


def test_distinct_github_and_independent_pin_receipt_fields(tmp_path, monkeypatch):
    path = _zip(tmp_path / "candidate.zip")
    anchor = _synthetic_log_anchor(monkeypatch, "original_treatment", path)
    receipt = preflight.audit_recovered_zip(
        path, expected_archive_sha256=anchor["zip_sha256"],
        github_job_log_artifact="original_treatment",
    )
    assert receipt["expected_archive_sha256_matched"] is True
    assert receipt["github_job_log_zip_correspondence"]["independent_archive_pin"] is False
    assert receipt["historical_evidence_authenticated"] is False


def test_cli_exposes_explicit_github_log_role_without_promoting_provenance(
    tmp_path, monkeypatch, capsys
):
    path = _zip(tmp_path / "synthetic.zip")
    _synthetic_log_anchor(monkeypatch, "evaluator_recovery", path)
    monkeypatch.setattr(sys, "argv", [
        "preflight_recovered_artifact_zip", str(path),
        "--github-job-log-artifact", "evaluator_recovery",
    ])
    assert preflight.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["github_job_log_zip_correspondence"]["artifact_role"] == "evaluator_recovery"
    assert receipt["expected_archive_sha256_matched"] is False
    assert receipt["historical_evidence_authenticated"] is False
