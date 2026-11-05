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


def test_failed_filesystem_lookup_does_not_disclose_backup_directories(tmp_path):
    """Real preflight OS errors contain full paths; public JSON receipts must not."""
    secret_root = tmp_path / "confidential-backup-location"
    absent = secret_root / "candidate.zip"
    receipt = triage.triage_candidates([("original_treatment", absent)])
    row = receipt["candidates"][0]
    serialized = json.dumps(receipt, sort_keys=True)
    assert row["status"] == "structural_preflight_failed"
    assert row["supplied_filename"] == "candidate.zip"
    assert row["diagnostic"] == "cannot safely inspect ZIP: filesystem error (ENOENT)"
    assert "confidential-backup-location" not in serialized
    assert str(tmp_path) not in serialized
    assert receipt["all_explicit_candidates_accounted_for"] is True
    assert receipt["human_evaluation_ready"] is False


def test_wrapped_permission_error_is_sanitized_without_masking_other_failures(
    tmp_path, monkeypatch,
):
    """OSError cause chains retain the category without leaking file paths."""
    secret = tmp_path / "private-custody-directory" / "evidence.zip"

    def reject(_path, **_kwargs):
        try:
            raise PermissionError(13, "Permission denied", str(secret))
        except PermissionError as cause:
            raise triage.zip_preflight.RecoveredArchiveError(
                f"cannot safely inspect ZIP: {cause}"
            ) from cause

    monkeypatch.setattr(triage.zip_preflight, "audit_recovered_zip", reject)
    receipt = triage.triage_candidates([("evaluator_recovery", secret)])
    row = receipt["candidates"][0]
    assert row["diagnostic"] == "cannot safely inspect ZIP: filesystem error (EACCES)"
    assert "private-custody-directory" not in json.dumps(receipt)
    assert row["status"] == "structural_preflight_failed"
    assert row["observed_regular_member_content_sha256"] is None

    malformed = tmp_path / "broken.zip"
    malformed.write_bytes(b"not a ZIP")
    monkeypatch.undo()
    other = triage.triage_candidates([("original_treatment", malformed)])
    assert other["candidates"][0]["status"] == "structural_preflight_failed"
    assert "cannot safely inspect ZIP" in other["candidates"][0]["diagnostic"]
    assert other["original_treatment_evidence_authenticated"] is False


@pytest.mark.parametrize("role", triage.ROLES)
def test_matching_provider_zip_is_not_authentication(tmp_path, monkeypatch, role):
    anchor = triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES[role]
    path = _zip(tmp_path / "synthetic.zip")

    def mocked_structural_inspection(path_arg, **_kwargs):
        assert path_arg == path
        return {
            "archive_bytes": anchor["size_bytes"],
            "archive_sha256_observed_now": anchor["zip_sha256"],
            "file_count": 40,
            "files": [
                {"path": "synthetic/report.md", "uncompressed_bytes": 12,
                 "sha256": "a" * 64},
            ],
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
            "files": [
                {"path": "synthetic/report.md", "uncompressed_bytes": 12,
                 "sha256": "a" * 64},
            ],
    }
    observed[field] = 123 if field == "archive_bytes" else "0" * 64
    monkeypatch.setattr(
        triage.zip_preflight, "audit_recovered_zip", lambda path, **_kwargs: observed
    )
    receipt = triage.triage_candidates([(role, tmp_path / "synthetic.zip")])
    assert receipt["candidates"][0]["github_provider_zip_digest_and_size_match"] is False
    assert receipt["by_role"][role]["provider_concordant_count"] == 0


