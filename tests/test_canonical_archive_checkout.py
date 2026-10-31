"""Synthetic offline tests for canonical archive/checkout concordance.

Fixtures contain no real experimental data, recovered traces, or human scores.
"""
import hashlib
import zipfile

import pytest

from scripts import verify_canonical_archive_checkout as audit


def _fixture(tmp_path, monkeypatch, *, missing=(), extra=(), altered=(), archive_overrides=None):
    root = tmp_path / "checkout"
    sources = {}
    for relative in audit.CANONICAL_MEMBERS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = ("synthetic snapshot: " + relative + "\n").encode("utf-8")
        path.write_bytes(content)
        sources[relative] = content
    archive = tmp_path / "canonical.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for relative, content in sources.items():
            if relative not in missing:
                out.writestr(
                    relative,
                    b"changed synthetic evidence" if relative in altered
                    else (archive_overrides or {}).get(relative, content),
                )
        for relative in extra:
            out.writestr(relative, b"unexpected synthetic bytes")
    monkeypatch.setattr(audit.custody, "run_verified", lambda root: {"ok": True})
    return root, archive, sources


def test_exact_canonical_bundle_matches_after_upstream_provenance_gate(
    tmp_path, monkeypatch
):
    root, archive, sources = _fixture(tmp_path, monkeypatch)
    observed = audit.verify_archive_against_checkout(
        archive, root=root, expected_archive_sha256=hashlib.sha256(
            archive.read_bytes()
        ).hexdigest()
    )
    assert observed["status"] == (
        "canonical_archive_matches_verified_checkout_not_original_evidence"
    )
    assert len(observed["matched_files"]) == 7
    assert set(item["path"] for item in observed["matched_files"]) == set(sources)
    assert observed["independently_supplied_archive_pin_matched"] is True
    assert observed["historical_evidence_authenticated"] is False
    assert observed["original_treatment_traces_authenticated"] is False
    assert observed["human_evaluation_ready"] is False
    assert observed["experimental_treatments_rerun"] is False
    assert observed["human_ratings_generated"] is False


