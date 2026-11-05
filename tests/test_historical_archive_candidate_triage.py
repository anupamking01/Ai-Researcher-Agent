"""Synthetic tests for read-only, all-candidate historical ZIP triage."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts import triage_historical_archive_candidates as triage


def _zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr("synthetic/report.md", "# Not a historical result\n")
    return path


def test_every_supplied_candidate_is_reported_without_modification(tmp_path):
    good = _zip(tmp_path / "good.zip")
    second = _zip(tmp_path / "second.zip")
    invalid = tmp_path / "broken.zip"
    invalid.write_bytes(b"not a ZIP")
    before = {path.name: path.read_bytes() for path in (good, second, invalid)}
    receipt = triage.triage_candidates([
        ("original_treatment", good),
        ("original_treatment", invalid),
        ("evaluator_recovery", second),
    ])

    assert [row["candidate_index"] for row in receipt["candidates"]] == [1, 2, 3]
    assert [row["role"] for row in receipt["candidates"]] == [
        "original_treatment", "original_treatment", "evaluator_recovery"
    ]
    assert [row["status"] for row in receipt["candidates"]] == [
        "does_not_match_historical_github_provider_zip",
        "structural_preflight_failed",
        "does_not_match_historical_github_provider_zip",
    ]
    assert receipt["by_role"]["original_treatment"]["candidate_count"] == 2
    assert receipt["by_role"]["evaluator_recovery"]["candidate_count"] == 1
    assert receipt["original_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["supplied_candidates_proven_exhaustive"] is False
    assert {path.name: path.read_bytes() for path in (good, second, invalid)} == before
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(before)


@pytest.mark.parametrize("role", triage.ROLES)
def test_matching_provider_zip_is_not_authentication(tmp_path, monkeypatch, role):
    anchor = triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES[role]
    path = _zip(tmp_path / "synthetic.zip")

    def mocked_structural_inspection(path_arg):
        assert path_arg == path
        return {
            "archive_bytes": anchor["size_bytes"],
            "archive_sha256_observed_now": anchor["zip_sha256"],
            "file_count": 40,
        }

    monkeypatch.setattr(triage.zip_preflight, "audit_recovered_zip", mocked_structural_inspection)
    receipt = triage.triage_candidates([(role, path)])
    row = receipt["candidates"][0]
    assert row["github_provider_zip_digest_and_size_match"] is True
    assert row["status"] == "github_provider_zip_concordant_not_authenticated"
    assert receipt["by_role"][role]["provider_concordant_count"] == 1
    assert receipt["original_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False


@pytest.mark.parametrize("field", ["archive_bytes", "archive_sha256_observed_now"])
def test_both_historical_byte_size_and_digest_required(tmp_path, monkeypatch, field):
    role = "original_treatment"
    anchor = triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES[role]
    observed = {
        "archive_bytes": anchor["size_bytes"],
        "archive_sha256_observed_now": anchor["zip_sha256"],
        "file_count": 40,
    }
    observed[field] = 123 if field == "archive_bytes" else "0" * 64
    monkeypatch.setattr(
        triage.zip_preflight, "audit_recovered_zip", lambda path: observed
    )
    receipt = triage.triage_candidates([(role, tmp_path / "synthetic.zip")])
    assert receipt["candidates"][0]["github_provider_zip_digest_and_size_match"] is False
    assert receipt["by_role"][role]["provider_concordant_count"] == 0


def test_duplicate_or_invalid_candidate_inventory_rejected_before_io(tmp_path, monkeypatch):
    path = tmp_path / "candidate.zip"
    monkeypatch.setattr(
        triage.zip_preflight, "audit_recovered_zip",
        lambda path: pytest.fail("should not inspect an invalid inventory"),
    )
    with pytest.raises(triage.CandidateTriageError, match="same candidate path"):
        triage.triage_candidates([
            ("original_treatment", path),
            ("evaluator_recovery", tmp_path / "." / "candidate.zip"),
        ])
    with pytest.raises(triage.CandidateTriageError, match="unknown historical archive role"):
        triage.triage_candidates([("canonical_analysis", path)])
    with pytest.raises(triage.CandidateTriageError, match="provide 1 to"):
        triage.triage_candidates([])
    with pytest.raises(triage.CandidateTriageError, match="provide 1 to"):
        triage.triage_candidates([("original_treatment", Path(str(i))) for i in range(17)])


def test_cli_has_no_side_effects_and_never_claims_custody(tmp_path, monkeypatch, capsys):
    path = _zip(tmp_path / "candidate.zip")
    digest_before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr("sys.argv", ["triage", "--original-treatment", str(path)])
    assert triage.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "candidate_triage_only_no_historical_authentication"
    assert result["human_evaluation_ready"] is False
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest_before
    assert list(tmp_path.iterdir()) == [path]


def test_distinct_paths_with_identical_zip_bytes_are_one_unique_candidate(tmp_path):
    first = _zip(tmp_path / "first.zip")
    copy = tmp_path / "copy.zip"
    copy.write_bytes(first.read_bytes())
    different = tmp_path / "different.zip"
    with zipfile.ZipFile(different, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr("synthetic/different-report.md", "# Another synthetic case\\n")

    receipt = triage.triage_candidates([
        ("original_treatment", first),
        ("original_treatment", copy),
        ("original_treatment", different),
    ])
    assert [row["duplicate_verified_zip_of_candidate_index"] for row in receipt["candidates"]] == [
        None, 1, None,
    ]
    assert receipt["verified_zip_byte_duplicate_count"] == 1
    assert receipt["by_role"]["original_treatment"]["candidate_count"] == 3
    assert receipt["by_role"]["original_treatment"]["distinct_structurally_verified_zip_count"] == 2
    assert receipt["by_role"]["original_treatment"]["distinct_provider_concordant_zip_count"] == 0
    assert receipt["all_explicit_candidates_accounted_for"] is True
    assert receipt["distinct_zip_bytes_establish_independent_custody"] is False


def test_repeat_provider_concordance_does_not_count_same_bytes_twice(tmp_path, monkeypatch):
    anchor = triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES["original_treatment"]
    def mocked_preflight(path):
        return {
            "archive_bytes": anchor["size_bytes"],
            "archive_sha256_observed_now": anchor["zip_sha256"],
            "file_count": 40,
        }
    monkeypatch.setattr(triage.zip_preflight, "audit_recovered_zip", mocked_preflight)
    receipt = triage.triage_candidates([
        ("original_treatment", tmp_path / "copy-a.zip"),
        ("original_treatment", tmp_path / "copy-b.zip"),
    ])
    summary = receipt["by_role"]["original_treatment"]
    assert summary["candidate_count"] == 2
    assert summary["provider_concordant_count"] == 2
    assert summary["distinct_provider_concordant_zip_count"] == 1
    assert receipt["candidates"][1]["duplicate_verified_zip_of_candidate_index"] == 1
    assert receipt["original_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False


def test_duplicate_identity_is_cross_role_and_failed_candidates_are_retained(tmp_path):
    first = _zip(tmp_path / "source.zip")
    second = tmp_path / "recovery.zip"
    second.write_bytes(first.read_bytes())
    unsafe = tmp_path / "invalid.zip"
    unsafe.write_bytes(b"not-a-zip")
    receipt = triage.triage_candidates([
        ("original_treatment", first),
        ("original_treatment", unsafe),
        ("evaluator_recovery", second),
    ])
    assert [row["duplicate_verified_zip_of_candidate_index"] for row in receipt["candidates"]] == [
        None, None, 1,
    ]
    assert receipt["candidates"][1]["status"] == "structural_preflight_failed"
    assert "observed_zip_sha256" not in receipt["candidates"][1]
    assert receipt["by_role"]["original_treatment"]["distinct_structurally_verified_zip_count"] == 1
    assert receipt["by_role"]["evaluator_recovery"]["distinct_structurally_verified_zip_count"] == 1
    assert receipt["verified_zip_byte_duplicate_count"] == 1
    assert receipt["all_explicit_candidates_accounted_for"] is True