def test_duplicate_or_invalid_candidate_inventory_rejected_before_io(tmp_path, monkeypatch):
    path = tmp_path / "candidate.zip"
    monkeypatch.setattr(
        triage.zip_preflight, "audit_recovered_zip",
        lambda path, **_kwargs: pytest.fail("should not inspect an invalid inventory"),
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


@pytest.mark.parametrize(
    "roles",
    [
        ("evaluator_recovery", "original_treatment", "evaluator_recovery"),
        ("original_treatment", "evaluator_recovery", "original_treatment"),
    ],
)
def test_cli_preserves_interleaved_roles_and_first_observed_duplicate_indices(
    tmp_path, monkeypatch, capsys, roles,
):
    """Source-recovery receipt indices must follow argv, not grouped roles."""
    first = _zip(tmp_path / "first.zip")
    second = tmp_path / "same-content.zip"
    second.write_bytes(first.read_bytes())
    rejected = tmp_path / "broken.zip"
    rejected.write_bytes(b"invalid ZIP bytes")
    paths = (first, second, rejected)
    before = [path.read_bytes() for path in paths]
    switches = {
        "original_treatment": "--original-treatment",
        "evaluator_recovery": "--evaluator-recovery",
    }
    argv = ["triage"]
    for role, path in zip(roles, paths):
        argv.extend([switches[role], str(path)])
    monkeypatch.setattr("sys.argv", argv)

    assert triage.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    rows = receipt["candidates"]
    assert [row["candidate_index"] for row in rows] == [1, 2, 3]
    assert [row["role"] for row in rows] == list(roles)
    assert [row["supplied_filename"] for row in rows] == [path.name for path in paths]
    assert rows[0]["duplicate_verified_zip_of_candidate_index"] is None
    assert rows[1]["duplicate_verified_zip_of_candidate_index"] == 1
    assert rows[1]["same_regular_members_as_candidate_index"] == 1
    assert rows[2]["status"] == "structural_preflight_failed"
    assert receipt["all_explicit_candidates_accounted_for"] is True
    assert receipt["original_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert [path.read_bytes() for path in paths] == before


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
    def mocked_preflight(path, **_kwargs):
        return {
            "archive_bytes": anchor["size_bytes"],
            "archive_sha256_observed_now": anchor["zip_sha256"],
            "file_count": 40,
            "files": [
                {"path": "synthetic/report.md", "uncompressed_bytes": 12,
                 "sha256": "a" * 64},
            ],
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


@pytest.mark.parametrize(
    ("declared_role", "matched_role"),
    [
        ("original_treatment", "evaluator_recovery"),
        ("evaluator_recovery", "original_treatment"),
    ],
)
def test_other_role_pin_match_is_flagged_without_reassigning(
    tmp_path, monkeypatch, declared_role, matched_role,
):
    anchor = triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES[matched_role]
    examined = []
    def inspect(path, **_kwargs):
        examined.append(path)
        return {
            "archive_bytes": anchor["size_bytes"],
            "archive_sha256_observed_now": anchor["zip_sha256"],
            "file_count": 40,
            "files": [
                {"path": "synthetic/report.md", "uncompressed_bytes": 12,
                 "sha256": "a" * 64},
            ],
        }
    monkeypatch.setattr(triage.zip_preflight, "audit_recovered_zip", inspect)
    candidate = tmp_path / "candidate.zip"
    receipt = triage.triage_candidates([(declared_role, candidate)])
    row = receipt["candidates"][0]
    assert examined == [candidate]
    assert receipt["schema_version"] == 3
    assert row["role"] == declared_role
    assert row["github_provider_zip_digest_and_size_match"] is False
    assert row["other_role_github_provider_zip_match"] == matched_role
    assert row["status"] == "matches_other_historical_role_not_declared_role"
    assert receipt["by_role"][declared_role]["provider_concordant_count"] == 0
    assert receipt["by_role"][declared_role]["other_role_provider_concordant_count"] == 1
    assert receipt["by_role"][declared_role]["distinct_provider_concordant_zip_count"] == 0
    assert receipt["other_role_provider_concordant_candidate_count"] == 1
    assert receipt["original_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False


@pytest.mark.parametrize("changed_field", ["archive_bytes", "archive_sha256_observed_now"])
def test_partial_other_role_pin_never_counts_as_match(tmp_path, monkeypatch, changed_field):
    anchor = triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES["evaluator_recovery"]
    evidence = {
        "archive_bytes": anchor["size_bytes"],
        "archive_sha256_observed_now": anchor["zip_sha256"],
        "file_count": 40,
            "files": [
                {"path": "synthetic/report.md", "uncompressed_bytes": 12,
                 "sha256": "a" * 64},
            ],
    }
    evidence[changed_field] = (
        anchor["size_bytes"] + 1 if changed_field == "archive_bytes" else "f" * 64
    )
    monkeypatch.setattr(
        triage.zip_preflight, "audit_recovered_zip", lambda path, **_kwargs: evidence
    )
    receipt = triage.triage_candidates([
        ("original_treatment", tmp_path / "candidate.zip")
    ])
    row = receipt["candidates"][0]
    assert row["other_role_github_provider_zip_match"] is None
    assert row["status"] == "does_not_match_historical_github_provider_zip"
    assert receipt["other_role_provider_concordant_candidate_count"] == 0
    assert receipt["by_role"]["original_treatment"]["other_role_provider_concordant_count"] == 0
    assert receipt["human_evaluation_ready"] is False


def test_repacked_zip_with_different_compression_is_same_regular_member_content(tmp_path):
    first = _zip(tmp_path / "deflated.zip")
    second = tmp_path / "stored.zip"
    with zipfile.ZipFile(second, "w", compression=zipfile.ZIP_STORED) as stream:
        stream.writestr("synthetic/report.md", "# Not a historical result\n")
    assert first.read_bytes() != second.read_bytes()
    receipt = triage.triage_candidates([
        ("original_treatment", first),
        ("evaluator_recovery", second),
    ])
    a, b = receipt["candidates"]
    assert a["observed_zip_sha256"] != b["observed_zip_sha256"]
    assert a["duplicate_verified_zip_of_candidate_index"] is None
    assert b["duplicate_verified_zip_of_candidate_index"] is None
    assert a["observed_regular_member_content_sha256"] == b["observed_regular_member_content_sha256"]
    assert a["same_regular_members_as_candidate_index"] is None
    assert b["same_regular_members_as_candidate_index"] == 1
    assert receipt["verified_zip_byte_duplicate_count"] == 0
    assert receipt["same_regular_members_duplicate_count"] == 1
    assert receipt["by_role"]["original_treatment"]["distinct_regular_member_content_count"] == 1
    assert receipt["by_role"]["evaluator_recovery"]["distinct_regular_member_content_count"] == 1
    assert receipt["original_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False


def test_member_order_does_not_create_distinct_regular_content(tmp_path):
    a = tmp_path / "a.zip"
    b = tmp_path / "b.zip"
    files = [("sources/a.md", "one"), ("sources/b.md", "two")]
    for path, pairs in ((a, files), (b, list(reversed(files)))):
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as stream:
            for filename, content in pairs:
                stream.writestr(filename, content)
    assert a.read_bytes() != b.read_bytes()
    receipt = triage.triage_candidates([
        ("original_treatment", a), ("original_treatment", b),
    ])
    assert receipt["candidates"][1]["same_regular_members_as_candidate_index"] == 1
    assert receipt["candidates"][1]["duplicate_verified_zip_of_candidate_index"] is None
    assert receipt["by_role"]["original_treatment"]["distinct_structurally_verified_zip_count"] == 2
    assert receipt["by_role"]["original_treatment"]["distinct_regular_member_content_count"] == 1


def test_changed_member_and_unsafe_candidate_never_claim_equal_content(tmp_path):
    a = _zip(tmp_path / "a.zip")
    b = tmp_path / "b.zip"
    with zipfile.ZipFile(b, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr("synthetic/report.md", "# Different synthetic content\n")
    broken = tmp_path / "bad.zip"
    broken.write_bytes(b"not zip content")
    receipt = triage.triage_candidates([
        ("original_treatment", a),
        ("evaluator_recovery", b),
        ("evaluator_recovery", broken),
    ])
    first, second, invalid = receipt["candidates"]
    assert first["observed_regular_member_content_sha256"] != second["observed_regular_member_content_sha256"]
    assert second["same_regular_members_as_candidate_index"] is None
    assert invalid["status"] == "structural_preflight_failed"
    assert invalid["observed_regular_member_content_sha256"] is None
    assert invalid["same_regular_members_as_candidate_index"] is None
    assert receipt["same_regular_members_duplicate_count"] == 0
    assert receipt["by_role"]["evaluator_recovery"]["distinct_regular_member_content_count"] == 1
    assert receipt["all_explicit_candidates_accounted_for"] is True


def test_batch_decompression_budget_accounts_for_all_candidates_without_preferring_outcomes(
    tmp_path, monkeypatch,
):
    """Earlier inspected sources reserve bytes; later oversized ones stay visible."""
    def source(name, count):
        path = tmp_path / name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as stream:
            stream.writestr("synthetic/evidence.md", "x" * count)
        return path

    first = source("first.zip", 25)
    too_large_for_remaining = source("second.zip", 25)
    later_small = source("third.zip", 8)
    before = [path.read_bytes() for path in (first, too_large_for_remaining, later_small)]
    monkeypatch.setattr(triage, "MAX_BATCH_UNCOMPRESSED_BYTES", 35)

    receipt = triage.triage_candidates([
        ("original_treatment", first),
        ("evaluator_recovery", too_large_for_remaining),
        ("original_treatment", later_small),
    ])
    rows = receipt["candidates"]
    assert [row["candidate_index"] for row in rows] == [1, 2, 3]
    assert [row["status"] for row in rows] == [
        "does_not_match_historical_github_provider_zip",
        "not_inspected_batch_decompression_budget_exceeded",
        "does_not_match_historical_github_provider_zip",
    ]
    assert rows[1]["structural_preflight_succeeded"] is False
    assert rows[1]["observed_regular_member_content_sha256"] is None
    assert "observed_zip_sha256" not in rows[1]
    assert receipt["batch_declared_uncompressed_byte_budget"] == 35
    assert receipt["batch_declared_uncompressed_bytes_reserved"] == 33
    assert receipt["batch_candidates_not_inspected_due_to_budget"] == 1
    assert receipt["all_explicit_candidates_accounted_for"] is True
    assert receipt["human_evaluation_ready"] is False
    assert [path.read_bytes() for path in (first, too_large_for_remaining, later_small)] == before


def test_invalid_stream_after_reservation_does_not_refund_batch_budget(
    tmp_path, monkeypatch,
):
    """A failed archive cannot force repeated expensive decompression attempts."""
    first = _zip(tmp_path / "first.zip")
    second = _zip(tmp_path / "second.zip")
    declared = len("# Not a historical result\n")
    monkeypatch.setattr(triage, "MAX_BATCH_UNCOMPRESSED_BYTES", declared + 1)

    def fail_member_stream(_self, *_args, **_kwargs):
        raise zipfile.BadZipFile("synthetic stream integrity failure")

    monkeypatch.setattr(zipfile.ZipFile, "open", fail_member_stream)
    receipt = triage.triage_candidates([
        ("original_treatment", first),
        ("original_treatment", second),
    ])
    rows = receipt["candidates"]
    assert rows[0]["status"] == "structural_preflight_failed"
    assert rows[1]["status"] == "not_inspected_batch_decompression_budget_exceeded"
    assert receipt["batch_declared_uncompressed_bytes_reserved"] == declared
    assert receipt["batch_candidates_not_inspected_due_to_budget"] == 1
    assert receipt["human_evaluation_ready"] is False


def test_preflight_reservation_rejects_before_any_member_stream_is_opened(
    tmp_path, monkeypatch,
):
    """Even a structurally valid ZIP is not decompressed if the ledger rejects."""
    path = _zip(tmp_path / "evidence.zip")
    reserved = []

    def reject(count):
        reserved.append(count)
        raise triage.BatchUncompressedBudgetExceeded("synthetic budget exhausted")

    def fail_if_opened(_self, *_args, **_kwargs):
        pytest.fail("member decompression must not begin after budget rejection")

    monkeypatch.setattr(zipfile.ZipFile, "open", fail_if_opened)
    with pytest.raises(triage.BatchUncompressedBudgetExceeded):
        triage.zip_preflight.audit_recovered_zip(
            path, reserve_uncompressed_bytes=reject
        )
    assert reserved == [len("# Not a historical result\n")]