@pytest.mark.parametrize("missing,extra", [
    (("outputs/main_study_runs.csv",), ()),
    ((), ("outputs/another-results.csv",)),
    (("paper/MAIN_STUDY_INFERENCE.md",), ("paper/other.md",)),
])
def test_missing_extra_or_substituted_members_fail_closed(
    tmp_path, monkeypatch, missing, extra
):
    root, archive, _ = _fixture(
        tmp_path, monkeypatch, missing=missing, extra=extra
    )
    with pytest.raises(ValueError, match="member set differs"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_complete_replacement_zip_with_changed_report_fails_closed(
    tmp_path, monkeypatch
):
    root, archive, _ = _fixture(
        tmp_path, monkeypatch, altered=("paper/MAIN_STUDY_INFERENCE.md",)
    )
    with pytest.raises(ValueError, match="file bytes differ"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_wrong_independent_archive_pin_is_not_silently_replaced(
    tmp_path, monkeypatch
):
    root, archive, _ = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="archive SHA-256 differs"):
        audit.verify_archive_against_checkout(
            archive, root=root, expected_archive_sha256="0" * 64
        )


def test_provenance_gate_failure_blocks_even_identical_bundle(
    tmp_path, monkeypatch
):
    root, archive, _ = _fixture(tmp_path, monkeypatch)
    def reject(_root):
        raise ValueError("canonical provenance does not verify")
    monkeypatch.setattr(audit.custody, "run_verified", reject)
    with pytest.raises(ValueError, match="provenance does not verify"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_checkout_changed_during_upstream_gate_is_rejected(
    tmp_path, monkeypatch
):
    root, archive, sources = _fixture(tmp_path, monkeypatch)
    def mutate(_root):
        target = root / "outputs/main_study_runs.csv"
        target.write_bytes(sources["outputs/main_study_runs.csv"] + b"mutation")
    monkeypatch.setattr(audit.custody, "run_verified", mutate)
    with pytest.raises(ValueError, match="changed during upstream"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_checkout_changed_during_zip_scan_is_rejected(
    tmp_path, monkeypatch
):
    root, archive, sources = _fixture(tmp_path, monkeypatch)
    original = audit.zip_preflight.audit_recovered_zip
    def mutate(*args, **kwargs):
        receipt = original(*args, **kwargs)
        target = root / "outputs/posthoc_support_runs.csv"
        target.write_bytes(sources["outputs/posthoc_support_runs.csv"] + b"mutation")
        return receipt
    monkeypatch.setattr(audit.zip_preflight, "audit_recovered_zip", mutate)
    with pytest.raises(ValueError, match="changed during archive"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_symlinked_checkout_member_is_not_accepted(tmp_path, monkeypatch):
    root, archive, _ = _fixture(tmp_path, monkeypatch)
    target = root / "outputs/main_study_inference.json"
    other = root / "other.json"
    other.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(other)
    with pytest.raises(ValueError, match="regular file"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_github_observed_v1_provenance_is_not_mistaken_for_v2_checkout(
    tmp_path, monkeypatch
):
    archived_v1 = b"synthetic legacy provenance receipt v1"
    monkeypatch.setattr(
        audit, "PUBLISHED_ARCHIVED_PROVENANCE_SHA256",
        hashlib.sha256(archived_v1).hexdigest(),
    )
    root, archive, sources = _fixture(
        tmp_path, monkeypatch,
        archive_overrides={audit.PROVENANCE_RECEIPT: archived_v1},
    )
    receipt = audit.verify_archive_against_checkout(archive, root=root)
    assert receipt["historical_workflow_receipt_exception_used"] is True
    assert receipt["status"] == (
        "canonical_archive_matches_checkout_and_pinned_historical_receipt_not_original_evidence"
    )
    assert receipt["archived_provenance_receipt_sha256"] == hashlib.sha256(
        archived_v1
    ).hexdigest()
    assert receipt["verified_checkout_provenance_receipt_sha256"] == hashlib.sha256(
        sources[audit.PROVENANCE_RECEIPT]
    ).hexdigest()
    matched = {member["path"]: member for member in receipt["matched_files"]}
    assert len(matched) == 7
    assert matched[audit.PROVENANCE_RECEIPT]["sha256"] != (
        receipt["verified_checkout_provenance_receipt_sha256"]
    )
    assert matched[audit.PROVENANCE_RECEIPT]["match_basis"] == (
        "pinned_github_workflow_v1_receipt"
    )
    assert all(
        member["match_basis"] == "verified_checkout"
        for path, member in matched.items() if path != audit.PROVENANCE_RECEIPT
    )
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False


def test_unpinned_v1_lookalike_fails_closed(tmp_path, monkeypatch):
    root, archive, _ = _fixture(
        tmp_path, monkeypatch,
        archive_overrides={
            audit.PROVENANCE_RECEIPT: b"arbitrary unpinned synthetic receipt"
        },
    )
    with pytest.raises(ValueError, match="pinned published provenance receipt"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_pinned_v1_receipt_cannot_mask_changed_analysis_bytes(
    tmp_path, monkeypatch
):
    archived_v1 = b"synthetic legacy provenance receipt v1"
    monkeypatch.setattr(
        audit, "PUBLISHED_ARCHIVED_PROVENANCE_SHA256",
        hashlib.sha256(archived_v1).hexdigest(),
    )
    root, archive, _ = _fixture(
        tmp_path, monkeypatch,
        archive_overrides={audit.PROVENANCE_RECEIPT: archived_v1},
        altered=("outputs/main_study_inference.json",),
    )
    with pytest.raises(ValueError, match="main_study_inference.json"):
        audit.verify_archive_against_checkout(archive, root=root)


def test_identical_v2_receipt_does_not_claim_historical_exception(
    tmp_path, monkeypatch
):
    root, archive, sources = _fixture(tmp_path, monkeypatch)
    receipt = audit.verify_archive_against_checkout(archive, root=root)
    assert receipt["historical_workflow_receipt_exception_used"] is False
    assert receipt["historical_workflow_receipt_pin_source"] is None
    assert receipt["archived_provenance_receipt_sha256"] == hashlib.sha256(
        sources[audit.PROVENANCE_RECEIPT]
    ).hexdigest()
    assert {entry["match_basis"] for entry in receipt["matched_files"]} == {
        "verified_checkout"
    }
