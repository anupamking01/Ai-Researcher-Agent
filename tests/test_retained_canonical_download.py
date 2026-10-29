"""Synthetic tests of historical GitHub source binding and audit gating.

Fixtures are not original treatment evidence or human judgments.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from scripts import verify_retained_canonical_download as audit


NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def _fixture(tmp_path, monkeypatch):
    archive = tmp_path / "retained.zip"
    archive.write_bytes(b"synthetic canonical zip fixture; not original evidence")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(audit, "OBSERVED_ZIP_BYTES", archive.stat().st_size)
    monkeypatch.setattr(audit, "OBSERVED_ZIP_SHA256", sha)
    metadata = {
        "id": audit.ARTIFACT_ID,
        "name": audit.ARTIFACT_NAME,
        "expired": False,
        "expires_at": "2026-12-23T23:03:46Z",
        "size_in_bytes": audit.OBSERVED_ZIP_BYTES,
        "digest": f"sha256:{sha}",
        "archive_download_url": (
            f"https://api.github.com/repos/{audit.REPO}/actions/artifacts/"
            f"{audit.ARTIFACT_ID}/zip"
        ),
        "workflow_run": {
            "id": audit.RUN_ID,
            "head_sha": audit.RUN_HEAD,
            "head_branch": "research-paper-eval-2027",
            "repository_id": audit.REPO_ID,
            "head_repository_id": audit.REPO_ID,
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    def verified(archive_path, *, root):
        assert Path(archive_path) == archive
        return {
            "archive_sha256_observed_now": sha,
            "historical_evidence_authenticated": False,
            "original_treatment_traces_authenticated": False,
            "human_evaluation_ready": False,
            "independently_supplied_archive_pin_matched": False,
        }
    monkeypatch.setattr(audit.concordance, "verify_archive_against_checkout", verified)
    return metadata_path, archive, metadata


def _check(path, archive):
    return audit.verify_download(path, archive, checked_at=NOW)


def test_valid_provider_observation_proceeds_to_checkout_gate(tmp_path, monkeypatch):
    metadata_path, archive, _ = _fixture(tmp_path, monkeypatch)
    result = _check(metadata_path, archive)
    assert result["status"] == (
        "provider_observed_canonical_archive_concordance_verified_not_original_evidence"
    )
    assert result["provider_reported_zip_sha256_matched"] is True
    assert result["independent_historical_custody_authenticated"] is False
    assert result["original_treatment_traces_authenticated"] is False
    assert result["human_evaluation_ready"] is False
    assert result["treatments_or_evaluators_rerun"] is False
    assert result["human_ratings_generated"] is False


@pytest.mark.parametrize("field,changed,message", [
    ("id", 900, "artifact ID"),
    ("name", "unrelated-artifact", "artifact name"),
    ("expired", True, "expired"),
    ("expires_at", "2026-10-01T00:00:00Z", "expiry has elapsed"),
    ("size_in_bytes", 99999, "byte size"),
    ("digest", "sha256:" + "0" * 64, "ZIP digest"),
    ("archive_download_url", "https://example.com/zip", "download URL"),
])
def test_changed_artifact_metadata_fails_closed(
    tmp_path, monkeypatch, field, changed, message
):
    metadata_path, archive, metadata = _fixture(tmp_path, monkeypatch)
    metadata[field] = changed
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        _check(metadata_path, archive)


@pytest.mark.parametrize("field,changed", [
    ("id", 111),
    ("head_sha", "0" * 40),
    ("head_branch", "main"),
    ("repository_id", 123),
    ("head_repository_id", 123),
])
def test_swapped_historical_run_identity_fails(
    tmp_path, monkeypatch, field, changed
):
    metadata_path, archive, metadata = _fixture(tmp_path, monkeypatch)
    metadata["workflow_run"][field] = changed
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="workflow identity"):
        _check(metadata_path, archive)


def test_downloaded_archive_tampering_fails_before_checkout(
    tmp_path, monkeypatch
):
    metadata_path, archive, _ = _fixture(tmp_path, monkeypatch)
    archive.write_bytes(b"x" * archive.stat().st_size)
    with pytest.raises(ValueError, match="retained ZIP bytes differ"):
        _check(metadata_path, archive)


def test_failed_actual_concordance_cannot_be_saved_as_success(tmp_path, monkeypatch):
    metadata_path, archive, _ = _fixture(tmp_path, monkeypatch)
    def reject(*args, **kwargs):
        raise ValueError("canonical checkout provenance failed")
    monkeypatch.setattr(audit.concordance, "verify_archive_against_checkout", reject)
    with pytest.raises(ValueError, match="provenance failed"):
        _check(metadata_path, archive)


def test_changed_zip_during_concordance_is_rejected(tmp_path, monkeypatch):
    metadata_path, archive, _ = _fixture(tmp_path, monkeypatch)
    def wrong_hash(*args, **kwargs):
        return {"archive_sha256_observed_now": "0" * 64}
    monkeypatch.setattr(audit.concordance, "verify_archive_against_checkout", wrong_hash)
    with pytest.raises(ValueError, match="changed between source"):
        _check(metadata_path, archive)


def test_duplicate_metadata_key_is_not_silently_accepted(tmp_path, monkeypatch):
    metadata_path, archive, _ = _fixture(tmp_path, monkeypatch)
    text = metadata_path.read_text()
    metadata_path.write_text(text.replace('"id":', '"id": 5, "id":', 1))
    with pytest.raises(ValueError, match="duplicate GitHub metadata JSON key"):
        _check(metadata_path, archive)


def test_fake_independent_authentication_claim_is_rejected(tmp_path, monkeypatch):
    metadata_path, archive, _ = _fixture(tmp_path, monkeypatch)
    def wrong_claim(*args, **kwargs):
        return {
            "archive_sha256_observed_now": audit.OBSERVED_ZIP_SHA256,
            "historical_evidence_authenticated": True,
        }
    monkeypatch.setattr(audit.concordance, "verify_archive_against_checkout", wrong_claim)
    with pytest.raises(ValueError, match="unexpected historical authentication"):
        _check(metadata_path, archive)


def test_workflow_is_read_only_and_runs_real_concordance_before_archive_retention():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/retained-canonical-archive-audit.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert ".github/workflows/retained-canonical-archive-audit.yml" in workflow
    assert "actions: read" in workflow and "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "run_budget_main_study" not in workflow
    assert "download-artifact" not in workflow  # We need the original ZIP, not extracted files.
    assert (
        workflow.index("Download exact canonical-run artifact metadata")
        < workflow.index("Download raw retained canonical ZIP")
        < workflow.index("python -m scripts.verify_retained_canonical_download")
        < workflow.index("Retain verified provider-observed ZIP")
    )
    assert "10837878458/zip" in workflow
    assert "if-no-files-found: error" in workflow


def test_retained_workflow_uses_exact_provenance_bound_revision_and_binds_live_results():
    """Code drift must not weaken the frozen receipt or silently redefine outputs."""
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/retained-canonical-archive-audit.yml"
    ).read_text(encoding="utf-8")
    anchor = "f333623380526fa05dcb14110e7ec1fb72d2d0e2"
    assert f"ref: {anchor}" in workflow
    assert "path: frozen-analysis-checkout" in workflow
    assert 'test "$(git -C "$frozen" rev-parse HEAD)" = "' + anchor + '"' in workflow
    for relative in (
        "outputs/canonical_analysis_source.json",
        "outputs/main_study_analysis_inputs_manifest.json",
        "outputs/main_study_inference.json",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "paper/MAIN_STUDY_INFERENCE.md",
    ):
        assert relative in workflow
    assert 'cmp -- "${GITHUB_WORKSPACE}/${relative}" "$frozen/${relative}"' in workflow
    assert '--root "${GITHUB_WORKSPACE}/frozen-analysis-checkout"' in workflow
    assert (
        workflow.index("Checkout provenance-bound canonical analysis revision")
        < workflow.index("Bind current published scientific bytes")
        < workflow.index("Download exact canonical-run artifact metadata")
        < workflow.index("python -m scripts.verify_retained_canonical_download")
        < workflow.index("Retain verified provider-observed ZIP")
    )
